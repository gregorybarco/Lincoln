"""
Lincoln Git Routes  v0.6.0
============================
Read-only git status, log, and diff for project folders.
Never commits, stages, or modifies anything.

Endpoints:
  GET /api/projects/<id>/git   Git status for a project's folder
"""

from flask import Blueprint, jsonify

from lincoln.lincoln_database import get_project_by_id, get_setting
from lincoln.lincoln_git_service import get_git_status

git_blueprint = Blueprint("git", __name__)


@git_blueprint.route("/api/projects/<int:project_id>/git", methods=["GET"])
def project_git_status(project_id: int):
    """
    Return git status for a project's folder.
    Uses the project's 'path' setting as the repo root.
    Runs via WSL for Windows-path projects (auto-detected).
    """
    project = get_project_by_id(project_id)
    if not project:
        return jsonify({"error": f"Project {project_id} not found"}), 404

    project_path = project.get("path", "")
    if not project_path or project_path == ".":
        return jsonify({
            "available": False,
            "error": "No folder path is set for this project. Set a RAG source folder in project settings.",
        })

    wsl_distro = get_setting("wsl_distro", "Ubuntu")
    status     = get_git_status(project_path, wsl_distro=wsl_distro)

    return jsonify(status)
