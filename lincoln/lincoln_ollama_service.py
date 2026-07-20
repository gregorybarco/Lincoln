"""
Lincoln Ollama Service
======================
Single owner of all communication with the local Ollama server.

Owns:
  - Sending chat messages to Qwen (or any model loaded in Ollama)
  - Streaming token-by-token responses to the Flask UI via Server-Sent Events
  - Fetching the list of available models from Ollama for the UI model selector
  - Health checking the Ollama connection
  - Context window sizing: per-request num_ctx derived dynamically from payload size
    and the model's native context limit.

Rules:
  - No route or other service calls the Ollama API directly.
    All Ollama communication flows through this module.
  - The model used for each request is passed in as a parameter —
    this service never assumes a default model internally.
    The caller is responsible for resolving which model to use.
  - num_ctx is never hardcoded. resolve_num_ctx_for_request() is called
    on every chat request and adapts to actual payload size up to native limits.

Used by:
  - lincoln\\app\\routes\\lincoln_routes_chat.py    (streaming chat responses)
  - lincoln\\app\\routes\\lincoln_routes_models.py  (model selector population)
"""

import json
import re
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
    """Return True if this model supports chain-of-thought thinking mode."""
    return any(p in model.lower() for p in _THINKING_MODEL_PATTERNS)


# ── Model discovery ───────────────────────────────────────────────────────────

def get_available_models() -> list[dict]:
    """
    Fetch all models currently loaded in Ollama.
    Used by the UI model selector — populates the dropdown dynamically
    so any model pulled into Ollama appears automatically without config changes.

    Returns:
        List of dicts with keys: name, size, modified_at
        Returns empty list if Ollama is unreachable.
    """
    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5,
        )
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
    """
    Check whether the Ollama server is reachable and responding.

    Returns:
        dict with keys:
          status  : 'ok' | 'unreachable'
          url     : the Ollama base URL being checked
          message : human-readable status description
    """
    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5,
        )
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

_ctx_cache:    dict[str, int] = {}  # model → hardware ceiling (cached per process)
_native_cache: dict[str, int] = {}  # model → model's own native context limit


def _fetch_model_info(model: str) -> dict:
    """
    Call Ollama /api/show and return the raw response dict.
    Returns empty dict on any failure — callers handle absence gracefully.
    """
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
    """
    Extract the model's own declared context window from /api/show response.

    Checks two locations:
      1. modelfile PARAMETER block  — "PARAMETER num_ctx <value>"
      2. model_info dict            — any key containing "context_length" (Ollama ≥0.3)

    Returns 131072 (128k) if neither source has it as a generous modern default.
    """
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

    return 131072  # Assume large 128k limit for modern models


def _estimate_tokens(messages: list[dict]) -> int:
    """
    Estimate the token count of a message list before sending to Ollama.
    """
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return int((total_chars / 4) * 1.10)


def resolve_hardware_ceiling(model: str) -> int:
    """
    Return the maximum native num_ctx for this model.
    Result is cached per process — /api/show is only called once per model.
    """
    if model in _ctx_cache:
        return _ctx_cache[model]

    info           = _fetch_model_info(model)
    native_ctx     = _parse_native_ctx(info)

    # Trust the model's native capabilities and let Ollama handle VRAM offloading dynamically
    hardware_max   = native_ctx

    _ctx_cache[model]    = hardware_max
    _native_cache[model] = native_ctx

    print(
        f"[Lincoln] ctx ceiling — model={model} "
        f"native={native_ctx} "
        f"→ hardware_max={hardware_max}"
    )
    return hardware_max


def resolve_num_ctx_for_request(model: str, messages: list[dict]) -> int:
    """
    Return the num_ctx to use for this specific request.
    """
    hardware_max     = resolve_hardware_ceiling(model)
    estimated_tokens = _estimate_tokens(messages)

    if estimated_tokens > hardware_max:
        print(
            f"[Lincoln] WARNING: payload exceeds model's native context — "
            f"estimated={estimated_tokens} tokens "
            f"model_max={hardware_max} tokens "
            f"model={model}. "
            f"Oldest history will be truncated by Ollama."
        )
        return hardware_max

    # Round up to next power of two
    window = 2048
    while window < estimated_tokens:
        window *= 2

    final = min(window, hardware_max)
    print(
        f"[Lincoln] num_ctx — estimated={estimated_tokens} tokens "
        f"→ window={final} (ceiling={hardware_max})"
    )
    return final


# ── Chat — single response ────────────────────────────────────────────────────

def chat(
    messages:    list[dict],
    model:       str,
    temperature: float = 0.7,
    timeout:     int   = 180,
    think:       bool  = False,
) -> str:
    """
    Send a conversation to Ollama and return the complete response text.
    """
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

    data = response.json()
    content = data.get("message", {}).get("content", "")

    if not content:
        raise ValueError(
            f"Ollama returned an empty response for model '{model}'. "
            f"Full response: {data}"
        )

    return content


# ── Chat — streaming ──────────────────────────────────────────────────────────

def stream_chat(
    messages:    list[dict],
    model:       str,
    temperature: float = 0.7,
    timeout:     int   = 180,
    think:       bool  = False,
) -> Generator[str, None, None]:
    """
    Stream a conversation response from Ollama token by token.
    """
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
    project_name:    str = "",
) -> list[dict]:
    """
    Build a full message list for Ollama combining session history,
    RAG-retrieved context, and the current user question.
    """
    system_content = (
        f"You are Lincoln, a local AI assistant. "
        f"{'You have deep knowledge of the ' + project_name + ' codebase. ' if project_name else ''}"
        f"You help with coding, analysis, and reasoning. "
        f"You never modify files without explicit approval. "
        f"You are running fully locally — no data leaves this machine.\n\n"
        f"Formatting rules: respond conversationally for questions and explanations. "
        f"Use markdown sparingly — only use code blocks for actual code, "
        f"bullet points only for genuine lists, headers only for long structured documents. "
        f"Do NOT bold every other phrase or use emojis in technical responses.\n\n"
    )

    if rag_context:
        system_content += (
            f"The following context was retrieved from the {project_name} "
            f"codebase index and is relevant to the user's question:\n\n"
            f"{rag_context}\n\n"
            f"Use this context to ground your answer in the actual code."
        )

    messages = [{"role": "system", "content": system_content}]
    messages.extend(session_history)
    messages.append({"role": "user", "content": user_question})

    return messages