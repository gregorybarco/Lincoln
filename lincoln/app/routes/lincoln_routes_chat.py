"""
Lincoln Chat Routes  v0.6.0
=============================
Flask routes for the chat interface.

Changes in v0.6.0:
  - System prompt assembled from DB via get_active_system_prompt() -- not hardcoded.
  - use_web_search flag: when true, DuckDuckGo results are injected into system prompt
    before the Ollama streaming call. Fixes B3/B7 (search command was broken).
  - display_text and LLM injection text properly separated for file attachments.
  - Ban list check on generated code for OptionsPricing-flagged projects (optional,
    result appended to SSE stream as 'ban_check' event type).

Endpoints:
  POST /api/chat/session      Create a new session
  GET  /api/chat/session/<id> Get all messages for a session
  POST /api/chat/send         Send a message and stream response via SSE
"""

import json
from pathlib import Path

from flask import Blueprint, Response, request, jsonify, stream_with_context

from lincoln.lincoln_database import (
    add_message,
    create_session,
    get_project_by_id,
    get_session_messages,
    rename_session,
    get_active_system_prompt,
    get_setting,
)
from lincoln.lincoln_ollama_service import (
    build_messages_with_rag_context,
    stream_chat,
)
from lincoln.lincoln_rag_index_service import query_project_index
from lincoln.lincoln_configuration import DEFAULT_TOP_K, LLM_MODEL, DB_PATH

chat_blueprint = Blueprint("chat", __name__)

_UPLOAD_DIR = DB_PATH.parent / "uploads"


@chat_blueprint.route("/api/chat/session", methods=["POST"])
def create_new_session():
    """
    Create a new chat session only when explicitly requested by the UI.
    The UI calls this only when the user clicks 'New chat' -- not on every page load.
    """
    data       = request.get_json() or {}
    project_id = data.get("project_id")
    session    = create_session(title="New chat", project_id=project_id)
    return jsonify(session)


@chat_blueprint.route("/api/chat/session/<int:session_id>", methods=["GET"])
def get_session(session_id: int):
    messages = get_session_messages(session_id)
    return jsonify(messages)


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
      use_web_search  : bool   -- if true, inject DuckDuckGo results before streaming
      file_id         : str | null
      think_mode      : 'fast' | 'normal' | 'deep'
    """
    data           = request.get_json() or {}
    session_id     = data.get("session_id")
    user_text      = data.get("message", "").strip()
    model          = data.get("model", LLM_MODEL)
    project_id     = data.get("project_id")
    use_rag        = data.get("use_rag", True)
    use_web_search = data.get("use_web_search", False)
    file_id        = data.get("file_id")
    think_mode     = data.get("think_mode", "normal")
    think          = (think_mode == "deep")

    if not session_id or not user_text:
        return jsonify({"error": "session_id and message are required"}), 400

    # ── Inject uploaded file content into LLM payload ─────────────────────────
    injected_filename = None
    llm_text          = user_text   # text sent to Ollama (may include file blob)
    display_text      = user_text   # text saved to DB and shown in UI

    if file_id:
        safe_id = "".join(c for c in file_id if c in "0123456789abcdef")
        # v0.6.0: all extracted content stored as .txt
        txt_path = _UPLOAD_DIR / f"{safe_id}.txt"
        matches  = [txt_path] if txt_path.exists() else list(_UPLOAD_DIR.glob(f"{safe_id}.*"))

        if matches:
            try:
                file_text         = matches[0].read_text(encoding="utf-8")
                injected_filename = matches[0].stem  # filename without .txt extension
                llm_text = (
                    f"[Attached file: {injected_filename}]\n"
                    f"```\n{file_text}\n```\n\n"
                    f"{user_text}"
                )
            except Exception:
                pass  # File read failed -- send without attachment

    # Save user message with display text (attachment icon + question, no blob)
    if injected_filename:
        display_text = f"📎 {injected_filename}\n\n{user_text}"

    add_message(session_id, "user", display_text)

    # Auto-rename session from first user message
    messages_so_far = get_session_messages(session_id)
    if len(messages_so_far) == 1:
        title = display_text[:50] + ("..." if len(display_text) > 50 else "")
        rename_session(session_id, title)

    def generate():
        sources      = []
        rag_context  = ""
        project_name = ""

        # Tell UI which think mode is active
        yield f"data: {json.dumps({'type': 'think_mode', 'mode': think_mode})}\n\n"

        # ── Assemble system prompt from DB ────────────────────────────────────
        system_prompt = get_active_system_prompt(project_id=project_id)

        # ── Web search injection ──────────────────────────────────────────────
        if use_web_search:
            try:
                from lincoln.lincoln_web_search import search, format_search_results_for_context
                search_results = search(user_text, max_results=5)
                if search_results:
                    formatted = format_search_results_for_context(search_results)
                    system_prompt += (
                        "\n\n---\n\n"
                        "The following web search results were retrieved for this query. "
                        "Use them to ground your answer in current information:\n\n"
                        + formatted
                    )
                    yield f"data: {json.dumps({'type': 'web_search', 'result_count': len(search_results)})}\n\n"
            except Exception as search_err:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Web search failed: {str(search_err)}'})}\n\n"

        # ── RAG context injection ─────────────────────────────────────────────
        if project_id and use_rag:
            try:
                project = get_project_by_id(project_id)
                if project and project.get("vector_count", 0) > 0:
                    project_name = project["display_name"]
                    top_k        = int(get_setting("top_k", str(DEFAULT_TOP_K)))
                    result       = query_project_index(
                        question     = user_text,
                        collection   = project["collection"],
                        project_name = project_name,
                        top_k        = top_k,
                    )
                    rag_context = result["answer"]
                    sources     = result["sources"]
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
            except Exception as rag_error:
                yield f"data: {json.dumps({'type': 'error', 'message': f'RAG error: {str(rag_error)}'})}\n\n"

        # ── Build Ollama message list ─────────────────────────────────────────
        history = get_session_messages(session_id)
        ollama_messages = build_messages_with_rag_context(
            user_question   = llm_text,
            rag_context     = rag_context,
            session_history = [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m["role"] != "system"
            ],
            system_prompt = system_prompt,
            project_name  = project_name,
        )

        # ── Stream response ───────────────────────────────────────────────────
        full_response = []
        try:
            for token in stream_chat(messages=ollama_messages, model=model, think=think):
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as stream_error:
            yield f"data: {json.dumps({'type': 'error', 'message': str(stream_error)})}\n\n"
            return

        complete_text = "".join(full_response)
        saved_message = add_message(session_id, "assistant", complete_text)

        # ── Optional ban list check (OptionsPricing projects) ─────────────────
        # Only runs if the response contains a code block and project is flagged
        if "```" in complete_text and project_id:
            try:
                from lincoln.lincoln_ban_list_checker import check_against_ban_list, format_violations_for_ui
                violations = check_against_ban_list(complete_text)
                if violations:
                    yield f"data: {json.dumps({'type': 'ban_check', 'violations': format_violations_for_ui(violations)})}\n\n"
            except Exception:
                pass  # Ban check failure never blocks the response

        yield f"data: {json.dumps({'type': 'done', 'message_id': saved_message['id']})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )
