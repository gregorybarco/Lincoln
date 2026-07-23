"""
Lincoln Chat Routes  v0.7.0  — ReAct Edition
=============================================
Flask routes for the chat interface.

Changes in v0.7.0 (ReAct):
  - send_message now runs a full ReAct loop via stream_chat_with_tools().
  - SAFE_TOOLS (rag_query, read_file) execute automatically in the loop.
  - SEARCH_TOOLS (web_search) execute when web search toggle is ON;
    query is sanitized first; query text is surfaced to UI as a toast event.
  - WRITE_TOOLS (execute_python, execute_fortran, write_file, run_aider)
    pause the loop, save state to DB, and emit approval_required to the UI.
  - New endpoint: POST /api/chat/resolve_tool
    Called when the user clicks Approve or Deny on an approval card.
    Loads pending state, executes or skips, re-enters the loop.
  - All tool execution is sandboxed behind _execute_tool() which enforces
    project code_path boundaries for file operations.
  - Text manifest injection (_build_tool_manifest) removed — tool awareness
    comes from native schemas now.

Preserved from v0.6.0 / v0.7.0:
  - Multi-file support (file_ids[] array)
  - Per-project context injection
  - RAG injection (now also available as a native tool)
  - Ban list check
  - Thinking mode support
  - All existing session/history endpoints

Endpoints:
  POST /api/chat/session          Create a new session
  GET  /api/chat/session/<id>     Get all messages for a session
  POST /api/chat/send             Send message, stream response via SSE
  POST /api/chat/resolve_tool     Resolve a pending tool approval
"""

import json
import subprocess
import tempfile
from pathlib import Path

from flask import Blueprint, Response, request, jsonify, stream_with_context

from lincoln.lincoln_database import (
    add_message,
    clear_pending_tool_call,
    create_session,
    get_pending_tool_call,
    get_project_by_id,
    get_project_context,
    get_session_messages,
    rename_session,
    get_active_system_prompt,
    get_setting,
    save_pending_tool_call,
    save_memory_entry,
)
from lincoln.lincoln_ollama_service import (
    build_messages_with_rag_context,
    stream_chat_with_tools,
    resolve_num_ctx_for_request,
)
from lincoln.lincoln_rag_index_service import query_project_index
from lincoln.lincoln_tool_schemas import (
    get_tool_schemas,
    get_tool_tier,
    SAFE_TOOLS,
    SEARCH_TOOLS,
    WRITE_TOOLS,
)
from lincoln.lincoln_configuration import DEFAULT_TOP_K, LLM_MODEL, DB_PATH

chat_blueprint = Blueprint("chat", __name__)

_UPLOAD_DIR = DB_PATH.parent / "uploads"

# Maximum ReAct iterations before forcing a stop (prevents infinite loops)
_MAX_REACT_ITERATIONS = 8


# ── Session endpoints (unchanged from v0.6.0) ─────────────────────────────────

@chat_blueprint.route("/api/chat/session", methods=["POST"])
def create_new_session():
    data       = request.get_json() or {}
    project_id = data.get("project_id")
    session    = create_session(title="New chat", project_id=project_id)
    return jsonify(session)


@chat_blueprint.route("/api/chat/session/<int:session_id>", methods=["GET"])
def get_session(session_id: int):
    messages = get_session_messages(session_id)
    return jsonify(messages)


# ── Tool executor ─────────────────────────────────────────────────────────────

