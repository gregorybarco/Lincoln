"""
Lincoln Settings Routes
=======================
Flask routes for reading and writing Lincoln's UI settings and
reporting system status.

Endpoints:
  GET  /api/settings         Return all current settings
  POST /api/settings         Save one or more settings
  GET  /api/settings/status  Return full system health report

Settings are stored in lincoln_database.db via lincoln_database.py.
Infrastructure settings (Ollama URL, embed model) are read-only
in the UI — they live in .env and require a restart to change.
"""

import os
from pathlib import Path

from flask import Blueprint, jsonify, request

from lincoln.lincoln_configuration import (
    CHROMA_DB_PATH,
    DB_PATH,
    EMBED_MODEL,
    LLM_MODEL,
    OLLAMA_BASE_URL,
    UI_HOST,
    UI_PORT,
)
from lincoln.lincoln_database import get_all_settings, get_all_projects, save_settings
from lincoln.lincoln_ollama_service import check_ollama_health, get_available_models

settings_blueprint = Blueprint("settings", __name__)


@settings_blueprint.route("/api/settings", methods=["GET"])
def get_settings():
    """
    Return all current UI settings plus read-only infrastructure info.

    Response:
      JSON with:
        ui_settings     : dict — user-editable settings from DB (theme, top_k, etc.)
        infrastructure  : dict — read-only values from .env (ollama url, embed model)
    """
    ui_settings = get_all_settings()
    return jsonify({
        "ui_settings": ui_settings,
        "infrastructure": {
            "ollama_base_url": OLLAMA_BASE_URL,
            "llm_model":       LLM_MODEL,
            "embed_model":     EMBED_MODEL,
            "ui_host":         UI_HOST,
            "ui_port":         UI_PORT,
        },
    })


@settings_blueprint.route("/api/settings", methods=["POST"])
def update_settings():
    """
    Save one or more UI settings.

    Request JSON:
      Any subset of editable setting keys:
        theme               : 'light' | 'dark' | 'system'
        default_project_id  : str (project DB id)
        top_k               : str (integer as string)
        canvas_open         : 'true' | 'false'

    Returns:
      JSON with the updated settings dict.

    Note: Infrastructure settings (ollama_base_url, embed_model, etc.)
          are ignored if included — they cannot be changed from the UI.
    """
    data = request.get_json() or {}

    # Only allow editable keys through — never write infrastructure values
    editable_keys = {"theme", "default_project_id", "top_k", "canvas_open"}
    filtered = {k: v for k, v in data.items() if k in editable_keys}

    if not filtered:
        return jsonify({"error": "No valid settings keys provided."}), 400

    save_settings(filtered)
    return jsonify(get_all_settings())


@settings_blueprint.route("/api/settings/status", methods=["GET"])
def system_status():
    """
    Return a full system health report for the Settings panel status section.

    Response:
      JSON with status for each Lincoln component:
        ollama    : health dict from lincoln_ollama_service
        chromadb  : exists flag and per-project vector counts
        database  : exists flag and row counts
        mlflow    : configured flag (future)
    """
    from lincoln import __version__, __codename__

    # Ollama health
    ollama_status = check_ollama_health()

    # ChromaDB status
    chroma_exists    = Path(CHROMA_DB_PATH).exists()
    chroma_projects  = []
    if chroma_exists:
        try:
            import chromadb
            client   = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            projects = get_all_projects()
            for project in projects:
                try:
                    count = client.get_collection(project["collection"]).count()
                except Exception:
                    count = 0
                chroma_projects.append({
                    "project": project["display_name"],
                    "vectors": count,
                })
        except Exception:
            pass

    # Database status
    db_exists = DB_PATH.exists()
    db_size   = os.path.getsize(str(DB_PATH)) if db_exists else 0

    return jsonify({
        "version":   f"{__version__} — {__codename__}",
        "ollama":    ollama_status,
        "chromadb": {
            "status":   "ok" if chroma_exists else "not built",
            "path":     CHROMA_DB_PATH,
            "projects": chroma_projects,
        },
        "database": {
            "status": "ok" if db_exists else "not found",
            "path":   str(DB_PATH),
            "size_kb": round(db_size / 1024, 1),
        },
        "mlflow": {
            "status": "not configured",
            "note":   "Planned for a future session",
        },
    })
