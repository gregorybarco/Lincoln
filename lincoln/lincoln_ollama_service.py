"""
Lincoln Ollama Service  v0.7.0
================================
Single owner of all communication with the local Ollama server.

Changes in v0.7.0:
  - num_predict now set to -1 (unlimited) on every request.
    Previously unset, causing Ollama to silently truncate responses at ~128
    tokens on some model/version combos. This was the primary cause of Lincoln
    being "neutered" -- code responses cut off mid-function, explanations
    ending abruptly. Fixed permanently: -1 means the model runs until done.
  - build_messages_with_rag_context() injects a TOOL_MANIFEST block when
    the system prompt does not already contain one. This tells the LLM what
    tools Lincoln has (OCR, web search, Jupyter, Fortran/WSL, Maple, Aider)
    so it never says "I don't have access to that tool." The manifest is
    assembled from DB settings at call time so it reflects what is actually
    installed on this machine.
  - resolve_num_ctx_for_request() now pads the computed window by 20%
    (RESPONSE_HEADROOM) to reserve tokens for the model's output. Previously
    the window was sized to fit the input, leaving no headroom for a long
    code response.

Changes in v0.6.0:
  - System prompt assembled from DB (lincoln_database.get_active_system_prompt)
    instead of hardcoded string. Fully editable from the Settings UI.
  - Ollama timeout read from DB setting 'ollama_timeout_sec' at call time.
  - OLLAMA_VRAM_GB fix: uses _optional() in configuration, not direct os.getenv.
  - build_messages_with_rag_context() accepts pre-built system prompt string.
"""

import json
from pathlib import Path
from typing import Generator

import requests

from lincoln.lincoln_configuration import OLLAMA_BASE_URL, OLLAMA_VRAM_GB

# Reserve this fraction of the context window for the model's output.
# Without headroom, a window sized to fit the input leaves no room for a
# long code response, causing silent mid-stream truncation.
_RESPONSE_HEADROOM = 0.20  # 20% of window reserved for output


# ── Thinking-mode detection ───────────────────────────────────────────────────

_THINKING_MODEL_PATTERNS = (
    "qwen3",
    "qwq",
    "deepseek-r",
    "phi4-reasoning",
)


def _is_thinking_model(model: str) -> bool:
    return any(p in model.lower() for p in _THINKING_MODEL_PATTERNS)


# ── Model discovery ───────────────────────────────────────────────────────────

def get_available_models() -> list[dict]:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        data   = response.json()
        models = data.get("models", [])
        return [
            {
                "name":        m.get("name", ""),
                "size":        m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
            }
            for m in models
        ]
    except Exception:
        return []


# ── Health check ──────────────────────────────────────────────────────────────

def check_ollama_health() -> dict:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        return {
            "status":  "ok",
            "url":     OLLAMA_BASE_URL,
            "message": "Ollama is running and reachable.",
        }
    except requests.exceptions.ConnectionError:
        return {
            "status":  "unreachable",
            "url":     OLLAMA_BASE_URL,
            "message": f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Is Ollama running?",
        }
    except Exception as e:
        return {
            "status":  "unreachable",
            "url":     OLLAMA_BASE_URL,
            "message": str(e),
        }


# ── Context window detection ──────────────────────────────────────────────────

_ctx_cache:    dict[str, int] = {}
_native_cache: dict[str, int] = {}


def _fetch_model_info(model: str) -> dict:
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/show",
            json={"model": model},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return {}


def _parse_native_ctx(info: dict) -> int:
    modelfile = info.get("modelfile", "")
    for line in modelfile.splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0].upper() == "PARAMETER" and parts[1] == "num_ctx":
            try:
                return int(parts[2])
            except ValueError:
                pass

    model_info = info.get("model_info", {})
    for key, val in model_info.items():
        if "context_length" in key and isinstance(val, int):
            return val

    return 131072


def _estimate_tokens(messages: list[dict]) -> int:
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return int((total_chars / 4) * 1.10)