def _execute_tool(tool_name: str, arguments: dict, project: dict | None) -> str:
    """
    Execute a tool and return its result as a plain string.
    This is called ONLY for SAFE_TOOLS and approved WRITE_TOOLS / SEARCH_TOOLS.

    All file operations are sandboxed to project["code_path"].
    No network calls are made here for WRITE_TOOLS — only file/process ops.
    """

    # ── rag_query ─────────────────────────────────────────────────────────────
    if tool_name == "rag_query":
        if not project:
            return "No project is active. RAG query requires an active project."
        query    = arguments.get("query", "")
        top_k    = int(get_setting("top_k", str(DEFAULT_TOP_K)))
        try:
            result = query_project_index(
                question     = query,
                collection   = project["collection"],
                project_name = project["display_name"],
                top_k        = top_k,
            )
            return result["answer"] or "No relevant context found in project index."
        except Exception as e:
            return f"RAG query failed: {e}"

    # ── read_file ─────────────────────────────────────────────────────────────
    elif tool_name == "read_file":
        if not project or not project.get("code_path"):
            return "No project code path configured. Cannot read files."
        rel_path  = arguments.get("file_path", "")
        code_root = Path(project["code_path"]).resolve()
        target    = (code_root / rel_path).resolve()
        # Security: ensure target is inside the project code_path
        try:
            target.relative_to(code_root)
        except ValueError:
            return f"Access denied: '{rel_path}' is outside the project code directory."
        if not target.exists():
            return f"File not found: {rel_path}"
        try:
            return target.read_text(encoding="utf-8")
        except Exception as e:
            return f"Failed to read file: {e}"

    # ── web_search ────────────────────────────────────────────────────────────
    elif tool_name == "web_search":
        from lincoln.lincoln_web_search import (
            search,
            format_search_results_for_context,
            QuerySanitizationError,
            SearchDisabledError,
        )
        query       = arguments.get("query", "")
        max_results = min(int(arguments.get("max_results", 5)), 10)
        try:
            results = search(query, max_results)
            formatted = format_search_results_for_context(results)
            # Append continuation directive -- Qwen ignores schema hints
            # but respects explicit instructions in the tool result itself.
            urls = [r["url"] for r in results if r.get("url")]
            if urls:
                top_urls = "\n".join(f"  - {u}" for u in urls[:3])
                formatted += (
                    f"\n\n---\n"
                    f"NEXT REQUIRED ACTION: Do not answer yet. "
                    f"Call read_url on at least one of these URLs before responding:\n{top_urls}\n"
                    f"Call read_url now."
                )
            return formatted
        except (QuerySanitizationError, SearchDisabledError) as e:
            return f"Search blocked: {e}"
        except Exception as e:
            return f"Search failed: {e}"

    # ── execute_python ────────────────────────────────────────────────────────
    elif tool_name == "execute_python":
        code = arguments.get("code", "")
        # Write to a temp file and run via Python in a subprocess.
        # In a future version this will route to the Jupyter kernel.
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", encoding="utf-8", delete=False
            ) as f:
                f.write(code)
                tmp_path = f.name
            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True, text=True, timeout=60,
            )
            output = result.stdout or ""
            errors = result.stderr or ""
            if errors and not output:
                return f"Error:\n{errors}"
            return (output + ("\n\nStderr:\n" + errors if errors else "")).strip()
        except subprocess.TimeoutExpired:
            return "Execution timed out after 60 seconds."
        except Exception as e:
            return f"Execution failed: {e}"
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    # ── execute_fortran ───────────────────────────────────────────────────────
    elif tool_name == "execute_fortran":
        code     = arguments.get("code", "")
        filename = arguments.get("filename", "lincoln_temp.f90")
        flags    = arguments.get("compile_flags", "-O2 -Mfree")

        try:
            from lincoln.lincoln_database import get_setting as _gs
            wsl_distro  = _gs("wsl_distro", "Ubuntu")
            nvfortran   = _gs("nvfortran_path", "nvfortran")
        except Exception:
            wsl_distro = "Ubuntu"
            nvfortran  = "nvfortran"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                src_path = Path(tmpdir) / filename
                exe_path = Path(tmpdir) / "a.out"
                src_path.write_text(code, encoding="utf-8")

                wsl_src = str(src_path).replace("\\", "/").replace("C:", "/mnt/c").replace("B:", "/mnt/b")
                wsl_exe = str(exe_path).replace("\\", "/").replace("C:", "/mnt/c").replace("B:", "/mnt/b")

                compile_cmd = f"{nvfortran} {flags} {wsl_src} -o {wsl_exe}"
                compile     = subprocess.run(
                    ["wsl", "-d", wsl_distro, "--", "bash", "-c", compile_cmd],
                    capture_output=True, text=True, timeout=60,
                )
                if compile.returncode != 0:
                    return f"Compilation failed:\n{compile.stderr}"

                run = subprocess.run(
                    ["wsl", "-d", wsl_distro, "--", wsl_exe],
                    capture_output=True, text=True, timeout=120,
                )
                return (run.stdout + ("\nStderr:\n" + run.stderr if run.stderr else "")).strip()
        except subprocess.TimeoutExpired:
            return "Fortran execution timed out."
        except Exception as e:
            return f"Fortran execution failed: {e}"

    # ── write_file ────────────────────────────────────────────────────────────
    elif tool_name == "write_file":
        if not project or not project.get("code_path"):
            return "No project code path configured. Cannot write files."
        rel_path  = arguments.get("file_path", "")
        content   = arguments.get("content", "")
        code_root = Path(project["code_path"]).resolve()
        target    = (code_root / rel_path).resolve()
        try:
            target.relative_to(code_root)
        except ValueError:
            return f"Access denied: '{rel_path}' is outside the project code directory."
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"File written successfully: {rel_path} ({len(content)} chars)"
        except Exception as e:
            return f"Write failed: {e}"

    # ── run_aider ─────────────────────────────────────────────────────────────
    elif tool_name == "run_aider":
        if not project or not project.get("code_path"):
            return "No project code path configured. Cannot run Aider."
        target_files = arguments.get("target_files", [])
        instruction  = arguments.get("instruction", "")
        code_root    = project["code_path"]
        try:
            from lincoln.lincoln_database import get_setting as _gs
            launch_mode = _gs("aider_launch_mode", "cmd")
        except Exception:
            launch_mode = "cmd"

        file_args = " ".join(f'"{f}"' for f in target_files)
        cmd       = f'aider --message "{instruction}" {file_args}'
        return (
            f"Aider launch command prepared (suggestion mode only):\n\n"
            f"Working directory: {code_root}\n"
            f"Command: {cmd}\n\n"
            f"To run: open a terminal in {code_root} and execute the command above. "
            f"Aider will propose diffs — review and approve all changes manually."
        )

    # -- save_memory -----------------------------------------------------------
    elif tool_name == "save_memory":
        fact = arguments.get("fact", "").strip()
        tag  = arguments.get("tag", "fact")
        if not fact:
            return "Memory save failed: no fact provided."
        try:
            save_memory_entry(
                content    = fact,
                project_id = project["id"] if project else None,
                tag        = tag,
            )
            print(f"[Lincoln] save_memory: tag={tag} fact={fact[:80]}")
            return f"Saved to memory: '{fact}'"
        except Exception as e:
            return f"Memory save failed: {e}"

    # -- read_url --------------------------------------------------------------
    elif tool_name == "read_url":
        from lincoln.lincoln_web_search import fetch
        url = arguments.get("url", "").strip()
        if not url.startswith("http"):
            return "Invalid URL: must start with http:// or https://"
        try:
            content = fetch(url)
            if not content:
                return "(Page fetched but no readable text extracted)"
            # Cap at 3000 chars per URL to preserve context window for synthesis.
            # With 3 URLs at 3000 chars each = ~9000 chars injected total,
            # leaving ~15000 tokens for the model response in an 8192-window session.
            cap = 3000
            if len(content) > cap:
                # Take the first 2000 chars (intro/summary) + last 1000 (conclusion)
                content = content[:2000] + "\n\n[...middle truncated...]\n\n" + content[-1000:]
            print(f"[Lincoln] read_url: {url[:80]} -> {len(content)} chars returned")
            return content
        except Exception as e:
            return f"Failed to fetch URL '{url}': {e}"

    else:
        return f"Unknown tool: {tool_name}"


