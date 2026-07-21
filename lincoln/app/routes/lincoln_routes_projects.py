"""
Lincoln Project Routes  v0.6.0
================================
Flask routes for project management.

Changes in v0.6.0:
  - Aider launch supports WSL mode (B8): checks aider_launch_mode setting.
    If 'wsl', launches wsl.exe with auto-derived Linux path.
  - aider_editor project setting (cmd | wsl | vscode).
  - Index polling correctly stops on 'complete' or 'error' (B1 fix on server side).

Endpoints:
  GET    /api/projects              List all projects
  POST   /api/projects              Create a project
  PATCH  /api/projects/<id>         Update project settings
  DELETE /api/projects/<id>         Delete a project
  POST   /api/projects/<id>/index   Trigger index build
  GET    /api/projects/<id>/status  Poll index build status
  POST   /api/projects/<id>/preview Preview indexable files
  POST   /api/projects/<id>/aider   Launch Aider in terminal
  GET    /api/projects/<id>/git     (handled by lincoln_routes_git.py)
"""

import subprocess
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from lincoln.lincoln_database import (
    create_project,
    delete_project,
    get_all_projects,
    get_project_by_id,
    update_project_settings,
    update_project_vector_count,
    get_setting,
)
from lincoln.lincoln_rag_index_service import build_project_index, dry_run_project

projects_blueprint = Blueprint("projects", __name__)

# key: project_id -> {'status': str, 'progress': int, 'message': str, 'error': str}
_index_build_status: dict[int, dict] = {}


# ── Project CRUD ──────────────────────────────────────────────────────────────

@projects_blueprint.route("/api/projects", methods=["GET"])
def list_projects():
    return jsonify(get_all_projects())


@projects_blueprint.route("/api/projects", methods=["POST"])
def add_project():
    data         = request.get_json() or {}
    display_name = (data.get("display_name") or "").strip()
    path         = (data.get("path") or ".").strip()
    code_path    = (data.get("code_path") or "").strip() or None

    if not display_name:
        return jsonify({"error": "display_name is required"}), 400

    try:
        project = create_project(display_name=display_name, path=path, code_path=code_path)
        return jsonify(project), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@projects_blueprint.route("/api/projects/<int:project_id>", methods=["PATCH"])
def update_project(project_id: int):
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    data = request.get_json() or {}

    path          = data.get("path")
    code_path     = data.get("code_path")
    write_enabled = data.get("write_enabled")

    update_project_settings(
        project_id    = project_id,
        path          = path,
        code_path     = code_path,
        write_enabled = bool(write_enabled) if write_enabled is not None else None,
    )
    return jsonify(get_project_by_id(project_id))


@projects_blueprint.route("/api/projects/<int:project_id>", methods=["DELETE"])
def remove_project(project_id: int):
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    wipe_index = request.args.get("wipe_index", "false").lower() == "true"

    try:
        delete_project(project_id, wipe_chroma_collection=wipe_index)
        return "", 204
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Index build ───────────────────────────────────────────────────────────────

@projects_blueprint.route("/api/projects/<int:project_id>/index", methods=["POST"])
def trigger_index(project_id: int):
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    if _index_build_status.get(project_id, {}).get("status") == "running":
        return jsonify({"error": "Index build already running for this project"}), 409

    force_rebuild = request.get_json(silent=True) or {}
    force_rebuild = bool(force_rebuild.get("force_rebuild", False))

    _index_build_status[project_id] = {
        "status":   "running",
        "progress": 0,
        "message":  "Starting index build...",
        "error":    "",
    }

    def _run_build():
        try:
            _index_build_status[project_id]["message"] = "Collecting files..."
            count = build_project_index(project, force_rebuild=force_rebuild)
            update_project_vector_count(project_id, count)
            _index_build_status[project_id] = {
                "status":   "complete",
                "progress": 100,
                "message":  f"Index complete. {count} vectors.",
                "error":    "",
            }
        except Exception as exc:
            _index_build_status[project_id] = {
                "status":   "error",
                "progress": 0,
                "message":  "Index build failed.",
                "error":    str(exc),
            }

    thread = threading.Thread(target=_run_build, daemon=True)
    thread.start()

    return jsonify({"status": "started", "project_id": project_id})


@projects_blueprint.route("/api/projects/<int:project_id>/status", methods=["GET"])
def index_status(project_id: int):
    """
    Poll index build status.
    BUG FIX (B1): returns 'complete' or 'error' so the JS poller can stop.
    """
    status = _index_build_status.get(project_id, {
        "status":   "idle",
        "progress": 0,
        "message":  "No index build has run yet.",
        "error":    "",
    })
    return jsonify(status)


# ── File preview ──────────────────────────────────────────────────────────────

@projects_blueprint.route("/api/projects/<int:project_id>/preview", methods=["POST"])
def preview_index(project_id: int):
    """Dry run: show which files would be indexed without embedding."""
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    result = dry_run_project(project)
    return jsonify(result)


# ── Aider launch ──────────────────────────────────────────────────────────────

@projects_blueprint.route("/api/projects/<int:project_id>/aider", methods=["POST"])
def launch_aider(project_id: int):
    """
    Launch Aider in a terminal for a project.

    BUG FIX (B8): checks aider_launch_mode setting.
      'cmd' (default) -- opens Windows cmd window
      'wsl'           -- opens WSL bash, translates Windows path to /mnt/...
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    launch_mode  = get_setting("aider_launch_mode", "cmd")
    project_path = project.get("path") or project.get("code_path") or "."
    wsl_distro   = get_setting("wsl_distro", "Ubuntu")

    try:
        if launch_mode == "wsl" and project_path != ".":
            # Translate Windows path B:\OptionsPricing -> /mnt/b/OptionsPricing
            p = project_path.replace("\\", "/")
            if len(p) >= 2 and p[1] == ":":
                drive    = p[0].lower()
                rest     = p[2:].lstrip("/")
                wsl_path = f"/mnt/{drive}/{rest}"
            else:
                wsl_path = p

            subprocess.Popen(
                [
                    "wsl.exe",
                    "-d", wsl_distro,
                    "--",
                    "bash", "-c",
                    f"cd {wsl_path!r} && aider; exec bash",
                ],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            message = f"Aider launched in WSL ({wsl_distro}) at {wsl_path}"

        else:
            # Windows cmd
            if project_path and project_path != ".":
                drive = project_path[:2] if len(project_path) >= 2 else ""
                cd_cmd = f"{drive} && cd \"{project_path}\" && " if drive else f"cd \"{project_path}\" && "
            else:
                cd_cmd = ""

            subprocess.Popen(
                f"start cmd /k \"{cd_cmd}aider\"",
                shell=True,
            )
            message = "Aider launched in Windows terminal"

        return jsonify({"status": "ok", "message": message})

    except Exception as exc:
        return jsonify({"error": f"Failed to launch Aider: {exc}"}), 500
