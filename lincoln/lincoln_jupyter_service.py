"""
Lincoln Jupyter Execution Service  v0.6.1
==========================================
Destination: B:\Homebrewed_AI\Lincoln\lincoln\lincoln_jupyter_service.py

Maintains a background Jupyter kernel for Python execution, and provides
direct WSL/subprocess runners for all other supported languages.

Execution matrix:
  Python                → Jupyter kernel (persistent, stateful)
  Fortran (f90/f95/...) → nvfortran via WSL2 + MKL, compiled + run
  C                     → gcc via WSL2, compiled + run
  C++                   → g++ via WSL2, compiled + run
  Julia                 → julia via WSL2
  R / RMarkdown         → Rscript via WSL2
  Bash / Shell          → bash via WSL2
  Maple                 → cmaple.exe (Windows, direct subprocess)

All WSL paths and tool locations are read from DB settings at call time
so they update immediately when the user edits them in Settings > Build Tools.
"""

import os
import queue
import logging
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

log = logging.getLogger("lincoln.jupyter_service")
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# ── DB settings helpers ───────────────────────────────────────────────────────

def _setting(key: str, default: str) -> str:
    """Read a single setting from the DB at call time (never cached)."""
    try:
        from lincoln.lincoln_database import get_all_settings
        return get_all_settings().get(key, default)
    except Exception:
        return default


def _wsl_distro() -> str:
    return _setting("wsl_distro", "Ubuntu")


def _nvfortran_path() -> str:
    return _setting("nvfortran_path", "/opt/nvidia/hpc_sdk/Linux_x86_64/26.3/compilers/bin/nvfortran")


def _f2py_flag() -> str:
    return _setting("f2py_fcompiler_flag", "nv")


def _maple_bin() -> str:
    return _setting("maple_path", r"D:\Maple\bin.X86_64_WINDOWS")


# ── WSL direct runner ─────────────────────────────────────────────────────────

def _run_wsl(cmd_parts: list[str], timeout: int = 60) -> str:
    """
    Run a command in WSL and return combined stdout+stderr as a string.
    cmd_parts is the command after 'wsl -d <distro> --'.
    """
    distro = _wsl_distro()
    full_cmd = ["wsl", "-d", distro, "--"] + cmd_parts
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout or ""
        err = result.stderr or ""
        if result.returncode != 0:
            return (out + ("\n❌ stderr:\n" + err if err.strip() else "")).strip()
        return (out + (err if err.strip() else "")).strip() or "(completed with no output)"
    except subprocess.TimeoutExpired:
        return f"❌ Timed out after {timeout}s"
    except FileNotFoundError:
        return "❌ WSL not found. Is WSL2 installed and the distro running?"
    except Exception as e:
        return f"❌ Execution error: {e}"


def _wsl_tmp_path(filename: str) -> tuple[str, str]:
    """
    Write content to a Windows temp file and return:
      (windows_path, wsl_path)  e.g. (C:/Users/.../tmp/foo.f90, /mnt/c/Users/.../tmp/foo.f90)
    """
    tmp_dir = Path(tempfile.gettempdir())
    win_path = tmp_dir / filename
    # Convert C:\Users\... → /mnt/c/users/...
    parts = win_path.parts  # ('C:\\', 'Users', ...)
    drive = parts[0].rstrip(":\\").lower()
    rest = "/".join(parts[1:]).replace("\\", "/")
    wsl_path = f"/mnt/{drive}/{rest}"
    return str(win_path), wsl_path


# ── Language runners ──────────────────────────────────────────────────────────