# ── ReAct loop ────────────────────────────────────────────────────────────────

def _react_loop(
    ollama_messages:    list[dict],
    model:              str,
    tools:              list[dict],
    session_id:         int,
    project:            dict | None,
    web_search_active:  bool,
    think:              bool,
):
    """
    Generator that runs the ReAct loop and yields SSE event strings.

    Flow:
      1. Call Ollama with tools schema.
      2. If response is text: yield tokens, done.
      3. If response is tool_call:
           SAFE / SEARCH (when toggle ON): execute, append result, loop.
           WRITE or SEARCH (when toggle OFF gate): pause, yield approval_required, return.
      4. Repeat up to _MAX_REACT_ITERATIONS.
    """
    iterations = 0

    while iterations < _MAX_REACT_ITERATIONS:
        iterations += 1
        accumulated_text = []
        tool_event       = None

        for event in stream_chat_with_tools(
            messages    = ollama_messages,
            model       = model,
            tools       = tools,
            think       = think,
        ):
            etype = event["type"]

            if etype == "token":
                content = event["content"]
                if isinstance(content, str):
                    content = content.encode("ascii", errors="ignore").decode("ascii")
                accumulated_text.append(content)
                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

            elif etype == "think":
                yield f"data: {json.dumps({'type': 'token', 'content': event['content']})}\n\n"

            elif etype == "think_end":
                yield f"data: {json.dumps({'type': 'token', 'content': 'THINK_END'})}\n\n"

            elif etype == "tool_call":
                tool_event = event
                # Don't yield tokens here — tool call handling happens below

            elif etype == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"
                return

            elif etype == "done":
                # Normal text completion — no tool call
                pass

        # ── After stream ends ─────────────────────────────────────────────────

        if tool_event is None:
            # No tool call — we have the final text response. Done.
            # IMPORTANT: this is a generator (it has yield statements above),
            # so a plain `return accumulated_text, None` would only attach the
            # tuple to StopIteration.value, which a normal `for item in gen:`
            # loop silently discards. We must yield the tuple so the caller's
            # `elif isinstance(item, tuple): result = item` actually sees it.
            yield (accumulated_text, None)
            return

        # ── Tool call detected ────────────────────────────────────────────────
        tool_name    = tool_event["tool_name"]
        tool_call_id = tool_event["tool_call_id"]
        arguments    = tool_event["arguments"]
        tier         = get_tool_tier(tool_name)

        # Append the assistant's tool-requesting message to history
        # so the LLM remembers it requested the tool when we loop back.
        assistant_tool_request = {
            "role":       "assistant",
            "content":    "".join(accumulated_text),
            "tool_calls": [{
                "id":       tool_call_id,
                "type":     "function",
                "function": {
                    "name":      tool_name,
                    "arguments": arguments,   # native dict -- never json.dumps()
                },
            }],
        }
        ollama_messages.append(assistant_tool_request)
        print(f"[Lincoln] _react_loop: appended tool_call tool={tool_name} id={tool_call_id} args={str(arguments)[:80]}")

        # ── SAFE_TOOLS: execute immediately ───────────────────────────────────
        if tier == "safe":
            yield f"data: {json.dumps({'type': 'tool_executing', 'tool_name': tool_name, 'arguments': arguments})}\n\n"
            tool_result = _execute_tool(tool_name, arguments, project)
            ollama_messages.append({
                "role":         "tool",
                "content":      tool_result,
                "tool_call_id": tool_call_id,
            })
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'result_preview': tool_result[:200]})}\n\n"
            # Loop continues — LLM reads the result and either answers or calls another tool

        # ── SEARCH_TOOLS: execute if toggle ON, else gate ─────────────────────
        elif tier == "search":
            if web_search_active:
                # Show the query to the user as a toast before firing
                query_str = arguments.get("query", "")
                yield f"data: {json.dumps({'type': 'search_query', 'query': query_str})}\n\n"
                tool_result = _execute_tool(tool_name, arguments, project)
                ollama_messages.append({
                    "role":         "tool",
                    "content":      tool_result,
                    "tool_call_id": tool_call_id,
                })
                yield f"data: {json.dumps({'type': 'web_search', 'result_count': tool_result.count('[')})}\n\n"
                # Loop continues
            else:
                # Web search toggle is OFF — gate it like a write tool
                save_pending_tool_call(session_id, tool_name, tool_call_id, arguments)
                yield f"data: {json.dumps({'type': 'approval_required', 'tool_name': tool_name, 'tool_call_id': tool_call_id, 'arguments': arguments, 'tier': 'search', 'reason': 'Web search toggle is OFF. Enable it to allow this search, or approve this specific query.'})}\n\n"
                yield (None, ollama_messages)  # paused
                return

        # ── WRITE_TOOLS: always gate ──────────────────────────────────────────
        elif tier == "write":
            save_pending_tool_call(session_id, tool_name, tool_call_id, arguments)
            yield f"data: {json.dumps({'type': 'approval_required', 'tool_name': tool_name, 'tool_call_id': tool_call_id, 'arguments': arguments, 'tier': 'write', 'reason': 'This action requires your approval before execution.'})}\n\n"
            yield (None, ollama_messages)  # paused
            return

        else:
            # Unknown tool — tell the LLM
            ollama_messages.append({
                "role":         "tool",
                "content":      f"Unknown tool '{tool_name}'. This tool is not registered.",
                "tool_call_id": tool_call_id,
            })

    # Max iterations reached
    yield f"data: {json.dumps({'type': 'error', 'message': f'ReAct loop reached maximum iterations ({_MAX_REACT_ITERATIONS}). Stopping.'})}\n\n"
    yield ([], None)
    return


