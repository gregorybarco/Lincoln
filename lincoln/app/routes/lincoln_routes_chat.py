"""
Lincoln Chat Routes
===================
Flask routes for the chat interface.

Endpoints:
  POST /api/chat/send      Send a message, get a streamed response via SSE
  GET  /api/chat/session   Get all messages for a session
  POST /api/chat/session   Create a new session

Flow per message:
  1. Receive user message, optional file_id, active project/model from UI
  2. If file_id present, load file content and prepend to user message
  3. Save user message to lincoln_database
  4. If project active and indexed, query RAG index for context
  5. Build full message list (system prompt + history + RAG + user message)
  6. Stream response from Ollama token by token via SSE
  7. Save completed assistant response to lincoln_database
  8. Return source references for canvas display
"""

import json
from pathlib import Path

from flask import Blueprint, Response, request, jsonify, stream_with_context

from lincoln.lincoln_database import (
    add_message,
    create_session,
    get_project_by_id,
    get_session_messages,
    rename_session,
)
from lincoln.lincoln_ollama_service import (
    build_messages_with_rag_context,
    stream_chat,
)
from lincoln.lincoln_rag_index_service import query_project_index
from lincoln.lincoln_configuration import DEFAULT_TOP_K, LLM_MODEL, DB_PATH
chat_blueprint = Blueprint("chat", __name__)

_UPLOAD_DIR = DB_PATH.parent / "uploads"

@chat_blueprint.route("/api/chat/session", methods=["POST"])
def create_new_session():
    """
    Create a new chat session only when explicitly requested by the UI.
    The UI should call this only when the user clicks 'New chat',
    not on every page load — prevents ghost sessions in history.

    Request JSON:
      project_id : int | null

    Returns:
      JSON with the new session dict
    """
    data       = request.get_json() or {}
    project_id = data.get("project_id")
    session    = create_session(title="New chat", project_id=project_id)
    return jsonify(session)


@chat_blueprint.route("/api/chat/session/<int:session_id>", methods=["GET"])
def get_session(session_id: int):
    messages = get_session_messages(session_id)
    return jsonify(messages)


@chat_blueprint.route("/api/chat/send", methods=["POST"])
def send_message():
    """
    Send a user message and stream the assistant response via SSE.

    Request JSON:
      session_id  : int
      message     : str
      model       : str
      project_id  : int | null
      use_rag     : bool
      file_id     : str | null   — optional uploaded file to inject as context
    """
    data       = request.get_json() or {}
    session_id = data.get("session_id")
    user_text  = data.get("message", "").strip()
    model      = data.get("model", LLM_MODEL)
    project_id = data.get("project_id")
    use_rag    = data.get("use_rag", True)
    file_id    = data.get("file_id")          # may be None

    if not session_id or not user_text:
        return jsonify({"error": "session_id and message are required"}), 400

    # ── Inject uploaded file content into user message ────────────────────
    injected_filename = None
    if file_id:
        safe_id = "".join(c for c in file_id if c in "0123456789abcdef")
        matches = list(_UPLOAD_DIR.glob(f"{safe_id}.*")) if safe_id else []
        if matches:
            try:
                file_text = matches[0].read_text(encoding="utf-8")
                injected_filename = matches[0].name
                user_text = (
                    f"[Attached file: {injected_filename}]\n"
                    f"```\n{file_text}\n```\n\n"
                    f"{user_text}"
                )
            except Exception:
                pass   # file read failed — send without attachment

    # Save user message (store the original question, not the injected blob)
    display_text = data.get("message", "").strip()
    if injected_filename:
        display_text = f"📎 {injected_filename}\n\n{display_text}"
    add_message(session_id, "user", display_text)

    # Auto-rename session from first user message
    messages = get_session_messages(session_id)
    if len(messages) == 1:
        title = display_text[:50] + ("…" if len(display_text) > 50 else "")
        rename_session(session_id, title)

    def generate():
        sources      = []
        rag_context  = ""
        project_name = ""

        if project_id and use_rag:
            try:
                project = get_project_by_id(project_id)
                if project and project.get("vector_count", 0) > 0:
                    project_name = project["display_name"]
                    result       = query_project_index(
                        question     = data.get("message", "").strip(),
                        collection   = project["collection"],
                        project_name = project_name,
                        top_k        = DEFAULT_TOP_K,
                    )
                    rag_context = result["answer"]
                    sources     = result["sources"]
                    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
            except Exception as rag_error:
                yield f"data: {json.dumps({'type': 'error', 'message': f'RAG error: {str(rag_error)}'})}\n\n"

        history = get_session_messages(session_id)
        ollama_messages = build_messages_with_rag_context(
            user_question   = user_text,        # includes file blob if injected
            rag_context     = rag_context,
            session_history = [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m["role"] != "system"
            ],
            project_name = project_name,
        )

        full_response = []
        try:
            for token in stream_chat(messages=ollama_messages, model=model):
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as stream_error:
            yield f"data: {json.dumps({'type': 'error', 'message': str(stream_error)})}\n\n"
            return

        complete_text = "".join(full_response)
        saved_message = add_message(session_id, "assistant", complete_text)
        yield f"data: {json.dumps({'type': 'done', 'message_id': saved_message['id']})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )
