"""
Lincoln Git Service  v0.6.0
==============================
Read-only git status, log, and diff for project folders.
Never commits, never writes, never stages. Observation only.

For WSL-path projects (e.g. OptionsPricing at B:\OptionsPricing),
git commands run inside WSL at the translated Linux path.
For Windows-native projects, git runs via Windows git if available.

Used by: lincoln/app/routes/lincoln_routes_git.py
"""

import subprocess
from pathlib import Path


def _windows_to_wsl_path(windows_path: str) -> str:
    """
    Convert a Windows path to a WSL mount path.
    B:\OptionsPricing -> /mnt/b/OptionsPricing
    """
    p = windows_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest  = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def _run_git(args: list[str], cwd: str, wsl_distro: str = "Ubuntu") -> tuple[str, str, int]:
    """
    Run a git command in the given directory.
    Tries WSL first (for WSL-path projects), then Windows git.
    Returns (stdout, stderr, returncode).
    """
    # Determine if this is a Windows path that needs WSL translation
    is_windows_path = len(cwd) >= 2 and cwd[1] == ":"

    if is_windows_path:
        wsl_path = _windows_to_wsl_path(cwd)
        cmd = ["wsl", "-d", wsl_distro, "--", "git", "-C", wsl_path] + args
    else:
        cmd = ["git", "-C", cwd] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", "git not found", 1
    except subprocess.TimeoutExpired:
        return "", "git command timed out", 1
    except Exception as e:
        return "", str(e), 1


def get_git_status(project_path: str, wsl_distro: str = "Ubuntu") -> dict:
    """
    Return a structured git status summary for a project folder.

    Returns dict with:
      available : bool -- whether git is available and this is a git repo
      branch    : str  -- current branch name
      status    : str  -- short status output (M = modified, ? = untracked, etc.)
      log       : list -- last 10 commits (hash, message, author, date)
      diff_stat : str  -- summary of uncommitted changes
      error     : str  -- error message if git unavailable
    """
    result = {"available": False, "branch": "", "status": "", "log": [], "diff_stat": "", "error": ""}

    # Check if this is a git repo
    out, err, rc = _run_git(["rev-parse", "--is-inside-work-tree"], project_path, wsl_distro)
    if rc != 0:
        result["error"] = "Not a git repository or git not available."
        return result

    result["available"] = True

    # Current branch
    out, _, _ = _run_git(["branch", "--show-current"], project_path, wsl_distro)
    result["branch"] = out.strip()

    # Short status
    out, _, _ = _run_git(["status", "--short"], project_path, wsl_distro)
    result["status"] = out.strip()

    # Recent commits
    out, _, _ = _run_git(
        ["log", "--oneline", "--format=%H|%s|%an|%ar", "-n", "10"],
        project_path,
        wsl_distro,
    )
    commits = []
    for line in out.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({
                "hash":    parts[0][:8],
                "message": parts[1],
                "author":  parts[2],
                "when":    parts[3],
            })
    result["log"] = commits

    # Diff stat (uncommitted changes summary)
    out, _, _ = _run_git(["diff", "--stat", "HEAD"], project_path, wsl_distro)
    result["diff_stat"] = out.strip()

    return result
