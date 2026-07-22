"""
Lincoln Settings Routes  v0.6.0
==================================
Flask routes for reading and writing all Lincoln settings.

NOTHING HIDDEN GUARANTEE:
  Every value that affects Lincoln's behaviour is visible in the UI.
  User settings are stored in lincoln_database.db (editable any time).
  Infrastructure settings are stored in .env (editable via admin mode, restart required).

Endpoints:
  GET  /api/settings              All settings (user + infrastructure)
  POST /api/settings              Save user settings
  POST /api/settings/env          Admin: write a value back to .env (restart required)
  GET  /api/settings/status       Full system health report
  GET  /api/settings/fonts        Windows system font list
  GET  /api/settings/tools        Detected tool paths (nvfortran, Maple, oneAPI, etc.)

  GET  /api/settings/prompts              All global system prompt blocks
  POST /api/settings/prompts              Create a new global prompt block
  PATCH /api/settings/prompts/<id>        Update a prompt block
  DELETE /api/settings/prompts/<id>       Delete a prompt block
  POST /api/settings/prompts/reorder     Set sort order for global prompts

  GET  /api/projects/<id>/prompts         Project-level prompt blocks
  POST /api/projects/<id>/prompts         Create a project prompt block
"""

import os
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, request

from lincoln.lincoln_configuration import (
    CHROMA_DB_PATH,
    DB_PATH,
    EMBED_MODEL,
    GOOGLE_API_KEY,
    GOOGLE_CSE_ID,
    LLM_MODEL,
    LINCOLN_ROOT,
    OLLAMA_BASE_URL,
    UI_HOST,
    UI_PORT,
    OLLAMA_VRAM_GB,
    CHUNK_SIZE,
    get_all_env_values,
    write_env_key,
)
from lincoln.lincoln_database import (
    get_all_settings,
    get_all_projects,
    get_project_by_id,
    save_settings,
    get_global_system_prompts,
    get_project_system_prompts,
    create_system_prompt,
    update_system_prompt,
    delete_system_prompt,
    reorder_system_prompts,
)
from lincoln.lincoln_ollama_service import check_ollama_health, get_available_models

settings_blueprint = Blueprint("settings", __name__)

# All keys writable via POST /api/settings (user-editable, no restart needed)
_EDITABLE_KEYS = {
    "theme",
    "ui_font_family",
    "default_project_id",
    "canvas_open",
    "history_limit",
    "sidebar_show_project_chats",
    "top_k",
    "rag_snippet_chars",
    "upload_max_text_kb",
    "upload_max_doc_mb",
    "upload_retention_days",
    "ollama_timeout_sec",
    "web_search_enabled",
    "web_search_always_on",
    "lincoln_version",
    "lincoln_codename",
    "nvfortran_path",
    "f2py_fcompiler_flag",
    "wsl_distro",
    "maple_path",
    "oneapi_path",
    "aider_launch_mode",
}


# ── User settings ─────────────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings", methods=["GET"])
def get_settings():
    """
    Return all current settings plus infrastructure info.
    All values visible -- nothing hidden.
    """
    ui_settings = get_all_settings()
    env_values  = get_all_env_values()

    return jsonify({
        "ui_settings":    ui_settings,
        "infrastructure": {
            "ollama_base_url": env_values.get("OLLAMA_API_BASE",    OLLAMA_BASE_URL),
            "llm_model":       env_values.get("LINCOLN_LLM_MODEL",  LLM_MODEL),
            "embed_model":     env_values.get("LINCOLN_EMBED_MODEL", EMBED_MODEL),
            "chunk_size":      env_values.get("LINCOLN_CHUNK_SIZE",  str(CHUNK_SIZE)),
            "ui_port":         env_values.get("LINCOLN_UI_PORT",     str(UI_PORT)),
            "vram_gb":         env_values.get("LINCOLN_VRAM_GB",     str(OLLAMA_VRAM_GB)),
            "ui_host":         UI_HOST,
            "google_api_key":  env_values.get("GOOGLE_API_KEY", GOOGLE_API_KEY),
            "google_cse_id":   env_values.get("GOOGLE_CSE_ID",  GOOGLE_CSE_ID),
        },
    })


@settings_blueprint.route("/api/settings", methods=["POST"])
def update_settings():
    """Save one or more user-editable settings."""
    data     = request.get_json() or {}
    filtered = {k: v for k, v in data.items() if k in _EDITABLE_KEYS}

    if not filtered:
        return jsonify({"error": "No valid settings keys provided."}), 400

    save_settings(filtered)
    return jsonify(get_all_settings())