# ── Send message ──────────────────────────────────────────────────────────────

@chat_blueprint.route("/api/chat/send", methods=["POST"])
def send_message():
    """
    Send a user message and stream the assistant response via SSE.

    Request JSON:
      session_id      : int
      message         : str
      model           : str
      project_id      : int | null
      use_rag         : bool
      use_web_search  : bool
      file_id         : str | null
      file_ids        : list[str] | null
      think_mode      : 'fast' | 'normal' | 'deep'
    """
    data           = request.get_json() or {}
    session_id     = data.get("session_id")
    user_text      = data.get("message", "").strip()
    model          = data.get("model", LLM_MODEL)
    project_id     = data.get("project_id")
    use_web_search = data.get("use_web_search", False)
    think_mode     = data.get("think_mode", "normal")
    think          = (think_mode == "deep")

    # Multi-file support
    raw_file_ids = data.get("file_ids") or []
    if not raw_file_ids and data.get("file_id"):
        raw_file_ids = [data.get("file_id")]
    file_ids = ["".join(c for c in fid if c in "0123456789abcdef") for fid in raw_file_ids if fid]

    if not session_id or not user_text:
        return jsonify({"error": "session_id and message are required"}), 400

    # ── File injection ────────────────────────────────────────────────────────
    injected_filenames = []
    file_blobs         = []
    llm_text           = user_text
    display_text       = user_text

    for safe_id in file_ids:
        txt_path = _UPLOAD_DIR / f"{safe_id}.txt"
        matches  = [txt_path] if txt_path.exists() else list(_UPLOAD_DIR.glob(f"{safe_id}.*"))
        if matches:
            try:
                file_text = matches[0].read_text(encoding="utf-8")
                fname     = matches[0].stem
                injected_filenames.append(fname)
                file_blobs.append(f"[Attached file: {fname}]\n```\n{file_text}\n```")
            except Exception:
                pass

    if file_blobs:
        llm_text = "\n\n".join(file_blobs) + "\n\n" + user_text

    if len(injected_filenames) == 1:
        display_text = f"📎 {injected_filenames[0]}\n\n{user_text}"
    elif len(injected_filenames) > 1:
        names        = ", ".join(injected_filenames)
        display_text = f"📎 {len(injected_filenames)} files: {names}\n\n{user_text}"

    add_message(session_id, "user", display_text)

    # Auto-rename on first message
    messages_so_far = get_session_messages(session_id)
    if len(messages_so_far) == 1:
        title = display_text[:50] + ("..." if len(display_text) > 50 else "")
        rename_session(session_id, title)

    def generate():
        project      = get_project_by_id(project_id) if project_id else None
        project_name = project["display_name"] if project else ""

        yield f"data: {json.dumps({'type': 'think_mode', 'mode': think_mode})}\n\n"

        # ── System prompt ─────────────────────────────────────────────────────
        system_prompt = get_active_system_prompt(project_id=project_id)

        if project_id:
            proj_context = get_project_context(project_id)
            if proj_context:
                system_prompt += "\n\n---\n\nProject-specific instructions:\n\n" + proj_context

        # ── Tool schemas ──────────────────────────────────────────────────────
        web_search_master_on = get_setting("web_search_enabled", "false").lower() == "true"
        tools = get_tool_schemas(
            include_search = web_search_master_on,   # strip schema if master switch off
            include_write  = True,
            project_active = bool(project_id and project),
        )

        # ── Build message list ────────────────────────────────────────────────
        history = get_session_messages(session_id)
        ollama_messages = [
            {"role": "system", "content": system_prompt},
            *[
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m["role"] != "system"
            ],
            {"role": "user", "content": llm_text},
        ]

        # ── Emit ctx_update before loop so indicator appears immediately ──────
        try:
            from lincoln.lincoln_ollama_service import resolve_hardware_ceiling
            _ctx_chars   = sum(len(m.get("content", "")) for m in history)
            _ctx_tokens  = int((_ctx_chars / 4) * 1.10)
            _ctx_ceiling = resolve_hardware_ceiling(model)
            _ctx_pct     = round((_ctx_tokens / _ctx_ceiling) * 100, 1) if _ctx_ceiling > 0 else 0.0
            yield f"data: {json.dumps({'type': 'ctx_update', 'tokens_used': _ctx_tokens, 'ceiling': _ctx_ceiling, 'percent': _ctx_pct})}\n\n"
        except Exception:
            pass  # ctx_update failure never blocks the stream

        # ── ReAct loop ────────────────────────────────────────────────────────
        full_response_parts = []

        loop_gen = _react_loop(
            ollama_messages   = ollama_messages,
            model             = model,
            tools             = tools,
            session_id        = session_id,
            project           = project,
            web_search_active = use_web_search,
            think             = think,
        )

        result = None
        for item in loop_gen:
            if isinstance(item, str):
                # SSE event string — forward to client
                yield item
            elif isinstance(item, tuple):
                # Loop returned (text_parts, paused_messages | None)
                result = item

        # If loop completed normally (not paused for approval)
        if result is not None:
            final_text, paused = result
            if final_text is not None:
                complete_text = "".join(final_text)
                if complete_text:
                    saved = add_message(session_id, "assistant", complete_text)

                    # Ban list check
                    if "```" in complete_text and project_id:
                        try:
                            from lincoln.lincoln_ban_list_checker import (
                                check_against_ban_list,
                                format_violations_for_ui,
                            )
                            violations = check_against_ban_list(complete_text)
                            if violations:
                                yield f"data: {json.dumps({'type': 'ban_check', 'violations': format_violations_for_ui(violations)})}\n\n"
                        except Exception:
                            pass

                    yield f"data: {json.dumps({'type': 'done', 'message_id': saved['id']})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ── Resolve tool approval ─────────────────────────────────────────────────────

