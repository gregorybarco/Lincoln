"""
Lincoln Configuration Loader
=============================
Loads and validates Lincoln's infrastructure configuration from .env.

Owns:
  - Ollama connection details
  - Default LLM model (overridable per session from the UI model selector)
  - Embed model (fixed — changing requires full re-index of every project)
  - RAG chunk size (affects index structure, set before first index build)
  - Web UI host and port

Does NOT own:
  - Project paths, names, or ChromaDB collection names
    → managed by lincoln_database.py, created and edited from the UI
  - Chat history, session state, or UI preferences
    → managed by lincoln_database.py
  - MLflow configuration (stubbed here, wired in a future session)

Rule: No other file in Lincoln ever calls os.getenv() directly.
      All environment access flows through this module.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Locate and load .env ──────────────────────────────────────────────────────
# This file lives at lincoln\lincoln_configuration.py
# .env lives at the project root (two levels up)

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _require(key: str) -> str:
    """
    Read a required environment variable.
    Exits loudly at startup if missing — silent failures waste hours of debugging.
    """
    val = os.getenv(key, "").strip()
    if not val:
        print(f"\n[Lincoln] FATAL: Required environment variable '{key}' is not set.")
        print(f"[Lincoln] Expected in: {_ENV_PATH}")
        print(f"[Lincoln] Lincoln cannot start without this value.\n")
        sys.exit(1)
    return val


def _optional(key: str, default: str) -> str:
    """Read an optional environment variable, returning default if absent."""
    return os.getenv(key, default).strip()


def _optional_int(key: str, default: int) -> int:
    """Read an optional integer environment variable with a fallback default."""
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(
            f"[Lincoln] WARNING: '{key}' must be an integer, "
            f"got '{raw}'. Using default: {default}."
        )
        return default


# ── Filesystem paths ──────────────────────────────────────────────────────────

# Project root — the parent of the lincoln\ package folder
LINCOLN_ROOT = Path(__file__).resolve().parent.parent

# Sub-directories — created on first use by the services that own them
DATA_DIR         = LINCOLN_ROOT / "data"
CHROMA_DB_PATH   = str(DATA_DIR / "chroma_db")
HASHES_DIR       = DATA_DIR / "hashes"
LOGS_DIR         = DATA_DIR / "logs"
DB_PATH          = DATA_DIR / "lincoln_database.db"
BIN_DIR          = LINCOLN_ROOT / "bin"


# ── Ollama connection ─────────────────────────────────────────────────────────

OLLAMA_BASE_URL = _optional("OLLAMA_API_BASE", "http://localhost:11434")


# ── LLM model ─────────────────────────────────────────────────────────────────
# Default model loaded on startup.
# The UI model selector overrides this per session by reading
# available models live from Ollama's /api/tags endpoint.
# To change the startup default, edit LINCOLN_LLM_MODEL in .env.

LLM_MODEL = _require("LINCOLN_LLM_MODEL")


# ── Embedding model ───────────────────────────────────────────────────────────
# Treat as fixed infrastructure — do not expose as a UI-selectable option.
#
# Changing this value invalidates every ChromaDB collection in data\chroma_db\.
# Every project must be fully re-indexed if this value ever changes.
# This is a deliberate migration event, not a casual configuration change.

EMBED_MODEL = _require("LINCOLN_EMBED_MODEL")


# ── RAG tunables ──────────────────────────────────────────────────────────────
# CHUNK_SIZE affects how source files are split before embedding.
# Set this before building the first index — changing it mid-project
# requires a --rebuild to apply consistently.
#
# CHUNK_OVERLAP and DEFAULT_TOP_K are sensible fixed defaults.
# They are not exposed in the UI to avoid accidental misconfiguration.

CHUNK_SIZE    = _optional_int("LINCOLN_CHUNK_SIZE", 512)
CHUNK_OVERLAP = 50
DEFAULT_TOP_K = 5


# ── Web UI ────────────────────────────────────────────────────────────────────
# UI_HOST is always 127.0.0.1 — Lincoln is never exposed to the network.
# UI_PORT is configurable in .env if 5000 conflicts with another local service.

UI_HOST = "127.0.0.1"
UI_PORT = _optional_int("LINCOLN_UI_PORT", 5000)


# ── MLflow (stubbed — wired in the MLflow session) ───────────────────────────
# Keys are present and commented out in .env.
# These values will be empty strings until MLflow is configured.

MLFLOW_TRACKING_URI  = _optional("MLFLOW_TRACKING_URI",  "")
MLFLOW_ARTIFACT_ROOT = _optional("MLFLOW_ARTIFACT_ROOT", "")


# ── Startup diagnostics ───────────────────────────────────────────────────────

def print_startup_summary():
    """
    Print a clean human-readable summary of loaded infrastructure config.
    Called by bin\lincoln.bat before Flask starts.
    Project list is not shown here — it comes from lincoln_database.py at runtime.
    """
    from lincoln import __version__, __codename__

    print(f"\n{'═' * 55}")
    print(f"  Lincoln v{__version__} — {__codename__}")
    print(f"{'═' * 55}")
    print(f"  Ollama      : {OLLAMA_BASE_URL}")
    print(f"  LLM model   : {LLM_MODEL}  (default · overridable in UI)")
    print(f"  Embed model : {EMBED_MODEL}  (fixed)")
    print(f"  Chunk size  : {CHUNK_SIZE}")
    print(f"  UI          : http://{UI_HOST}:{UI_PORT}")
    print(f"  Database    : {DB_PATH}")
    print(f"  ChromaDB    : {CHROMA_DB_PATH}")
    if MLFLOW_TRACKING_URI:
        print(f"  MLflow      : {MLFLOW_TRACKING_URI}")
    else:
        print(f"  MLflow      : not configured (future session)")
    print(f"{'═' * 55}")
    print(f"  Projects and settings are managed via the UI")
    print(f"  Opening http://{UI_HOST}:{UI_PORT} ...")
    print(f"{'═' * 55}\n")
