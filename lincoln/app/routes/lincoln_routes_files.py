"""
Lincoln File Routes  v0.5.0
============================
Flask routes for file attachment handling in the chat UI.

Endpoints:
  POST /api/files/upload   Accept a file upload, extract text, store for session use
  GET  /api/files/<id>     Retrieve stored file content by file_id

v0.5.0 additions:
  - PDF text extraction via pypdf (already in requirements.txt)
  - .docx text extraction via python-docx (add: pip install python-docx)
  - .xlsx text extraction via openpyxl (add: pip install openpyxl)
  - .ipynb (Jupyter) — JSON parse, extract code cells
  - .tex .latex .bib .maple .mw .mpl added to allowlist as plain text
  - Size cap raised to 2 MB for document types (.pdf .docx .xlsx)
  - Text files still capped at 512 KB

Supported extensions (v0.5.0):
  Code:        .py .f90 .f95 .f03 .f08 .f .for .js .ts .jsx .tsx
               .css .html .htm .sql .c .cpp .h .hpp .rs .go .java
               .sh .bat .ps1 .r
  Data/Config: .md .txt .csv .json .yaml .yml .toml .ini .cfg .env.example
  LaTeX/Math:  .tex .latex .bib .maple .mw .mpl
  Notebook:    .ipynb
  Documents:   .pdf .docx .xlsx  (server-side text extraction)

Binary files that slipped through extension check → 415 Unsupported.
"""

import hashlib
import io
import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from lincoln.lincoln_configuration import DB_PATH

files_blueprint = Blueprint("files", __name__)

_UPLOAD_DIR = DB_PATH.parent / "uploads"

_MAX_TEXT_BYTES = 512 * 1024   # 512 KB for plain text / code
_MAX_DOC_BYTES  = 2 * 1024 * 1024  # 2 MB for PDF / docx / xlsx / csv

# ── Extension lists ───────────────────────────────────────────────────────────

_TEXT_EXTENSIONS = {
    # Code
    ".py", ".f90", ".f95", ".f03", ".f08", ".f", ".for", ".fpp",
    ".js", ".ts", ".jsx", ".tsx", ".css", ".html", ".htm",
    ".sql", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java",
    ".sh", ".bat", ".ps1", ".r",
    # Data / config
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".env.example",
    # LaTeX / math / Maple
    ".tex", ".latex", ".bib", ".maple", ".mw", ".mpl",
}

_DOC_EXTENSIONS = {
    ".pdf",   # text extracted via pypdf
    ".docx",  # text extracted via python-docx
    ".xlsx",  # text extracted via openpyxl / pandas
    ".csv",   # text extracted via pandas
    ".ipynb", # JSON parsed, code cells extracted
}

_ALLOWED_EXTENSIONS = _TEXT_EXTENSIONS | _DOC_EXTENSIONS


# ── Text extractors for binary document types ─────────────────────────────────