# ── Admin env write-back ──────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings/env", methods=["POST"])
def update_env_setting():
    """
    Admin mode: write a single infrastructure value back to .env.
    Only allowlisted keys are accepted.
    A restart is required for the change to take effect.
    """
    data  = request.get_json() or {}
    key   = data.get("key", "").strip()
    value = data.get("value", "").strip()

    if not key or not value:
        return jsonify({"error": "key and value are required"}), 400

    success = write_env_key(key, value)
    if not success:
        return jsonify({
            "error": f"Key '{key}' is not in the admin allowlist and cannot be written."
        }), 403

    return jsonify({
        "status":  "ok",
        "key":     key,
        "value":   value,
        "message": "Value written to .env. Restart Lincoln for the change to take effect.",
    })


# ── System status ─────────────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings/status", methods=["GET"])
def system_status():
    from lincoln import __version__, __codename__

    ollama_status = check_ollama_health()

    chroma_exists   = Path(CHROMA_DB_PATH).exists()
    chroma_projects = []
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

    db_exists = DB_PATH.exists()
    db_size   = os.path.getsize(str(DB_PATH)) if db_exists else 0

    # Check Tesseract availability
    tesseract_ok = False
    try:
        import subprocess
        result = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "which", "tesseract"],
            capture_output=True,
            timeout=5,
        )
        tesseract_ok = result.returncode == 0
    except Exception:
        pass

    return jsonify({
        "version": f"{__version__} -- {__codename__}",
        "ollama": ollama_status,
        "chromadb": {
            "status":   "ok" if chroma_exists else "not built",
            "path":     CHROMA_DB_PATH,
            "projects": chroma_projects,
        },
        "database": {
            "status":  "ok" if db_exists else "not found",
            "path":    str(DB_PATH),
            "size_kb": round(db_size / 1024, 1),
        },
        "tesseract": {
            "status": "ok" if tesseract_ok else "not installed",
            "note":   "Install in WSL: sudo apt install tesseract-ocr" if not tesseract_ok else "",
        },
        "mlflow": {
            "status": "not configured",
            "note":   "Planned for v0.7.0",
        },
    })


# ── System fonts ──────────────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings/fonts", methods=["GET"])
def list_system_fonts():
    """
    Return a list of font family names available on this Windows machine.
    Reads C:\Windows\Fonts\ and extracts font family names from .ttf/.otf files.
    Falls back to a curated list if the font directory is inaccessible.
    """
    fonts_dir = Path("C:/Windows/Fonts")
    font_names = set()

    if fonts_dir.exists():
        try:
            from PIL import ImageFont
            for font_file in fonts_dir.iterdir():
                if font_file.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    try:
                        # Extract family name from font file
                        font = ImageFont.truetype(str(font_file), size=12)
                        # PIL doesn't expose family name easily; use filename stem as fallback
                        name = font_file.stem.replace("-", " ").replace("_", " ")
                        font_names.add(name)
                    except Exception:
                        font_names.add(font_file.stem)
        except ImportError:
            # PIL not available -- use filename-based detection
            for font_file in fonts_dir.iterdir():
                if font_file.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    font_names.add(font_file.stem)

    # Always include reliable system fonts
    system_fonts = [
        "system-ui",
        "Segoe UI",
        "Consolas",
        "Cascadia Code",
        "JetBrains Mono",
        "Fira Code",
        "Arial",
        "Georgia",
        "Times New Roman",
        "Courier New",
        "Calibri",
        "Cambria",
        "Verdana",
        "Tahoma",
    ]
    for f in system_fonts:
        font_names.add(f)

    return jsonify({
        "fonts": sorted(font_names, key=str.lower),
    })


# ── Tool paths ────────────────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings/tools", methods=["GET"])
def get_tool_paths():
    """
    Return detected tool paths for the Build Tools section of the settings panel.
    Results are cached for the process lifetime (detection runs at startup).
    """
    from lincoln.lincoln_cleanup_service import detect_tool_paths
    tools = detect_tool_paths()
    return jsonify({"tools": tools})


# ── Global system prompts ─────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings/prompts", methods=["GET"])
def list_global_prompts():
    """Return all global system prompt blocks."""
    prompts = get_global_system_prompts()
    return jsonify(prompts)


@settings_blueprint.route("/api/settings/prompts", methods=["POST"])
def add_global_prompt():
    """Create a new global system prompt block."""
    data    = request.get_json() or {}
    label   = (data.get("label") or "").strip()
    content = (data.get("content") or "").strip()

    if not label:
        return jsonify({"error": "label is required"}), 400
    if not content:
        return jsonify({"error": "content is required"}), 400

    prompt = create_system_prompt(
        label   = label,
        content = content,
        scope   = "global",
        enabled = bool(data.get("enabled", True)),
    )
    return jsonify(prompt), 201


@settings_blueprint.route("/api/settings/prompts/<int:prompt_id>", methods=["PATCH"])
def edit_global_prompt(prompt_id: int):
    """Update label, content, enabled, or sort_order of a prompt block."""
    data = request.get_json() or {}

    label      = data.get("label")
    content    = data.get("content")
    enabled    = data.get("enabled")
    sort_order = data.get("sort_order")

    updated = update_system_prompt(
        prompt_id  = prompt_id,
        label      = label,
        content    = content if content is not None else None,
        enabled    = bool(enabled) if enabled is not None else None,
        sort_order = sort_order,
    )
    if not updated:
        return jsonify({"error": f"Prompt {prompt_id} not found"}), 404
    return jsonify(updated)


@settings_blueprint.route("/api/settings/prompts/<int:prompt_id>", methods=["DELETE"])
def remove_global_prompt(prompt_id: int):
    """Delete a global system prompt block."""
    delete_system_prompt(prompt_id)
    return "", 204


@settings_blueprint.route("/api/settings/prompts/reorder", methods=["POST"])
def reorder_global_prompts():
    """
    Set the display order for global prompts.
    Body: { "ids": [3, 1, 2] } -- ordered list of prompt ids
    """
    data = request.get_json() or {}
    ids  = data.get("ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list"}), 400
    reorder_system_prompts(ids)
    return jsonify({"status": "ok"})


# ── Project system prompts ────────────────────────────────────────────────────

@settings_blueprint.route("/api/projects/<int:project_id>/prompts", methods=["GET"])
def list_project_prompts(project_id: int):
    """Return all prompt blocks for a project."""
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404
    prompts = get_project_system_prompts(project_id)
    return jsonify(prompts)


@settings_blueprint.route("/api/projects/<int:project_id>/prompts", methods=["POST"])
def add_project_prompt(project_id: int):
    """Create a new system prompt block for a project."""
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    data    = request.get_json() or {}
    label   = (data.get("label") or "").strip()
    content = (data.get("content") or "").strip()

    if not label:
        return jsonify({"error": "label is required"}), 400
    if not content:
        return jsonify({"error": "content is required"}), 400

    prompt = create_system_prompt(
        label      = label,
        content    = content,
        scope      = "project",
        project_id = project_id,
        enabled    = bool(data.get("enabled", True)),
    )
    return jsonify(prompt), 201


@settings_blueprint.route("/api/projects/<int:project_id>/prompts/<int:prompt_id>", methods=["PATCH"])
def edit_project_prompt(project_id: int, prompt_id: int):
    """Update a project-level prompt block."""
    data = request.get_json() or {}
    updated = update_system_prompt(
        prompt_id  = prompt_id,
        label      = data.get("label"),
        content    = data.get("content"),
        enabled    = bool(data.get("enabled")) if data.get("enabled") is not None else None,
        sort_order = data.get("sort_order"),
    )
    if not updated:
        return jsonify({"error": f"Prompt {prompt_id} not found"}), 404
    return jsonify(updated)


@settings_blueprint.route("/api/projects/<int:project_id>/prompts/<int:prompt_id>", methods=["DELETE"])
def remove_project_prompt(project_id: int, prompt_id: int):
    """Delete a project-level prompt block."""
    delete_system_prompt(prompt_id)
    return "", 204


@settings_blueprint.route("/api/projects/<int:project_id>/prompts/reorder", methods=["POST"])
def reorder_project_prompts(project_id: int):
    """Set the display order for project prompts."""
    data = request.get_json() or {}
    ids  = data.get("ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list"}), 400
    reorder_system_prompts(ids)
    return jsonify({"status": "ok"})


# ── Admin action routes ───────────────────────────────────────────────────────

@settings_blueprint.route("/api/settings/open-terminal", methods=["POST"])
def open_dev_terminal():
    """
    Admin mode: open a cmd.exe terminal window in the Lincoln root with the
    virtual environment already activated.
    No body parameters required.
    Only available in admin mode (enforced on the UI side).
    """
    lincoln_root = str(LINCOLN_ROOT)
    venv_activate = str(LINCOLN_ROOT / "venv" / "Scripts" / "activate.bat")
    cmd = (
        f'cmd.exe /K "cd /d {lincoln_root} && '
        f'call {venv_activate}"'
    )
    try:
        subprocess.Popen(
            cmd,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return jsonify({"status": "ok", "message": "Dev terminal opened."})
    except Exception as e:
        return jsonify({"error": f"Failed to open terminal: {e}"}), 500


@settings_blueprint.route("/api/settings/git-reset", methods=["POST"])
def git_reset_hard():
    """
    Admin mode: run 'git reset --hard HEAD' in the Lincoln root.
    Emergency rollback when a patch breaks things.
    The UI must show a confirmation dialog before calling this route.
    """
    try:
        result = subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=str(LINCOLN_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return jsonify({
                "status":  "ok",
                "message": "Git reset --hard HEAD completed.",
                "output":  result.stdout.strip(),
            })
        else:
            return jsonify({
                "error":  "git reset failed",
                "output": result.stderr.strip(),
            }), 500
    except FileNotFoundError:
        return jsonify({"error": "git not found in PATH. Is Git installed?"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "git reset timed out after 30 seconds."}), 500
    except Exception as e:
        return jsonify({"error": f"git reset failed: {e}"}), 500
