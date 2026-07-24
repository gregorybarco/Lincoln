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
    update_memory_entry,
    delete_memory_entry,
    delete_memory_entries_bulk,
    delete_all_memory_entries,
    get_setting,
)

history_blueprint = Blueprint("history", __name__)

# Locked tag set for T1-F manual memory edit/append (UI dropdown must match)
_ALLOWED_MEMORY_TAGS = {
    "preference", "decision", "constraint", "fact", "code_style", "persona",
}


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


@history_blueprint.route("/api/history/memory", methods=["POST"])
def add_memory_entry():
    """
    Manually append a new memory entry from the Memory panel (T1-F).
    Body: { "content": "...", "tag": "...", "project_id": (optional int) }
    Distinct from POST /api/history/context, which hardcodes tag=session_summary
    for the auto-save flow.
    """
    data       = request.get_json(silent=True) or {}
    content    = (data.get("content") or "").strip()
    tag        = data.get("tag")
    project_id = data.get("project_id")

    if not content:
        return jsonify({"status": "error", "message": "content is required"}), 400

    if tag not in _ALLOWED_MEMORY_TAGS:
        return jsonify({
            "status":  "error",
            "message": f"tag must be one of: {', '.join(sorted(_ALLOWED_MEMORY_TAGS))}",
        }), 400

    try:
        save_memory_entry(
            content    = content,
            project_id = project_id if isinstance(project_id, int) else None,
            tag        = tag,
        )
        return jsonify({"status": "ok"}), 201
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@history_blueprint.route("/api/history/memory/<int:entry_id>", methods=["PUT"])
def edit_memory_entry(entry_id: int):
    """
    Edit an existing memory entry's content/tag from the Memory panel (T1-F).
    Body: { "content": "...", "tag": "..." }
    """
    data    = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    tag     = data.get("tag")

    if not content:
        return jsonify({"status": "error", "message": "content is required"}), 400

    if tag not in _ALLOWED_MEMORY_TAGS:
        return jsonify({
            "status":  "error",
            "message": f"tag must be one of: {', '.join(sorted(_ALLOWED_MEMORY_TAGS))}",
        }), 400

    try:
        update_memory_entry(entry_id, content=content, tag=tag)
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


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
    Spawns a background thread to extract and save session memory asynchronously.
    Returns 200 OK immediately so the UI never hangs.

    v0.7.1 fixes:
      - Was writing to phantom 'memory_entries' table via raw SQL.
        Now uses save_memory_entry() which writes to the correct
        'lincoln_memory_entries' table.
      - History payload is now cleaned into a readable 'User: / Lincoln:'
        transcript before being passed to the LLM -- not str(list) repr.
      - Extraction prompt is more specific and produces higher-quality output.
      - History capped at last 3000 chars to prevent VRAM spike.
    """
    import threading
    from lincoln.lincoln_configuration import LLM_MODEL

    data           = request.get_json(silent=True) or {}
    raw_project_id = data.get("project_id")
    project_id     = (
        int(raw_project_id)
        if raw_project_id is not None and str(raw_project_id).isdigit()
        else None
    )

    # JS sends context as a pre-formatted "User: ...\nLincoln: ..." string
    # (built by saveAgenticMemory() in lincoln_chat.js DOM scrape).
    # Fall back to history list if context key is missing.
    raw_context = data.get("context") or data.get("history") or ""

    # If it arrived as a list (old format), convert to readable transcript
    if isinstance(raw_context, list):
        lines = []
        for msg in raw_context:
            role    = msg.get("role", "unknown")
            content = msg.get("content", "").strip()
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Lincoln: {content}")
        raw_context = "\n\n".join(lines)

    # Cap to last 3000 chars to avoid VRAM spike on long sessions
    transcript = str(raw_context).strip()
    if len(transcript) > 3000:
        transcript = transcript[-3000:]

    if not transcript:
        return jsonify({"status": "ok", "message": "No history to extract from."}), 200

    def _background_extract(transcript_text: str, proj_id: int | None):
        try:
            import ollama
            from lincoln.lincoln_database import save_memory_entry

            extraction_prompt = (
                "You are a memory extraction assistant. "
                "Read the following chat transcript and extract ONLY facts worth "
                "remembering across future sessions. Focus on:\n"
                "- User preferences and style rules (e.g. 'User prefers X')\n"
                "- Decisions made (e.g. 'Decided to use Y for Z')\n"
                "- Constraints or bans (e.g. 'Never use ctypes for GPU bridging')\n"
                "- Tool paths, versions, or environment facts\n"
                "- Code style directives\n\n"
                "Output a concise bulleted list of declarative sentences. "
                "Each bullet must make sense in isolation. "
                "Do NOT include temporary working notes, questions, or mid-task state. "
                "If there is nothing worth saving, output exactly: NOTHING_TO_SAVE\n\n"
                f"Transcript:\n{transcript_text}"
            )

            response = ollama.chat(
                model    = LLM_MODEL,
                messages = [{"role": "user", "content": extraction_prompt}],
            )
            extracted = response.get("message", {}).get("content", "").strip()

            if not extracted or extracted == "NOTHING_TO_SAVE":
                print("[Lincoln] auto_save_memory: nothing worth saving in this session.")
                return

            # Write to correct table via DB helper (not raw SQL)
            save_memory_entry(
                content    = extracted,
                project_id = proj_id,
                tag        = "session_summary",
            )
            print(f"[Lincoln] auto_save_memory: saved {len(extracted)} chars to memory.")

        except Exception as bg_err:
            print(f"[Lincoln] auto_save_memory background error: {bg_err}")

    t        = threading.Thread(target=_background_extract, args=(transcript, project_id))
    t.daemon = True
    t.start()

    return jsonify({
        "status":  "ok",
        "message": "Memory extraction queued in background.",
    }), 200