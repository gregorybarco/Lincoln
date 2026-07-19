"""
Lincoln Ollama Service
======================
Single owner of all communication with the local Ollama server.

Owns:
  - Sending chat messages to Qwen (or any model loaded in Ollama)
  - Streaming token-by-token responses to the Flask UI via Server-Sent Events
  - Fetching the list of available models from Ollama for the UI model selector
  - Health checking the Ollama connection
  - Context window sizing: per-request num_ctx derived from payload size,
    model parameter count, and available VRAM — never a fixed global cap.

Rules:
  - No route or other service calls the Ollama API directly.
    All Ollama communication flows through this module.
  - The model used for each request is passed in as a parameter —
    this service never assumes a default model internally.
    The caller is responsible for resolving which model to use.
  - num_ctx is never hardcoded. resolve_num_ctx_for_request() is called
    on every chat request and adapts to actual payload size.

Used by:
  - lincoln\app\routes\lincoln_routes_chat.py    (streaming chat responses)
  - lincoln\app\routes\lincoln_routes_models.py  (model selector population)
"""

import json
import re
from typing import Generator

import requests

from lincoln.lincoln_configuration import OLLAMA_BASE_URL, OLLAMA_VRAM_GB


# ── Thinking-mode detection ───────────────────────────────────────────────────
#
# Qwen3 and similar reasoning models generate a silent <think>...</think> block
# before producing any visible output.  This can add minutes of blank-screen
# latency for conversational queries that don't benefit from chain-of-thought.
#
# The `think` parameter is threaded through chat() and stream_chat() so the
# caller controls it per-request.  The UI exposes three modes:
#   fast   → think=False   (suppress entirely — fastest)
#   normal → think=False   (same, default for general chat)
#   deep   → think=True    (full reasoning — UI shows collapsible block)
#
# Ollama API: pass "think": <bool> as a top-level payload key (not in options).
# Reference: https://ollama.com/blog/thinking-llms

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
#
# Design intent:
#   - Maximum coverage always: num_ctx is set per-request to exactly what the
#     payload needs, never a fixed global cap.
#   - VRAM-safe always: the ceiling is derived from available VRAM minus model
#     weight footprint, so we never allocate KV cache that doesn't fit.
#   - Warn loudly: if a payload would exceed the hardware ceiling, Lincoln logs
#     a clear warning with token counts before sending — no silent truncation.
#   - Zero user input: everything is derived from Ollama /api/show + VRAM config.
#
# KV cache cost model (conservative estimates per token, all layers, K+V):
#   ~7B  param model @ Q4  → ~0.50 MB/token
#   ~9B  param model @ Q4  → ~0.55 MB/token
#   ~12B param model @ Q4  → ~0.70 MB/token
#   ~27B param model @ Q4  → ~1.20 MB/token
#
# Weight footprint estimates (Q4):
#   ~7B  → ~4.5 GB
#   ~9B  → ~5.5 GB
#   ~12B → ~7.5 GB
#   ~27B → ~15.0 GB
#
# Formula: max_tokens = (VRAM_GB - weight_gb) * 1024 / mb_per_token
# We apply a 15% safety margin on top of that.

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

    Returns 32768 if neither source has it — conservative high value so we
    don't accidentally under-allocate on a capable model.
    """
    # Primary: modelfile parameter block
    modelfile = info.get("modelfile", "")
    for line in modelfile.splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0].upper() == "PARAMETER" and parts[1] == "num_ctx":
            try:
                return int(parts[2])
            except ValueError:
                pass

    # Secondary: model_info dict (Ollama ≥0.3)
    model_info = info.get("model_info", {})
    for key, val in model_info.items():
        if "context_length" in key and isinstance(val, int):
            return val

    return 32768  # unknown → assume large, let VRAM cap do the limiting


def _parse_param_count(info: dict) -> float:
    """
    Extract approximate parameter count (in billions) from /api/show response.

    Checks:
      1. model_info keys containing 'parameter_count' (exact, in raw count)
      2. details.parameter_size string e.g. '9.4B', '12B', '7B'
      3. model name string — parse the number before 'b' (e.g. 'qwen3.5:9b' → 9.0)

    Returns 9.0 as fallback — safe middle ground for typical models.
    """
    # Option 1: model_info exact count
    model_info = info.get("model_info", {})
    for key, val in model_info.items():
        if "parameter_count" in key and isinstance(val, (int, float)):
            return val / 1e9

    # Option 2: details.parameter_size string
    details = info.get("details", {})
    param_size = details.get("parameter_size", "")
    if param_size:
        # e.g. "9.4B", "12B", "7B", "27.2B"
        clean = param_size.upper().replace("B", "").strip()
        try:
            return float(clean)
        except ValueError:
            pass

    # Option 3: parse model name — "qwen3.5:9b" → 9.0, "gemma4:12b" → 12.0
    model_lower = info.get("model", "").lower()
    match = re.search(r":(\d+(?:\.\d+)?)b", model_lower)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return 9.0  # safe fallback


def _compute_vram_ceiling(param_billions: float, vram_gb: float) -> int:
    """
    Derive the maximum safe num_ctx from available VRAM and model size.

    Formula:
      weight_gb      = estimated model weight footprint at Q4
      available_gb   = vram_gb - weight_gb
      mb_per_token   = estimated KV cache cost per token at Q4
      raw_max        = (available_gb * 1024) / mb_per_token
      safe_max       = raw_max * 0.85  (15% safety margin)

    Returns the result rounded down to the nearest power of two,
    clamped to a minimum of 2048.
    """
    # Weight footprint at Q4 (GB) — conservative estimates
    if param_billions <= 7.5:
        weight_gb    = 4.5
        mb_per_token = 0.50
    elif param_billions <= 10.0:
        weight_gb    = 5.5
        mb_per_token = 0.55
    elif param_billions <= 14.0:
        weight_gb    = 7.5
        mb_per_token = 0.70
    elif param_billions <= 30.0:
        weight_gb    = 15.0
        mb_per_token = 1.20
    else:
        # Very large model — most VRAM goes to weights
        weight_gb    = vram_gb * 0.90
        mb_per_token = 1.60

    available_gb = max(vram_gb - weight_gb, 0)
    raw_max      = (available_gb * 1024) / mb_per_token
    safe_max     = int(raw_max * 0.85)

    # Round down to power of two (Ollama allocates in these increments)
    power = 2048
    while power * 2 <= safe_max:
        power *= 2

    return max(power, 2048)


def _estimate_tokens(messages: list[dict]) -> int:
    """
    Estimate the token count of a message list before sending to Ollama.

    Rule of thumb: 1 token ≈ 4 characters (conservative for mixed English + code).
    Add 10% overhead for Ollama's internal message formatting (role headers, etc.).

    This is an estimate, not a guarantee — real tokenisation is model-specific.
    It is always used as a lower bound; we never assume the real count is smaller.
    """
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return int((total_chars / 4) * 1.10)


def resolve_hardware_ceiling(model: str) -> int:
    """
    Return the hardware-derived maximum num_ctx for this model on this machine.
    Result is cached per process — /api/show is only called once per model.

    This is the absolute ceiling. Individual requests may use less (see
    resolve_num_ctx_for_request), but never more than this value.
    """
    if model in _ctx_cache:
        return _ctx_cache[model]

    info           = _fetch_model_info(model)
    native_ctx     = _parse_native_ctx(info)
    param_billions = _parse_param_count(info)
    vram_ceiling   = _compute_vram_ceiling(param_billions, OLLAMA_VRAM_GB)
    hardware_max   = min(native_ctx, vram_ceiling)

    _ctx_cache[model]    = hardware_max
    _native_cache[model] = native_ctx

    print(
        f"[Lincoln] ctx ceiling — model={model} "
        f"params={param_billions:.1f}B "
        f"native={native_ctx} "
        f"vram_ceiling={vram_ceiling} "
        f"→ hardware_max={hardware_max}"
    )
    return hardware_max


def resolve_num_ctx_for_request(model: str, messages: list[dict]) -> int:
    """
    Return the num_ctx to use for this specific request.

    Pipeline:
      1. Resolve hardware ceiling for this model (cached after first call).
      2. Estimate token count of the actual payload.
      3. Round up to next power of two above the estimate — allocate exactly
         what is needed, no more, no less.
      4. If the estimate exceeds the hardware ceiling:
           - Log a WARNING with exact counts so the problem is visible.
           - Clamp to hardware ceiling and send anyway — Ollama will truncate
             the oldest history, which is less bad than refusing to respond.
      5. Return the resolved value.

    This is called on every request — the per-request cost is one token
    estimate (pure Python string ops, <1ms) plus a dict lookup for the ceiling.
    The /api/show call only happens once per model per process lifetime.
    """
    hardware_max    = resolve_hardware_ceiling(model)
    estimated_tokens = _estimate_tokens(messages)

    if estimated_tokens > hardware_max:
        print(
            f"[Lincoln] WARNING: payload too large for hardware — "
            f"estimated={estimated_tokens} tokens "
            f"hardware_max={hardware_max} tokens "
            f"model={model} "
            f"VRAM={OLLAMA_VRAM_GB}GB — "
            f"oldest history will be truncated by Ollama. "
            f"Consider starting a new session or reducing pasted content."
        )
        return hardware_max

    # Round up to next power of two — never allocate less than needed
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
    Use stream_chat() instead when streaming to the UI.

    Args:
        messages    : List of message dicts with 'role' and 'content' keys
                      e.g. [{"role": "user", "content": "explain Black-Scholes"}]
        model       : Ollama model name (e.g. 'qwen3.5:9b', 'gemma4:12b')
        temperature : Sampling temperature (default 0.7)
        timeout     : Request timeout in seconds (default 180)
        think       : Enable chain-of-thought reasoning (default False).
                      Only meaningful for thinking-capable models (Qwen3, QwQ, etc.).
                      When False, suppresses the silent <think> block entirely.

    Returns:
        Complete response text as a string.

    Raises:
        requests.RequestException on network failure.
        ValueError if Ollama returns an unexpected response format.
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
    # Suppress thinking for thinking-capable models unless explicitly enabled.
    # Non-thinking models ignore this key harmlessly.
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
    Used by lincoln_routes_chat.py to stream responses to the UI via SSE.

    Args:
        messages    : List of message dicts with 'role' and 'content' keys
        model       : Ollama model name
        temperature : Sampling temperature (default 0.7)
        timeout     : Request timeout in seconds (default 180)
        think       : Enable chain-of-thought reasoning (default False).
                      When True, Ollama streams <think> tokens separately via
                      the `thinking` field on each chunk.  This generator yields
                      those tokens wrapped in SSE-style markers so the UI can
                      route them to a collapsible reasoning block:
                        "THINK_START"  — open the reasoning block
                        token          — each thinking token (raw text)
                        "THINK_END"    — close the reasoning block
                      After THINK_END, normal response tokens follow.
                      When False (default), thinking is suppressed entirely —
                      no <think> block, no latency, first token appears fast.

    Yields:
        Individual text tokens as they arrive from Ollama.
        When think=True, also yields THINK_START / THINK_END markers.

    Raises:
        requests.RequestException on network failure.
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
    # Suppress thinking for thinking-capable models unless explicitly enabled.
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

                # When think=True, Ollama puts reasoning tokens in chunk["thinking"]
                # and normal tokens in chunk["message"]["content"] as usual.
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
                    # think=False: only normal response tokens, no thinking overhead
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

    Args:
        user_question   : The current question from the user
        rag_context     : Retrieved chunks from lincoln_rag_index_service
        session_history : Previous messages in this session (role + content dicts)
        project_name    : Display name of the active project (for system prompt)

    Returns:
        List of message dicts ready to pass to chat() or stream_chat()
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
