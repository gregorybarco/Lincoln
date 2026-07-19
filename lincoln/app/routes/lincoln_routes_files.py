"""
Lincoln File Routes
===================
Flask routes for file attachment handling in the chat UI.

Endpoints:
  POST /api/files/upload   Accept a file upload and store it for session use

Files are stored temporarily in data/uploads/ keyed by session_id.
They are injected into the chat context as text when the next message is sent.
Binary files (images, PDFs) are not yet supported — text/code files only.

Supported extensions: .py .f90 .f95 .f03 .f08 .js .ts .css .html .sql
                      .md .txt .csv .json .yaml .yml .toml .ini .cfg .env
                      .c .cpp .h .hpp .rs .go .java .sh .bat .ps1

Rejected extensions return 415 Unsupported Media Type with a clear message.
File size limit: 512 KB per file. Larger files return 413.
"""

import hashlib
from pathlib import Path

from flask import Blueprint, jsonify, request

from lincoln.lincoln_configuration import DB_PATH

files_blueprint = Blueprint("files", __name__)

# Where uploaded files land — sibling of chroma_db\ and lincoln_database.db
_UPLOAD_DIR = DB_PATH.parent / "uploads"

_MAX_BYTES = 512 * 1024  # 512 KB

_ALLOWED_EXTENSIONS = {
    ".py", ".f90", ".f95", ".f03", ".f08", ".for", ".fpp",
    ".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".htm",
    ".sql", ".md", ".txt", ".csv", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java",
    ".sh", ".bat", ".ps1", ".env.example",
}


@files_blueprint.route("/api/files/upload", methods=["POST"])
def upload_file():
    """
    Accept a file upload from the chat input paperclip button.

    Form fields:
      file       : the file blob (multipart/form-data)
      session_id : (optional) current chat session id as string

    Response on success (200):
      {
        "status":     "ok",
        "file_id":    "<sha256-hex[:12]>",
        "filename":   "original_name.py",
        "size_bytes": 4096,
        "preview":    "first 300 chars of file content"
      }

    The file_id is passed back with the next chat message so the route
    handler can inject the file content into the Ollama prompt.
    """
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part in request"}), 400

    upload = request.files["file"]

    if not upload.filename:
        return jsonify({"status": "error", "message": "Empty filename"}), 400

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        return jsonify({
            "status":  "error",
            "message": (
                f"File type '{suffix}' is not supported. "
                f"Upload a text or code file (.py, .f90, .md, .txt, .json, …)"
            ),
        }), 415

    raw = upload.read()

    if len(raw) > _MAX_BYTES:
        return jsonify({
            "status":  "error",
            "message": (
                f"File is {len(raw) // 1024} KB — limit is 512 KB. "
                f"Paste the relevant section directly into the chat instead."
            ),
        }), 413

    # Decode — reject binary files that slipped through extension check
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({
            "status":  "error",
            "message": "File does not appear to be UTF-8 text. Binary files are not supported.",
        }), 415

    # Content-addressed storage: same file content → same file_id
    file_id  = hashlib.sha256(raw).hexdigest()[:16]
    out_path = _UPLOAD_DIR / f"{file_id}{suffix}"

    if not out_path.exists():
        out_path.write_bytes(raw)

    return jsonify({
        "status":     "ok",
        "file_id":    file_id,
        "filename":   upload.filename,
        "size_bytes": len(raw),
        "preview":    text[:300].strip(),
    }), 200


@files_blueprint.route("/api/files/<file_id>", methods=["GET"])
def get_file_content(file_id: str):
    """
    Retrieve stored file content by file_id for injection into the chat prompt.
    Called by lincoln_routes_chat.py before building the Ollama payload.

    Response:
      { "status": "ok", "content": "<full file text>", "filename": "…" }
    """
    # Sanitise the file_id — must be hex only
    if not all(c in "0123456789abcdef" for c in file_id):
        return jsonify({"status": "error", "message": "Invalid file_id"}), 400

    matches = list(_UPLOAD_DIR.glob(f"{file_id}.*"))
    if not matches:
        return jsonify({"status": "error", "message": "File not found"}), 404

    file_path = matches[0]
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({
        "status":   "ok",
        "content":  content,
        "filename": file_path.name,
    }), 200