def resolve_hardware_ceiling(model: str) -> int:
    if model in _ctx_cache:
        return _ctx_cache[model]

    info       = _fetch_model_info(model)
    native_ctx = _parse_native_ctx(info)

    _ctx_cache[model]    = native_ctx
    _native_cache[model] = native_ctx

    print(
        f"[Lincoln] ctx ceiling -- model={model} "
        f"native={native_ctx} -> hardware_max={native_ctx}"
    )
    return native_ctx


def resolve_num_ctx_for_request(model: str, messages: list[dict]) -> int:
    """
    Compute num_ctx for this request.

    Sizes the window to comfortably fit the input PLUS a 20% headroom
    reserve for the model's output. Without headroom, the window is packed
    with input tokens and leaves the model almost no room to write a long
    code response before Ollama cuts the stream.

    The final value is always a power of two capped at the model's native
    context ceiling.
    """
    hardware_max     = resolve_hardware_ceiling(model)
    estimated_tokens = _estimate_tokens(messages)

    if estimated_tokens > hardware_max:
        print(
            f"[Lincoln] WARNING: payload exceeds model native context -- "
            f"estimated={estimated_tokens} tokens "
            f"model_max={hardware_max} tokens "
            f"model={model}. Oldest history will be truncated by Ollama."
        )
        return hardware_max

    # Add headroom so the output has room to breathe
    tokens_with_headroom = int(estimated_tokens / (1.0 - _RESPONSE_HEADROOM))

    window = 2048
    while window < tokens_with_headroom:
        window *= 2

    final = min(window, hardware_max)
    print(
        f"[Lincoln] num_ctx -- input_est={estimated_tokens} "
        f"+ headroom -> need={tokens_with_headroom} "
        f"-> window={final} (ceiling={hardware_max})"
    )
    return final


def _get_timeout() -> int:
    """Read ollama_timeout_sec from DB settings at call time."""
    try:
        from lincoln.lincoln_database import get_setting
        return int(get_setting("ollama_timeout_sec", "180"))
    except Exception:
        return 180


# ── Chat -- single response ───────────────────────────────────────────────────

def chat(
    messages:    list[dict],
    model:       str,
    temperature: float = 0.7,
    timeout:     int | None = None,
    think:       bool = False,
) -> str:
    if timeout is None:
        timeout = _get_timeout()

    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {
            "temperature": temperature,
            "num_ctx":     resolve_num_ctx_for_request(model, messages),
            # -1 = unlimited output tokens.
            # Without this, Ollama may default to 128 tokens on some builds,
            # silently cutting off code responses mid-function.
            "num_predict": -1,
        },
    }

    if _is_thinking_model(model):
        payload["think"] = think
        print(f"[Lincoln] thinking={'on' if think else 'off'} for {model}")

    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    data    = response.json()
    content = data.get("message", {}).get("content", "")

    if not content:
        raise ValueError(
            f"Ollama returned an empty response for model '{model}'. "
            f"Full response: {data}"
        )

    return content


# ── Chat -- streaming ─────────────────────────────────────────────────────────

def stream_chat(
    messages:    list[dict],
    model:       str,
    temperature: float = 0.7,
    timeout:     int | None = None,
    think:       bool = False,
) -> Generator[str, None, None]:
    if timeout is None:
        timeout = _get_timeout()

    payload = {
        "model":    model,
        "messages": messages,
        "stream":   True,
        "options":  {
            "temperature": temperature,
            "num_ctx":     resolve_num_ctx_for_request(model, messages),
            # -1 = unlimited output tokens. Prevents silent mid-stream cutoff.
            "num_predict": -1,
        },
    }

    if _is_thinking_model(model):
        payload["think"] = think
        print(f"[Lincoln] thinking={'on' if think else 'off'} for {model}")

    in_think_block = False

    with requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        stream=True,
        timeout=timeout,
    ) as response:
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))

                if think:
                    thinking_token = chunk.get("thinking", "")
                    if thinking_token:
                        if not in_think_block:
                            in_think_block = True
                            yield "THINK_START"
                        yield thinking_token

                    response_token = chunk.get("message", {}).get("content", "")
                    if response_token:
                        if in_think_block:
                            in_think_block = False
                            yield "THINK_END"
                        yield response_token
                else:
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token

                if chunk.get("done", False):
                    if in_think_block:
                        yield "THINK_END"
                    break

            except (json.JSONDecodeError, UnicodeDecodeError):
                continue


