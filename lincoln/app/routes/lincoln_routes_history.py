"""
Lincoln Chat History Routes  v0.6.0
======================================
Flask routes for chat session history and memory management.

Changes in v0.6.0:
  - history_limit read from DB setting (configurable in UI, default 100)
  - GET /api/history supports ?project_id= filter
  - DELETE /api/history/all -- was called by JS but route was missing (bug fix)
  - DELETE /api/history/selected -- bulk delete for multi-select
  - Full memory entry management: GET/POST/DELETE /api/history/memory
  - DELETE /api/history/memory/<id> -- single memory delete
  - DELETE /api/history/memory/selected -- bulk memory delete
  - DELETE /api/history/memory/all -- clear all memories

Endpoints:
  GET    /api/history                  List sessions (respects history_limit + project_id filter)
  GET    /api/history/<id>             Get messages for a session
  DELETE /api/history/<id>             Delete a session
  DELETE /api/history/all              Delete all sessions
  DELETE /api/history/selected         Bulk delete selected sessions
  GET    /api/history/context          Recent memory entries for context strip (startup)
  POST   /api/history/context          Save a memory entry
  GET    /api/history/memory           All memory entries (for Memory panel full list)
  DELETE /api/history/memory/<id>      Delete a single memory entry
  DELETE /api/history/memory/selected  Bulk delete memory entries
  DELETE /api/history/memory/all       Delete all memory entries
"""

from flask import Blueprint, jsonify, request

from lincoln.lincoln_database import (
    delete_session,
    delete_sessions_bulk,
    delete_all_sessions,
    get_all_sessions,
    get_all_memory_entries,
    get_recent_memory_entries,
    get_session_messages,
    save_memory_entry,
    delete_memory_entry,
    delete_memory_entries_bulk,
    delete_all_memory_entries,
    get_setting,
)

history_blueprint = Blueprint("history", __name__)


def _get_history_limit() -> int:
    """Read history_limit from DB settings. Default 100."""
    try:
        return int(get_setting("history_limit", "100"))
    except (ValueError, TypeError):
        return 100


# ── Chat history ──────────────────────────────────────────────────────────────

@history_blueprint.route("/api/history", methods=["GET"])
def list_sessions():
    """
    Return recent chat sessions for sidebar rendering.
    Respects history_limit setting (configurable in UI, default 100).
    Optional ?project_id=N filter for project home recent chats.
    """
    limit      = _get_history_limit()
    project_id = request.args.get("project_id", type=int)
    sessions   = get_all_sessions(limit=limit, project_id=project_id)
    return jsonify(sessions)


@history_blueprint.route("/api/history/<int:session_id>", methods=["GET"])
def get_session_history(session_id: int):
    messages = get_session_messages(session_id)
    return jsonify(messages)


@history_blueprint.route("/api/history/<int:session_id>", methods=["DELETE"])
def remove_session(session_id: int):
    delete_session(session_id)
    return "", 204


@history_blueprint.route("/api/history/all", methods=["DELETE"])
def remove_all_sessions():
    """
    Delete ALL chat sessions and messages.
    This route was called by the JS clearAllHistory() function
    but the route was missing (bug fix in v0.6.0).
    """
    delete_all_sessions()
    return "", 204


@history_blueprint.route("/api/history/selected", methods=["DELETE"])
def remove_selected_sessions():
    """
    Bulk delete a set of sessions by id.
    Body: { "ids": [1, 2, 3] }
    """
    data = request.get_json(silent=True) or {}
    ids  = data.get("ids", [])

    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ids must be a non-empty list of integers"}), 400

    try:
        ids = [int(i) for i in ids]
    except (ValueError, TypeError):
        return jsonify({"error": "All ids must be integers"}), 400

    delete_sessions_bulk(ids)
    return jsonify({"status": "ok", "deleted": len(ids)})


# ── Memory context strip (startup) ────────────────────────────────────────────

