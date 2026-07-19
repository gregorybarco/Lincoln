"""
Lincoln Model Routes
====================
Flask routes for the UI model selector.

Endpoints:
  GET /api/models          List all chat-capable models available in Ollama
  GET /api/models/health   Check Ollama server health

Embedding-only models (nomic-embed-text and variants) are excluded from the
model selector — they are not chat models and should never appear in the UI.
The embed model is displayed as a read-only badge in Settings instead.
"""

from flask import Blueprint, jsonify

from lincoln.lincoln_ollama_service import check_ollama_health, get_available_models
from lincoln.lincoln_configuration import LLM_MODEL

models_blueprint = Blueprint("models", __name__)

# Models that exist in Ollama but are not chat models.
# Extend this set if you pull other embedding models in future.
_EMBEDDING_MODELS = {
    "nomic-embed-text",
    "nomic-embed-text:latest",
    "nomic-embed-text:v1.5",
    "mxbai-embed-large",
    "mxbai-embed-large:latest",
    "all-minilm",
    "all-minilm:latest",
    "snowflake-arctic-embed",
    "snowflake-arctic-embed:latest",
}


@models_blueprint.route("/api/models", methods=["GET"])
def list_available_models():
    """
    Return all chat-capable models currently available in Ollama.
    Embedding-only models are stripped before the response is sent.

    Response:
      JSON with:
        models        : list of model dicts (name, size, modified_at)
        default_model : str — the startup default from .env
    """
    all_models = get_available_models()

    # Strip embedding models — they are not selectable as chat models
    chat_models = [
        m for m in all_models
        if m.get("name", "").lower() not in _EMBEDDING_MODELS
    ]

    return jsonify({
        "models":        chat_models,
        "default_model": LLM_MODEL,
    })


@models_blueprint.route("/api/models/health", methods=["GET"])
def ollama_health_check():
    """
    Check whether the Ollama server is reachable.
    Used by the Settings panel system status section.

    Response:
      JSON with: status ('ok'|'unreachable'), url, message
    """
    health = check_ollama_health()
    status_code = 200 if health["status"] == "ok" else 503
    return jsonify(health), status_code