# ── Tool manifest ─────────────────────────────────────────────────────────────

def _build_tool_manifest() -> str:
    """
    Assemble a plain-text description of Lincoln's available tools.

    This is injected into the system prompt so the LLM always knows what
    capabilities are available on this machine. Without it, the LLM may
    say "I don't have access to that tool" even when the tool is installed
    and fully wired.

    Reads DB settings to reflect what is actually configured (e.g. whether
    Maple is installed, which WSL distro, which nvfortran path).
    """
    try:
        from lincoln.lincoln_database import get_setting
        wsl_distro    = get_setting("wsl_distro",    "Ubuntu")
        nvfortran     = get_setting("nvfortran_path", "nvfortran")
        maple_path    = get_setting("maple_path",     "")
        oneapi_path   = get_setting("oneapi_path",    "")
        web_enabled   = get_setting("web_search_enabled", "false")
    except Exception:
        wsl_distro  = "Ubuntu"
        nvfortran   = "nvfortran"
        maple_path  = ""
        oneapi_path = ""
        web_enabled = "false"

    maple_line = (
        f"- **Maple** (cmaple): Available at {maple_path}. "
        "You can generate Maple code and it will be executed via the canvas Run button."
        if maple_path else
        "- **Maple**: Not configured (set maple_path in Settings > Build Tools)."
    )

    oneapi_line = (
        f"- **Intel oneAPI / ifort**: Available at {oneapi_path}. "
        "Use for Intel Fortran compilation via WSL."
        if oneapi_path else
        "- **Intel oneAPI**: Not configured."
    )

    web_line = (
        "- **Web search** (DuckDuckGo): Active for this message. "
        "Results are injected into your context automatically."
        if web_enabled == "true" else
        "- **Web search**: Available per-message via the globe pill in the input bar."
    )

    # Find Lincoln's own source directory for self-awareness
    try:
        source_dir = str(Path(__file__).parent.resolve())
    except Exception:
        source_dir = "B:\\Homebrewed_AI\\Lincoln\\lincoln\\"

    return f"""
--- LINCOLN TOOL MANIFEST ---
You are Lincoln, a local AI assistant running on this machine. You have access
to the following tools and capabilities. NEVER tell the user you lack access
to a tool listed here -- you have it. If a tool is not listed, say so honestly.

EXECUTION TOOLS (via Canvas Run button):
- **Python / Jupyter**: Full Python kernel. numpy, pandas, scipy, matplotlib,
  openpyxl, python-docx, Pillow, requests, and all pip-installed packages are
  available. Canvas Run button launches Jupyter execution.
- **Fortran (nvfortran)**: NVIDIA HPC SDK compiler at {nvfortran}.
  Available via WSL ({wsl_distro}). Canvas shows run hint for Fortran blocks.
- **C / C++**: gcc/g++ available in WSL ({wsl_distro}). Canvas Run copies
  compile+run command.
- **Julia / R / Bash**: Available via WSL ({wsl_distro}). Canvas Run copies
  the execution command.
{maple_line}
{oneapi_line}

FILE & DOCUMENT TOOLS:
- **OCR** (Tesseract): Installed in WSL. Reads text from images, Bloomberg
  screenshots, scanned PDFs. Languages: English, Russian, Hindi, Urdu, Punjabi,
  Bangla, Arabic. Attach an image and ask Lincoln to read it.
- **Vision model**: Uses the active Ollama model for 3D chart / vol surface
  interpretation where OCR cannot read structured visuals.
- **Document parsing**: .docx (python-docx), .xlsx (openpyxl), .pdf
  (pdfplumber/pypdf), .csv (pandas). Attach any of these and Lincoln reads them.
- **Multi-file upload**: Use the paperclip icon to attach multiple files.

KNOWLEDGE & SEARCH TOOLS:
{web_line}
- **RAG (project index)**: When a project is active, Lincoln retrieves relevant
  chunks from the indexed codebase via ChromaDB. Sources shown below each response.
- **Memory**: Session summaries are saved to memory and injected at the start
  of the next session via the context strip.

CODE TOOLS:
- **Aider** (suggestion mode): Proposes file edits to the codebase in the active
  project's code folder. User reviews and approves all changes. Never auto-commits.
- **Git** (read-only): Lincoln can read git status, log, and diff from the
  project's code folder via the Canvas > Diff tab.
- **Self-inspection**: Lincoln's own source code is at {source_dir}.
  If asked to debug Lincoln itself, you can reference your own implementation
  by asking the user to activate the Lincoln source as a RAG project, or by
  reading specific files via the file attach feature.

HARDWARE (this machine):
- CPU: Intel i7-10700
- GPU: NVIDIA RTX 5060 Ti 16GB (Blackwell, CUDA + WDDM)
- RAM: ~30GB usable
- Ollama runs locally at localhost:11434. All inference is local. No data leaves
  this machine.
--- END TOOL MANIFEST ---
""".strip()