def _run_fortran(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    win_src, wsl_src = _wsl_tmp_path(f"lincoln_{uid}.f90")
    wsl_bin = wsl_src.replace(".f90", "")
    nvf = _nvfortran_path()

    # Write source with UNIX newlines
    Path(win_src).write_text(code, encoding="utf-8", newline="\n")

    # Compile
    compile_cmd = ["bash", "-ic", f'"{nvf}" -O2 -mp "{wsl_src}" -lmkl_rt -o "{wsl_bin}" 2>&1']
    compile_out = _run_wsl(compile_cmd, timeout=60)

    if "error" in compile_out.lower() and wsl_bin not in compile_out:
        return f"🔨 Compiling with nvfortran...\n\n❌ Compile failed:\n{compile_out}"

    # Run
    run_out = _run_wsl(["bash", "-ic", f'"{wsl_bin}"'], timeout=30)
    return f"🔨 Compiled with nvfortran + MKL\n{'─'*40}\n{run_out}"


def _run_c(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    win_src, wsl_src = _wsl_tmp_path(f"lincoln_{uid}.c")
    wsl_bin = wsl_src.replace(".c", "")
    Path(win_src).write_text(code, encoding="utf-8", newline="\n")

    compile_out = _run_wsl(["bash", "-c", f'gcc -O2 -o "{wsl_bin}" "{wsl_src}" 2>&1'], timeout=30)
    if compile_out and "error" in compile_out.lower():
        return f"🔨 Compiling with gcc...\n\n❌ Compile failed:\n{compile_out}"

    run_out = _run_wsl([wsl_bin], timeout=15)
    return f"🔨 Compiled with gcc\n{'─'*40}\n{run_out}"


def _run_cpp(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    win_src, wsl_src = _wsl_tmp_path(f"lincoln_{uid}.cpp")
    wsl_bin = wsl_src.replace(".cpp", "")
    Path(win_src).write_text(code, encoding="utf-8", newline="\n")

    compile_out = _run_wsl(["bash", "-c", f'g++ -O2 -std=c++17 -o "{wsl_bin}" "{wsl_src}" 2>&1'], timeout=30)
    if compile_out and "error" in compile_out.lower():
        return f"🔨 Compiling with g++...\n\n❌ Compile failed:\n{compile_out}"

    run_out = _run_wsl([wsl_bin], timeout=15)
    return f"🔨 Compiled with g++ (C++17)\n{'─'*40}\n{run_out}"


def _run_julia(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    win_src, wsl_src = _wsl_tmp_path(f"lincoln_{uid}.jl")
    Path(win_src).write_text(code, encoding="utf-8", newline="\n")
    return _run_wsl(["julia", "--color=no", wsl_src], timeout=60)


def _run_r(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    win_src, wsl_src = _wsl_tmp_path(f"lincoln_{uid}.R")
    Path(win_src).write_text(code, encoding="utf-8", newline="\n")
    return _run_wsl(["Rscript", "--vanilla", wsl_src], timeout=60)


def _run_bash(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    win_src, wsl_src = _wsl_tmp_path(f"lincoln_{uid}.sh")
    Path(win_src).write_text(code, encoding="utf-8", newline="\n")
    return _run_wsl(["bash", wsl_src], timeout=30)


def _run_maple(code: str) -> str:
    uid = uuid.uuid4().hex[:8]
    tmp_dir = Path(tempfile.gettempdir())
    src_path = tmp_dir / f"lincoln_{uid}.mpl"
    src_path.write_text(code, encoding="utf-8")

    maple_bin = Path(_maple_bin()) / "cmaple.exe"
    if not maple_bin.exists():
        return f"❌ cmaple.exe not found at {maple_bin}\nCheck Settings > Build Tools > Maple installation path."

    try:
        result = subprocess.run(
            [str(maple_bin), "-q", str(src_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = result.stdout or ""
        err = result.stderr or ""
        return (out + (err if err.strip() else "")).strip() or "(completed with no output)"
    except subprocess.TimeoutExpired:
        return "❌ Maple timed out after 60s"
    except Exception as e:
        return f"❌ Maple error: {e}"


# ── Router ────────────────────────────────────────────────────────────────────

_FORTRAN_LANGS = {"fortran", "f90", "f95", "f03", "f08", "f"}
_C_LANGS       = {"c"}
_CPP_LANGS     = {"cpp", "c++", "cxx"}
_JULIA_LANGS   = {"julia", "jl"}
_R_LANGS       = {"r", "rmarkdown", "rmd"}
_BASH_LANGS    = {"bash", "sh", "shell"}
_MAPLE_LANGS   = {"maple", "mpl", "mm"}
_PYTHON_LANGS  = {"python", "py", "ipython", "jupyter"}


# ── Jupyter kernel (Python) ───────────────────────────────────────────────────

class JupyterSandbox:
    def __init__(self):
        self.kernels = {}

    def get_kernel(self):
        kernel_name = "python3"
        if kernel_name not in self.kernels:
            import jupyter_client
            try:
                km, kc = jupyter_client.manager.start_new_kernel(kernel_name=kernel_name)
                self.kernels[kernel_name] = (km, kc)
                log.info("[Lincoln] Started Jupyter kernel: python3")
            except Exception as e:
                return None, f"Kernel failed to start: {e}"
        return self.kernels[kernel_name][1], ""

    def execute_python(self, code: str) -> str:
        kc, error = self.get_kernel()
        if not kc:
            return f"❌ Execution Error: {error}"

        kc.execute(code)
        output = []
        while True:
            try:
                msg      = kc.get_iopub_msg(timeout=30)
                msg_type = msg["header"]["msg_type"]
                content  = msg["content"]
                if msg_type == "stream":
                    output.append(content["text"])
                elif msg_type in ("execute_result", "display_data"):
                    if "text/plain" in content["data"]:
                        output.append(content["data"]["text/plain"])
                elif msg_type == "error":
                    output.append(ANSI_ESCAPE.sub("", "\n".join(content["traceback"])))
                elif msg_type == "status" and content["execution_state"] == "idle":
                    break
            except queue.Empty:
                output.append("\n[Timeout: execution took longer than 30s]")
                break

        result = "\n".join(output).strip()
        return result or "(Code executed successfully with no output)"


sandbox = JupyterSandbox()


def execute_code(code: str, language: str) -> str:
    """
    Route code to the correct executor based on language.
    Called by lincoln_routes_jupyter.py.
    """
    lang = (language or "python").lower().strip()

    if lang in _PYTHON_LANGS:
        return sandbox.execute_python(code)
    if lang in _FORTRAN_LANGS:
        return _run_fortran(code)
    if lang in _C_LANGS:
        return _run_c(code)
    if lang in _CPP_LANGS:
        return _run_cpp(code)
    if lang in _JULIA_LANGS:
        return _run_julia(code)
    if lang in _R_LANGS:
        return _run_r(code)
    if lang in _BASH_LANGS:
        return _run_bash(code)
    if lang in _MAPLE_LANGS:
        return _run_maple(code)

    return f"❌ Language '{language}' is not supported for direct execution.\nSupported: Python, Fortran, C, C++, Julia, R, Bash, Maple."
