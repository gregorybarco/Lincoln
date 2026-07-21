"""
Lincoln Cleanup Service  v0.6.0
================================
Runs at Flask startup to maintain data hygiene.

Owns:
  - Deleting old uploaded files from data/uploads/ based on retention_days setting
  - Detecting installed tool paths (nvfortran, Maple, oneAPI, WSL, Tesseract)
    and returning them for the Settings panel Build Tools section

Called by: lincoln/app/__init__.py after initialise_database()
"""

import os
import subprocess
import time
from pathlib import Path

from lincoln.lincoln_configuration import UPLOADS_DIR


def cleanup_old_uploads(retention_days: int = 30) -> int:
    """
    Delete files in data/uploads/ whose modification time is older than
    retention_days days. Returns the count of files deleted.
    Called once at startup -- no background thread needed.
    """
    if not UPLOADS_DIR.exists():
        return 0

    cutoff_seconds = retention_days * 86400
    now = time.time()
    deleted = 0

    for file_path in UPLOADS_DIR.iterdir():
        try:
            if file_path.is_file():
                age = now - file_path.stat().st_mtime
                if age > cutoff_seconds:
                    file_path.unlink()
                    deleted += 1
        except OSError:
            pass

    if deleted:
        print(f"[Lincoln] Cleanup: removed {deleted} upload file(s) older than {retention_days} days.")

    return deleted


def detect_tool_paths() -> dict:
    """
    Detect installed tool paths for the Settings panel Build Tools section.
    All detection is read-only and non-destructive.
    Returns a dict of tool -> {path, found, note}.
    """
    tools = {}

    # nvfortran -- check via WSL
    nvfortran_path = "/opt/nvidia/hpc_sdk/Linux_x86_64/26.3/compilers/bin/nvfortran"
    try:
        result = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "test", "-f", nvfortran_path],
            capture_output=True,
            timeout=5,
        )
        tools["nvfortran"] = {
            "path":  nvfortran_path,
            "found": result.returncode == 0,
            "note":  "NVIDIA HPC SDK Fortran compiler (WSL path)",
        }
    except Exception:
        tools["nvfortran"] = {
            "path":  nvfortran_path,
            "found": False,
            "note":  "WSL not reachable for detection",
        }

    # Maple -- Windows path
    maple_exe = Path("D:/Maple/bin.X86_64_WINDOWS/maplew.exe")
    tools["maple"] = {
        "path":  str(maple_exe),
        "found": maple_exe.exists(),
        "note":  "Maple 2025.2 GUI executable",
    }

    maple_cli = Path("D:/Maple/bin.X86_64_WINDOWS/cmaple.exe")
    tools["cmaple"] = {
        "path":  str(maple_cli),
        "found": maple_cli.exists(),
        "note":  "Maple 2025.2 CLI kernel (used for canvas block execution)",
    }

    # Intel oneAPI
    oneapi_root = Path("C:/Program Files (x86)/Intel/oneAPI")
    mkl_root    = oneapi_root / "mkl" / "latest"
    tools["oneapi"] = {
        "path":  str(oneapi_root),
        "found": oneapi_root.exists(),
        "note":  "Intel oneAPI root",
    }
    tools["mkl"] = {
        "path":  str(mkl_root),
        "found": mkl_root.exists(),
        "note":  "Intel MKL (linked by nvfortran via -lmkl_rt)",
    }

    # Tesseract OCR -- check if available in PATH or WSL
    try:
        result = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "which", "tesseract"],
            capture_output=True,
            timeout=5,
        )
        tess_path = result.stdout.decode().strip() if result.returncode == 0 else ""
        tools["tesseract"] = {
            "path":  tess_path or "/usr/bin/tesseract",
            "found": result.returncode == 0,
            "note":  "Tesseract OCR (WSL). Install: sudo apt install tesseract-ocr",
        }
    except Exception:
        tools["tesseract"] = {
            "path":  "/usr/bin/tesseract",
            "found": False,
            "note":  "Not detected",
        }

    # WSL itself
    try:
        result = subprocess.run(
            ["wsl", "--version"],
            capture_output=True,
            timeout=5,
        )
        tools["wsl"] = {
            "path":  "wsl.exe",
            "found": result.returncode == 0,
            "note":  "Windows Subsystem for Linux",
        }
    except Exception:
        tools["wsl"] = {
            "path":  "wsl.exe",
            "found": False,
            "note":  "WSL not found in PATH",
        }

    # Git -- via WSL
    try:
        result = subprocess.run(
            ["wsl", "-d", "Ubuntu", "--", "which", "git"],
            capture_output=True,
            timeout=5,
        )
        git_path = result.stdout.decode().strip() if result.returncode == 0 else ""
        tools["git"] = {
            "path":  git_path or "/usr/bin/git",
            "found": result.returncode == 0,
            "note":  "Git (WSL)",
        }
    except Exception:
        tools["git"] = {
            "path":  "/usr/bin/git",
            "found": False,
            "note":  "Not detected",
        }

    return tools