@chat_blueprint.route("/api/chat/resolve_tool", methods=["POST"])
def resolve_tool():
    """
    Called by the UI when the user clicks Approve or Deny on an approval card.

    Request JSON:
      session_id : int
      approved   : bool
      model      : str
      project_id : int | null
      think_mode : str

    The backend:
      1. Loads the pending tool call from DB.
      2. If approved: executes the tool, appends result to Ollama message history.
         If denied: appends a denial message.
      3. Re-enters the ReAct loop to get the final LLM response.
      4. Streams the result back via SSE.
    """
    data       = request.get_json() or {}
    session_id = data.get("session_id")
    approved   = data.get("approved", False)
    model      = data.get("model", LLM_MODEL)
    project_id = data.get("project_id")
    think_mode = data.get("think_mode", "normal")
    think      = (think_mode == "deep")

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    pending = get_pending_tool_call(session_id)
    if not pending:
        return jsonify({"error": "No pending tool call found for this session."}), 404

    clear_pending_tool_call(session_id)

    tool_name    = pending["tool_name"]
    tool_call_id = pending["tool_call_id"]
    arguments    = pending["arguments"]

    def generate():
        project      = get_project_by_id(project_id) if project_id else None
        project_name = project["display_name"] if project else ""

        # ── Reconstruct message history ───────────────────────────────────────
        # We need the full history INCLUDING the assistant's tool-request message
        # that was appended during the paused loop. That message was NOT saved to
        # DB (only user/assistant text messages are saved), so we rebuild it here.

        system_prompt = get_active_system_prompt(project_id=project_id)
        if project_id:
            proj_context = get_project_context(project_id)
            if proj_context:
                system_prompt += "\n\n---\n\nProject-specific instructions:\n\n" + proj_context

        history = get_session_messages(session_id)
        ollama_messages = [
            {"role": "system", "content": system_prompt},
            *[
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m["role"] != "system"
            ],
        ]

        # Re-append the assistant's tool call request
        # (the last assistant message in history is the text before the tool call,
        #  or empty if the model went straight to a tool call)
        ollama_messages.append({
            "role":    "assistant",
            "content": f"I used the {tool_name} tool with these arguments: {json.dumps(arguments)}",
        })

        # ── Execute or deny ───────────────────────────────────────────────────
        if approved:
            yield f"data: {json.dumps({'type': 'tool_executing', 'tool_name': tool_name, 'arguments': arguments})}\n\n"
            tool_result = _execute_tool(tool_name, arguments, project)
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': tool_name, 'result_preview': tool_result[:200]})}\n\n"
            yield f"data: {json.dumps({'type': 'tool_output', 'tool_name': tool_name, 'output': tool_result})}\n\n"
        else:
            tool_result = f"User denied permission to execute '{tool_name}'."
            yield f"data: {json.dumps({'type': 'tool_denied', 'tool_name': tool_name})}\n\n"

        if approved:
            code_snippet = arguments.get("code", "")
            # Determine language for fenced block label
            lang_label = "python" if tool_name == "execute_python" else (
                "fortran" if tool_name == "execute_fortran" else "text"
            )
            ollama_messages.append({
                "role":    "user",
                "content": (
                    f"Tool execution complete. Here is exactly what ran and what it returned.\n\n"
                    f"**Code executed:**\n"
                    f"```{lang_label}\n{code_snippet}\n```\n\n"
                    f"**Output:**\n"
                    f"```\n{tool_result}\n```\n\n"
                    f"Summarise what the code did and confirm the result. "
                    f"Keep the code and output fenced blocks exactly as shown above in your response."
                ),
            })
        else:
            ollama_messages.append({
                "role":    "user",
                "content": f"The user denied permission to run `{tool_name}`. Acknowledge this and ask how they would like to proceed.",
            })

        # ── Re-enter ReAct loop ───────────────────────────────────────────────
        web_search_master_on = get_setting("web_search_enabled", "false").lower() == "true"
        tools = get_tool_schemas(
            include_search = web_search_master_on,
            include_write  = True,
            project_active = bool(project_id and project),
        )

        full_response_parts = []
        loop_gen = _react_loop(
            ollama_messages   = ollama_messages,
            model             = model,
            tools             = tools,
            session_id        = session_id,
            project           = project,
            web_search_active = False,  # don't auto-fire search on resume
            think             = think,
        )

        result = None
        for item in loop_gen:
            if isinstance(item, str):
                yield item
            elif isinstance(item, tuple):
                result = item

        if result is not None:
            final_text, paused = result
            if final_text is not None:
                complete_text = "".join(final_text)
                if complete_text:
                    saved = add_message(session_id, "assistant", complete_text)
                    yield f"data: {json.dumps({'type': 'done', 'message_id': saved['id']})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )

# ── Context window usage endpoint (P3) ────────────────────────────────────────

@chat_blueprint.route("/api/chat/context_usage", methods=["GET"])
def context_usage():
    """
    Token usage estimate for the current session vs the model's hardware ceiling.

    Query params:
      session_id  int   required
      model       str   optional; defaults to LLM_MODEL from configuration

    Returns JSON:
      tokens_used   int     estimated tokens consumed by session so far
      ceiling       int     hardware-derived context window ceiling for this model
      percent       float   usage percentage (0-100)
      model         str     model name used for ceiling lookup
      warning       bool    true when percent >= 80
    """
    from lincoln.lincoln_ollama_service import resolve_hardware_ceiling

    session_id = request.args.get("session_id", type=int)
    model      = (request.args.get("model") or "").strip() or LLM_MODEL

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    try:
        messages    = get_session_messages(session_id)
        # Estimate: chars / 4 tokens per char, +10% for role/formatting overhead
        total_chars = sum(len(m.get("content", "")) for m in messages)
        tokens_used = int((total_chars / 4) * 1.10)
        ceiling     = resolve_hardware_ceiling(model)
        percent     = round((tokens_used / ceiling) * 100, 1) if ceiling > 0 else 0.0

        return jsonify({
            "tokens_used": tokens_used,
            "ceiling":     ceiling,
            "percent":     percent,
            "model":       model,
            "warning":     percent >= 80.0,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500