@history_blueprint.route("/api/history/context", methods=["GET"])
def get_session_context():
    """
    Return recent memory entries for the session context strip (startup banner).
    Returns only the 5 most recent -- for the full list use /api/history/memory.
    """
    entries = get_recent_memory_entries(limit=5)
    return jsonify(entries)


@history_blueprint.route("/api/history/context", methods=["POST"])
def save_session_context():
    """Save a memory entry from the current session."""
    data       = request.get_json(silent=True) or {}
    content    = (data.get("content") or "").strip()
    project_id = data.get("project_id")
    tag        = data.get("tag") or "session_summary"

    if not content:
        return jsonify({"status": "error", "message": "content is required"}), 400

    try:
        save_memory_entry(
            content    = content,
            project_id = project_id if isinstance(project_id, int) else None,
            tag        = tag,
        )
        return jsonify({"status": "ok"}), 201
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# ── Memory panel (full list) ──────────────────────────────────────────────────

@history_blueprint.route("/api/history/memory", methods=["GET"])
def list_all_memory():
    """
    Return all memory entries for the Memory panel full list.
    Optional ?project_id=N filter to show only entries for one project.
    """
    project_id = request.args.get("project_id", type=int)
    entries    = get_all_memory_entries(project_id=project_id)
    return jsonify(entries)


@history_blueprint.route("/api/history/memory/<int:entry_id>", methods=["DELETE"])
def remove_memory_entry(entry_id: int):
    """Delete a single memory entry."""
    delete_memory_entry(entry_id)
    return "", 204


@history_blueprint.route("/api/history/memory/selected", methods=["DELETE"])
def remove_selected_memory():
    """
    Bulk delete a set of memory entries.
    Body: { "ids": [1, 2, 3] }
    """
    data = request.get_json(silent=True) or {}
    ids  = data.get("ids", [])

    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ids must be a non-empty list of integers"}), 400

    try:
        ids = [int(i) for i in ids]
    except (ValueError, TypeError):
        return jsonify({"error": "All ids must be integers"}), 400

    delete_memory_entries_bulk(ids)
    return jsonify({"status": "ok", "deleted": len(ids)})


@history_blueprint.route("/api/history/memory/all", methods=["DELETE"])
def remove_all_memory():
    """Delete all memory entries."""
    delete_all_memory_entries()
    return "", 204

@history_blueprint.route("/api/history/memory/auto", methods=["POST"])
def auto_save_memory():
    """
    Spawns a background thread to handle Ollama memory extraction asynchronously,
    returning an immediate 200 OK to the UI to prevent hanging.
    """
    import threading
    from lincoln.lincoln_configuration import DB_PATH, LLM_MODEL

    data = request.get_json(silent=True) or {}
    chat_history = data.get("history") or data.get("context") or []
    raw_project_id = data.get("project_id")
    project_id = int(raw_project_id) if raw_project_id is not None and str(raw_project_id).isdigit() else None

    def _background_extract(history_data, proj_id):
        try:
            import sqlite3
            import ollama

            extraction_prompt = (
                "Analyze the following chat history and extract key architectural facts, "
                "user preferences, and code patterns into a concise bulleted list. "
                "Output only the extracted facts.\n\n" + str(history_data)
            )

            response = ollama.chat(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": extraction_prompt}]
            )
            extracted_facts = response.get("message", {}).get("content", "").strip()

            if not extracted_facts:
                extracted_facts = "No facts extracted from session history."

            # Use direct thread-safe connection to persist memory
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    project_id INTEGER,
                    tag TEXT DEFAULT 'session_summary',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "INSERT INTO memory_entries (content, project_id, tag) VALUES (?, ?, ?)",
                (extracted_facts, proj_id, "session_summary")
            )
            conn.commit()
            conn.close()
        except Exception as bg_err:
            print(f"[Lincoln Background Memory Error]: {bg_err}")

    # Spawn thread so UI returns instantly
    t = threading.Thread(target=_background_extract, args=(chat_history, project_id))
    t.daemon = True
    t.start()

    return jsonify({
        "status": "ok",
        "message": "Memory extraction queued in background."
    }), 200