# ── Context builder ───────────────────────────────────────────────────────────

def build_messages_with_rag_context(
    user_question:   str,
    rag_context:     str,
    session_history: list[dict],
    system_prompt:   str = "",
    project_name:    str = "",
) -> list[dict]:
    """
    Build a full message list for Ollama.
    The system_prompt is now passed in (assembled from DB by the caller)
    rather than being hardcoded here. Nothing is hardcoded in this function.

    v0.7.0: A TOOL_MANIFEST block is appended to the system prompt if the
    string "LINCOLN TOOL MANIFEST" is not already present. This ensures the
    LLM always knows what tools are available without requiring the user to
    add a prompt block manually.

    Args:
        user_question   : The user's current message (may include file blob)
        rag_context     : Retrieved RAG chunks (empty string if no project active)
        session_history : Prior messages in this session (role/content dicts)
        system_prompt   : Full assembled system prompt from DB (global + project blocks)
        project_name    : Display name of the active project (for RAG context header)
    """
    # If no system prompt was provided (should not happen in normal flow),
    # use a minimal fallback so behaviour is never undefined.
    if not system_prompt:
        system_prompt = "You are Lincoln, a local AI assistant."

    system_content = system_prompt

    # Inject tool manifest if not already present
    if "LINCOLN TOOL MANIFEST" not in system_content:
        system_content += "\n\n" + _build_tool_manifest()

    if rag_context:
        project_label = project_name or "the active project"
        system_content += (
            f"\n\n---\n\n"
            f"The following context was retrieved from the {project_label} "
            f"codebase index and is relevant to the user's question:\n\n"
            f"{rag_context}\n\n"
            f"Use this context to ground your answer in the actual code."
        )

    messages = [{"role": "system", "content": system_content}]
    messages.extend(session_history)
    messages.append({"role": "user", "content": user_question})

    return messages

"""
lincoln_ollama_service.py  — v0.7.0 ADDITIONS ONLY
====================================================
Append this entire block to the bottom of your existing
lincoln_ollama_service.py. All existing functions remain unchanged.

This adds stream_chat_with_tools() — the native tool-calling variant of
stream_chat(). It yields structured dicts instead of raw strings so the
ReAct loop in lincoln_routes_chat.py can detect and handle tool calls.

The existing stream_chat() is kept untouched for all non-agent code paths
(e.g. canvas execution, direct LLM calls from other services).
"""

from typing import Generator


# ── Streamed event types from stream_chat_with_tools() ───────────────────────
#
#  {"type": "token",     "content": str}
#      Normal text token from the LLM. Accumulate these for the final response.
#
#  {"type": "think",     "content": str}
#      Thinking/reasoning token (qwen3 only, when think=True).
#
#  {"type": "think_end"}
#      Reasoning block complete, main response beginning.
#
#  {"type": "tool_call", "tool_name": str, "tool_call_id": str, "arguments": dict}
#      LLM has requested a tool. ReAct loop must handle this.
#      After this event the stream ends — Ollama sets done=True.
#
#  {"type": "done"}
#      Stream complete, no tool call was made.
#
#  {"type": "error",     "message": str}
#      Something went wrong.