def _extract_pdf(raw: bytes) -> str:
    """Extract text from PDF using pypdf (already in requirements.txt)."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        pages  = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
        return "\n\n".join(pages) if pages else "(No extractable text found in PDF)"
    except Exception as exc:
        return f"(PDF text extraction failed: {exc})"


def _extract_docx(raw: bytes) -> str:
    """Extract text from .docx using python-docx."""
    try:
        import docx
        doc        = docx.Document(io.BytesIO(raw))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        # Also extract tables
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    paragraphs.append(" | ".join(cells))
        return "\n\n".join(paragraphs) if paragraphs else "(No text found in document)"
    except ImportError:
        return "(python-docx not installed — run: pip install python-docx)"
    except Exception as exc:
        return f"(DOCX text extraction failed: {exc})"


def _extract_xlsx(raw: bytes) -> str:
    """Extract text from .xlsx using pandas."""
    try:
        import pandas as pd
        df_dict = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        sheets = []
        for name, df in df_dict.items():
            df.dropna(how="all", inplace=True)
            df.dropna(axis=1, how="all", inplace=True)
            if not df.empty:
                sheets.append(f"=== Sheet: {name} ===\n" + df.to_markdown(index=False))
        return "\n\n".join(sheets) if sheets else "(No data found in spreadsheet)"
    except ImportError:
        return "(pandas not installed — run: pip install pandas openpyxl)"
    except Exception as exc:
        return f"(XLSX text extraction failed: {exc})"


def _extract_csv(raw: bytes) -> str:
    """Extract text from .csv using pandas and chardet."""
    try:
        import pandas as pd
        import chardet
        enc = chardet.detect(raw)["encoding"] or "utf-8"
        df = pd.read_csv(io.BytesIO(raw), encoding=enc)
        df.dropna(how="all", inplace=True)
        df.dropna(axis=1, how="all", inplace=True)
        return df.to_markdown(index=False)
    except ImportError:
        return "(pandas or chardet not installed — run: pip install pandas chardet)"
    except Exception as exc:
        return f"(CSV text extraction failed: {exc})"


def _extract_ipynb(raw: bytes) -> str:
    """Extract code and markdown cells from Jupyter notebook."""
    try:
        nb    = json.loads(raw.decode("utf-8"))
        cells = nb.get("cells", [])
        parts = []
        for cell in cells:
            ctype  = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue
            if ctype == "code":
                lang = nb.get("metadata", {}).get("kernelspec", {}).get("language", "python")
                parts.append(f"```{lang}\n{source}\n```")
            elif ctype == "markdown":
                parts.append(source)
        return "\n\n".join(parts) if parts else "(Empty notebook)"
    except Exception as exc:
        return f"(Notebook extraction failed: {exc})"


# ── Routes ────────────────────────────────────────────────────────────────────

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
        "file_id":    "<sha256-hex[:16]>",
        "filename":   "original_name.pdf",
        "size_bytes": 204800,
        "preview":    "first 500 chars of extracted text"
      }
    """
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part in request"}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"status": "error", "message": "Empty filename"}), 400

    suffix = Path(upload.filename).suffix.lower()

    # Special handling for .env.example — suffix would be '' or '.example'
    if upload.filename.endswith(".env.example"):
        suffix = ".env.example"

    if suffix not in _ALLOWED_EXTENSIONS:
        return jsonify({
            "status":  "error",
            "message": (
                f"File type '{suffix}' is not supported. "
                f"Supported: .py .f90 .tex .maple .md .csv .pdf .docx .xlsx .ipynb and more."
            ),
        }), 415

    is_doc = suffix in _DOC_EXTENSIONS
    limit  = _MAX_DOC_BYTES if is_doc else _MAX_TEXT_BYTES
    raw    = upload.read()

    if len(raw) > limit:
        kb = len(raw) // 1024
        return jsonify({
            "status":  "error",
            "message": (
                f"File is {kb} KB — limit is {limit // 1024} KB. "
                f"Paste the relevant section directly into the chat instead."
            ),
        }), 413

    # Extract text content
    if suffix == ".pdf":
        text = _extract_pdf(raw)
    elif suffix == ".docx":
        text = _extract_docx(raw)
    elif suffix == ".xlsx":
        text = _extract_xlsx(raw)
    elif suffix == ".csv":
        text = _extract_csv(raw)
    elif suffix == ".ipynb":
        text = _extract_ipynb(raw)
    else:
        # Plain text / code - Use chardet for robust multilingual encoding
        import chardet
        enc = chardet.detect(raw)["encoding"] or "utf-8"
        try:
            text = raw.decode(enc)
        except Exception:
            text = raw.decode("latin-1", errors="replace")

    # Content-addressed storage
    file_id  = hashlib.sha256(raw).hexdigest()[:16]
    out_path = _UPLOAD_DIR / f"{file_id}.txt"

    if not out_path.exists():
        out_path.write_text(text, encoding="utf-8")

    return jsonify({
        "status":     "ok",
        "file_id":    file_id,
        "filename":   upload.filename,
        "size_bytes": len(raw),
        "preview":    text[:500].strip(),
    }), 200


@files_blueprint.route("/api/files/<file_id>", methods=["GET"])
def get_file_content(file_id: str):
    """
    Retrieve stored file content by file_id for injection into the chat prompt.
    Called by lincoln_routes_chat.py before building the Ollama payload.

    Response:
      { "status": "ok", "content": "<full extracted text>", "filename": "…" }
    """
    if not all(c in "0123456789abcdef" for c in file_id):
        return jsonify({"status": "error", "message": "Invalid file_id"}), 400

    # v0.5.0: all extracted content stored as .txt
    txt_path = _UPLOAD_DIR / f"{file_id}.txt"
    if txt_path.exists():
        try:
            content = txt_path.read_text(encoding="utf-8")
            return jsonify({"status": "ok", "content": content, "filename": txt_path.name}), 200
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    # Legacy: try any extension (v0.4.x uploads)
    matches = list(_UPLOAD_DIR.glob(f"{file_id}.*"))
    if not matches:
        return jsonify({"status": "error", "message": "File not found"}), 404

    file_path = matches[0]
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "ok", "content": content, "filename": file_path.name}), 200