"""
Lincoln Project Routes
======================
Flask routes for project management — the UI replacement for .env project config.

Endpoints:
  GET    /api/projects              List all projects
  POST   /api/projects              Create a new project
  DELETE /api/projects/<id>         Delete a project
  POST   /api/projects/<id>/index   Trigger an index build for a project
  GET    /api/projects/<id>/status  Get index status for a project
  POST   /api/projects/<id>/preview Preview which files would be indexed
  POST   /api/projects/<id>/aider   Launch Aider in a new terminal

These routes are the only way projects are created or deleted in Lincoln.
No project configuration ever goes through .env.
"""

import threading
import subprocess
import os
from pathlib import Path
from flask import Blueprint, jsonify, request

from lincoln.lincoln_database import (
    create_project,
    delete_project,
    get_all_projects,
    get_project_by_id,
    update_project_settings,
    update_project_vector_count,
)
from lincoln.lincoln_rag_index_service import (
    build_project_index,
    dry_run_project,
)

projects_blueprint = Blueprint("projects", __name__)

# Track ongoing index builds to report progress to the UI
# key: project_id, value: dict with status, progress, message
_index_build_status: dict[int, dict] = {}


@projects_blueprint.route("/api/projects", methods=["GET"])
def list_projects():
    """
    Return all projects for sidebar rendering.

    Response:
      JSON list of project dicts, each with:
        id, name, display_name, path, collection,
        vector_count, last_indexed, created_at
    """
    projects = get_all_projects()
    return jsonify(projects)


@projects_blueprint.route("/api/projects", methods=["POST"])
def add_project():
    """
    Create a new project from the UI 'New project' form.

    Request JSON:
      display_name : str — human-readable project name (e.g. 'Options Pricing')
      path         : str — absolute path to the project folder on disk

    Returns:
      JSON with the created project dict, or error message.

    Note: The ChromaDB collection name is auto-generated from display_name.
          The caller does not choose or set collection names.
    """
    data         = request.get_json() or {}
    display_name = data.get("display_name", "").strip()
    path         = data.get("path", "").strip()
    code_path    = (data.get("code_path") or "").strip() or None

    if not display_name:
        return jsonify({"error": "display_name is required"}), 400
    if not path:
        return jsonify({"error": "path is required"}), 400

    try:
        project = create_project(display_name=display_name, path=path, code_path=code_path)
        return jsonify(project), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@projects_blueprint.route("/api/projects/<int:project_id>", methods=["PATCH"])
def update_project(project_id: int):
    """
    Update a project's folder paths and write_enabled flag.

    Request JSON (all fields optional — only send what changed):
      path          : str  — RAG source folder path
      code_path     : str  — Aider code folder path ('' to clear)
      write_enabled : bool — whether Aider can write to code_path

    Returns:
      JSON with the updated project dict
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    data          = request.get_json() or {}
    path          = data.get("path")
    code_path     = data.get("code_path")        # may be empty string to clear
    write_enabled = data.get("write_enabled")    # bool or None

    # Validate paths exist if provided and non-empty
    if path and path != '.':
        if not Path(path).exists():
            return jsonify({"error": f"Path does not exist: {path}"}), 400
    if code_path and code_path.strip():
        if not Path(code_path).exists():
            return jsonify({"error": f"Code path does not exist: {code_path}"}), 400

    try:
        update_project_settings(
            project_id    = project_id,
            path          = path if path is not None else None,
            code_path     = code_path if code_path is not None else None,
            write_enabled = write_enabled if write_enabled is not None else None,
        )
        updated = get_project_by_id(project_id)
        return jsonify(updated)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@projects_blueprint.route("/api/projects/<int:project_id>", methods=["DELETE"])
def remove_project(project_id: int):
    """
    Delete a project from the database.

    Query parameters:
      wipe_index : bool (default false) — also delete the ChromaDB collection

    Returns:
      204 No Content on success
      404 if project not found
    """
    wipe_index = request.args.get("wipe_index", "false").lower() == "true"

    try:
        delete_project(project_id, wipe_chroma_collection=wipe_index)
        return "", 204
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@projects_blueprint.route("/api/projects/<int:project_id>/preview", methods=["POST"])
def preview_project_files(project_id: int):
    """
    Preview which files would be indexed for a project.
    Used by the UI to show a file count before the user triggers an index build.

    Returns:
      JSON with: total, by_language dict, files list
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    result = dry_run_project(project)
    return jsonify(result)


@projects_blueprint.route("/api/projects/<int:project_id>/index", methods=["POST"])
def trigger_index_build(project_id: int):
    """
    Trigger an index build for a project.
    Runs in a background thread so the UI remains responsive during indexing.

    Request JSON:
      force_rebuild : bool (default false) — re-embed all files even if unchanged

    Returns:
      202 Accepted immediately with a status URL to poll
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    if _index_build_status.get(project_id, {}).get("status") == "running":
        return jsonify({"error": "Index build already in progress for this project"}), 409

    data          = request.get_json() or {}
    force_rebuild = data.get("force_rebuild", False)

    # Initialise status
    _index_build_status[project_id] = {
        "status":  "running",
        "message": "Starting index build...",
        "vectors": 0,
    }

    def run_index_build():
        try:
            _index_build_status[project_id]["message"] = "Scanning files..."
            vector_count = build_project_index(project, force_rebuild=force_rebuild)
            update_project_vector_count(project_id, vector_count)
            _index_build_status[project_id] = {
                "status":  "complete",
                "message": f"Index complete. {vector_count} vectors stored.",
                "vectors": vector_count,
            }
        except Exception as e:
            _index_build_status[project_id] = {
                "status":  "error",
                "message": str(e),
                "vectors": 0,
            }

    thread = threading.Thread(target=run_index_build, daemon=True)
    thread.start()

    return jsonify({
        "status":     "accepted",
        "message":    "Index build started in background.",
        "status_url": f"/api/projects/{project_id}/status",
    }), 202


@projects_blueprint.route("/api/projects/<int:project_id>/status", methods=["GET"])
def get_index_status(project_id: int):
    """
    Poll the status of an ongoing or completed index build.
    The UI polls this endpoint after triggering an index build.

    Returns:
      JSON with: status ('running'|'complete'|'error'), message, vectors
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    status = _index_build_status.get(project_id, {
        "status":  "idle",
        "message": "No index build has been run yet.",
        "vectors": project.get("vector_count", 0),
    })
    return jsonify(status)


@projects_blueprint.route("/api/projects/<int:project_id>/aider", methods=["POST"])
def launch_aider_terminal(project_id: int):
    """
    Launch Aider in a new terminal window for the given project.
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    code_path = project.get("code_path") or project.get("path") or "."
    if code_path != "." and not Path(code_path).exists():
        return jsonify({"error": f"Code path does not exist: {code_path}"}), 400

    try:
        cwd = str(Path(code_path).resolve()) if code_path != "." else os.getcwd()
        
        # Using start cmd /k to open a new terminal window on Windows
        subprocess.Popen(
            ["start", "cmd", "/k", "aider"],
            shell=True,
            cwd=cwd
        )
        return jsonify({"status": "launched", "message": "Aider launched in terminal."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