def stream_chat_with_tools(
    messages:    list[dict],
    model:       str,
    tools:       list[dict] | None = None,
    temperature: float = 0.7,
    timeout:     int | None = None,
    think:       bool = False,
) -> Generator[dict, None, None]:
    """
    Stream a chat response from Ollama with native tool-calling support.

    Unlike stream_chat() which yields raw strings, this yields structured
    event dicts so the ReAct loop can detect tool calls and route them
    through the approval gate.

    Args:
        messages    : Full message list including system prompt and history.
        model       : Ollama model name.
        tools       : List of Ollama-compatible tool schema dicts.
                      Pass [] or None to disable tool calling entirely.
        temperature : Sampling temperature.
        timeout     : Request timeout in seconds (reads from DB if None).
        think       : Enable chain-of-thought reasoning (qwen3 models only).

    Yields:
        Structured event dicts (see event types above).
    """
    import json as _json
    import requests as _requests

    if timeout is None:
        timeout = _get_timeout()

    payload: dict = {
        "model":    model,
        "messages": messages,
        "stream":   True,
        "options":  {
            "temperature": temperature,
            "num_ctx":     resolve_num_ctx_for_request(model, messages),
            "num_predict": -1,
        },
    }

    if tools:
        payload["tools"] = tools

    if _is_thinking_model(model):
        payload["think"] = think

    # Ollama streams tool calls differently from text responses.
    # When the model decides to call a tool:
    #   - chunk["message"]["tool_calls"] is populated
    #   - chunk["message"]["content"] may be empty or contain preamble text
    #   - chunk["done"] is True on the final chunk
    #
    # We accumulate tool_calls across chunks (some models split them)
    # and yield a single tool_call event when done=True.

    accumulated_tool_calls: list[dict] = []
    in_think_block = False

    try:
        with _requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=timeout,
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = _json.loads(line.decode("utf-8"))
                except (_json.JSONDecodeError, UnicodeDecodeError):
                    continue

                message = chunk.get("message", {})

                # ── Thinking tokens (qwen3 reasoning mode) ────────────────
                if think:
                    thinking_token = chunk.get("thinking", "")
                    if thinking_token:
                        if not in_think_block:
                            in_think_block = True
                        yield {"type": "think", "content": thinking_token}

                    if in_think_block and message.get("content"):
                        in_think_block = False
                        yield {"type": "think_end"}

                # ── Tool call chunks ──────────────────────────────────────
                tool_calls_in_chunk = message.get("tool_calls", [])
                if tool_calls_in_chunk:
                    accumulated_tool_calls.extend(tool_calls_in_chunk)

                # ── Text content tokens ───────────────────────────────────
                token = message.get("content", "")
                if token and not tool_calls_in_chunk:
                    # Only yield text tokens if this chunk is NOT a tool call.
                    # Some models emit preamble text before the tool call —
                    # we stream that normally.
                    yield {"type": "token", "content": token}

                # ── Stream complete ───────────────────────────────────────
                if chunk.get("done", False):
                    if in_think_block:
                        yield {"type": "think_end"}

                    if accumulated_tool_calls:
                        # Yield one tool_call event per requested tool.
                        # In practice Qwen/Gemma request one tool at a time.
                        for tc in accumulated_tool_calls:
                            func      = tc.get("function", {})
                            tool_name = func.get("name", "")
                            raw_args  = func.get("arguments", {})

                            # arguments may arrive as a JSON string or dict
                            if isinstance(raw_args, str):
                                try:
                                    raw_args = _json.loads(raw_args)
                                except _json.JSONDecodeError:
                                    raw_args = {"raw": raw_args}

                            yield {
                                "type":         "tool_call",
                                "tool_name":    tool_name,
                                "tool_call_id": tc.get("id", f"tc_{tool_name}"),
                                "arguments":    raw_args,
                            }
                    else:
                        yield {"type": "done"}
                    break

    except Exception as e:
        yield {"type": "error", "message": str(e)}


