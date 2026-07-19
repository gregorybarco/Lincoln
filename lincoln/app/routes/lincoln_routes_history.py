"""
Lincoln Chat History Routes
============================
Flask routes for chat session history management.

Endpoints:
  GET    /api/history              List recent chat sessions for sidebar
  GET    /api/history/<id>         Get all messages for a specific session
  DELETE /api/history/<id>         Delete a session and all its messages
  GET    /api/history/context      Get recent memory entries for session strip
  POST   /api/history/context      Save a memory entry from the current session

Deletion removes the session and all messages from lincoln_database.db.
There is no soft delete — deletion from the UI means deletion from the machine.
"""

from flask import Blueprint, jsonify, request

from lincoln.lincoln_database import (
    delete_session,
    get_all_sessions,
    get_recent_memory_entries,
    get_session_messages,
    save_memory_entry,
)

history_blueprint = Blueprint("history", __name__)


@history_blueprint.route("/api/history", methods=["GET"])
def list_sessions():
    """
    Return recent chat sessions for sidebar rendering.
    Ordered newest first, limited to 50 entries.

    Response:
      JSON list of session dicts, each with:
        id, title, project_id, project_display_name,
        created_at, updated_at
    """
    sessions = get_all_sessions(limit=50)
    return jsonify(sessions)


@history_blueprint.route("/api/history/<int:session_id>", methods=["GET"])
def get_session_history(session_id: int):
    """
    Return all messages for a specific chat session.
    Used when the user clicks a history entry to restore a conversation.

    Response:
      JSON list of message dicts ordered chronologically, each with:
        id, session_id, role, content, created_at
    """
    messages = get_session_messages(session_id)
    return jsonify(messages)


@history_blueprint.route("/api/history/<int:session_id>", methods=["DELETE"])
def remove_session(session_id: int):
    """
    Delete a chat session and all its messages from the database.
    This is permanent — there is no recovery after deletion.

    Returns:
      204 No Content on success
    """
    delete_session(session_id)
    return "", 204


@history_blueprint.route("/api/history/context", methods=["GET"])
def get_session_context():
    """
    Return recent memory entries for the session context strip.
    Called on UI startup to populate the dismissible context banner
    showing what was worked on in the last session.

    Response:
      JSON list of recent memory entry dicts (newest first, limit 5)
    """
    entries = get_recent_memory_entries(limit=5)
    return jsonify(entries)


@history_blueprint.route("/api/history/context", methods=["POST"])
def save_session_context():
    """
    Save a memory entry from the current session.
    Called by the JS memory button (lincolnChat.saveMemory) when the user
    clicks 'Save current session' in the Memory panel.

    Body (JSON):
      {
        "content":    "Summary text to persist",
        "project_id": 1,          (optional — int or null)
        "tag":        "session_summary"  (optional)
      }

    Response:
      201 { "status": "ok" }        on success
      400 { "status": "error" }     if content is missing or empty
      500 { "status": "error" }     on unexpected DB failure
    """
    data       = request.get_json(silent=True) or {}
    content    = (data.get("content") or "").strip()
    project_id = data.get("project_id")   # int | None — passed straight to DB
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