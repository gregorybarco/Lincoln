"""
Lincoln Ollama Service  v0.6.0
================================
Single owner of all communication with the local Ollama server.

Changes in v0.6.0:
  - System prompt assembled from DB (lincoln_database.get_active_system_prompt)
    instead of hardcoded string. Fully editable from the Settings UI.
  - Ollama timeout read from DB setting 'ollama_timeout_sec' at call time.
  - OLLAMA_VRAM_GB fix: uses _optional() in configuration, not direct os.getenv.
  - build_messages_with_rag_context() accepts pre-built system prompt string.
"""

import json
from typing import Generator

import requests

from lincoln.lincoln_configuration import OLLAMA_BASE_URL, OLLAMA_VRAM_GB


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

    window = 2048
    while window < estimated_tokens:
        window *= 2

    final = min(window, hardware_max)
    print(
        f"[Lincoln] num_ctx -- estimated={estimated_tokens} tokens "
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
