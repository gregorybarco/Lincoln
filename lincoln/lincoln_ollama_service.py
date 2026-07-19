"""
Lincoln Ollama Service
======================
Single owner of all communication with the local Ollama server.

Owns:
  - Sending chat messages to Qwen (or any model loaded in Ollama)
  - Streaming token-by-token responses to the Flask UI via Server-Sent Events
  - Fetching the list of available models from Ollama for the UI model selector
  - Health checking the Ollama connection

Rules:
  - No route or other service calls the Ollama API directly.
    All Ollama communication flows through this module.
  - The model used for each request is passed in as a parameter —
    this service never assumes a default model internally.
    The caller is responsible for resolving which model to use.

Used by:
  - lincoln\app\routes\lincoln_routes_chat.py    (streaming chat responses)
  - lincoln\app\routes\lincoln_routes_models.py  (model selector population)
"""

import json
from typing import Generator

import requests

from lincoln.lincoln_configuration import OLLAMA_BASE_URL


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


# ── Chat — single response ────────────────────────────────────────────────────

def chat(
    messages:    list[dict],
    model:       str,
    temperature: float = 0.7,
    timeout:     int   = 180,
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
        "options":  {"temperature": temperature},
    }

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
) -> Generator[str, None, None]:
    """
    Stream a conversation response from Ollama token by token.
    Used by lincoln_routes_chat.py to stream responses to the UI via SSE.

    Args:
        messages    : List of message dicts with 'role' and 'content' keys
        model       : Ollama model name
        temperature : Sampling temperature (default 0.7)
        timeout     : Request timeout in seconds (default 180)

    Yields:
        Individual text tokens as they arrive from Ollama.
        Yields an empty string when the stream is complete.

    Raises:
        requests.RequestException on network failure.
    """
    payload = {
        "model":    model,
        "messages": messages,
        "stream":   True,
        "options":  {"temperature": temperature},
    }

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
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done", False):
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
