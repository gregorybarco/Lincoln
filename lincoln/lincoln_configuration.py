"""
Lincoln Configuration Loader  v0.6.0
======================================
Loads and validates Lincoln's infrastructure configuration from .env.

Owns:
  - Ollama connection details
  - Default LLM model (overridable per session from the UI model selector)
  - Embed model (fixed -- changing requires full re-index of every project)
  - RAG chunk size
  - Web UI host and port
  - VRAM cap for context window sizing

Does NOT own:
  - Project paths, names, or ChromaDB collection names (lincoln_database.py)
  - Chat history, session state, or UI preferences (lincoln_database.py)
  - User-editable settings like top_k, history_limit (lincoln_database.py)

Rule: No other file in Lincoln ever calls os.getenv() directly.
      All environment access flows through this module.

Admin write-back: write_env_key() allows the settings UI (admin mode) to
update .env values. Requires a restart to take effect. Never writes
arbitrary keys -- only the allowlisted infrastructure keys.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Locate and load .env ──────────────────────────────────────────────────────

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        print(f"\n[Lincoln] FATAL: Required environment variable '{key}' is not set.")
        print(f"[Lincoln] Expected in: {_ENV_PATH}")
        print(f"[Lincoln] Lincoln cannot start without this value.\n")
        sys.exit(1)
    return val


def _optional(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _optional_int(key: str, default: int) -> int:
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

LINCOLN_ROOT   = Path(__file__).resolve().parent.parent
DATA_DIR       = LINCOLN_ROOT / "data"
CHROMA_DB_PATH = str(DATA_DIR / "chroma_db")
HASHES_DIR     = DATA_DIR / "hashes"
LOGS_DIR       = DATA_DIR / "logs"
DB_PATH        = DATA_DIR / "lincoln_database.db"
BIN_DIR        = LINCOLN_ROOT / "bin"
UPLOADS_DIR    = DATA_DIR / "uploads"


# ── Ollama connection ─────────────────────────────────────────────────────────

OLLAMA_BASE_URL = _optional("OLLAMA_API_BASE", "http://localhost:11434")

# ── Google Custom Search API (web search fallback) ────────────────────────────
# Used as fallback when DuckDuckGo rate-limits or times out.
# SafeSearch is hardcoded to 'active' in lincoln_web_search.py — these keys
# only control which account/engine is used, not safety settings.
#
# Free tier: 100 queries/day. No billing setup needed for under 100/day.
# Setup: console.cloud.google.com → Custom Search JSON API → create key
#         cse.google.com → new engine → enable "Search the entire web" → copy cx

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID:  str = os.getenv("GOOGLE_CSE_ID",  "")


# ── Startup summary addition ──────────────────────────────────────────────────
# Add these lines to your existing startup_summary() or print block:
#
#   google_status = "configured" if GOOGLE_API_KEY and GOOGLE_CSE_ID else "not configured (DDG only)"
#   print(f"  Google Search : {google_status}")
#
# This prints at launch so you can confirm keys are loaded without exposing them.

# ── LLM model ─────────────────────────────────────────────────────────────────

LLM_MODEL = _require("LINCOLN_LLM_MODEL")


# ── Embedding model ───────────────────────────────────────────────────────────

EMBED_MODEL = _require("LINCOLN_EMBED_MODEL")


# ── RAG tunables ──────────────────────────────────────────────────────────────

CHUNK_SIZE    = _optional_int("LINCOLN_CHUNK_SIZE", 512)
CHUNK_OVERLAP = 50
DEFAULT_TOP_K = 5


# ── Web UI ────────────────────────────────────────────────────────────────────

UI_HOST = "127.0.0.1"
UI_PORT = _optional_int("LINCOLN_UI_PORT", 5000)


# ── VRAM cap -- fixed: use _optional() not os.getenv() directly ──────────────

OLLAMA_VRAM_GB = float(_optional("LINCOLN_VRAM_GB", "16"))


# ── MLflow (stubbed) ──────────────────────────────────────────────────────────

MLFLOW_TRACKING_URI  = _optional("MLFLOW_TRACKING_URI",  "")
MLFLOW_ARTIFACT_ROOT = _optional("MLFLOW_ARTIFACT_ROOT", "")


# ── Admin env write-back ──────────────────────────────────────────────────────

# Only these keys may be written back to .env from the admin settings UI.
# This is a hard allowlist -- never write arbitrary keys.
_ENV_ADMIN_ALLOWLIST = {
    "OLLAMA_API_BASE",
    "LINCOLN_LLM_MODEL",
    "LINCOLN_EMBED_MODEL",
    "LINCOLN_CHUNK_SIZE",
    "LINCOLN_UI_PORT",
    "LINCOLN_VRAM_GB",
}

"""
lincoln_configuration.py  — v0.7.0 ADDITIONS ONLY
===================================================
Add these lines to your existing lincoln_configuration.py,
alongside the existing OLLAMA_BASE_URL, LLM_MODEL etc. entries.

Also add GOOGLE_API_KEY and GOOGLE_CSE_ID to your .env file:

  GOOGLE_API_KEY=your_api_key_here
  GOOGLE_CSE_ID=your_search_engine_id_here

These are read at startup and printed in the startup summary
(masked so they don't appear in full in terminal output).
"""

import os


def write_env_key(key: str, value: str) -> bool:
    """
    Write a single key-value pair back to .env.
    Only allowlisted infrastructure keys are accepted.
    Returns True on success, False if the key is not allowlisted.
    A restart is required for the change to take effect.
    """
    if key not in _ENV_ADMIN_ALLOWLIST:
        return False

    value = value.strip()
    env_text = _ENV_PATH.read_text(encoding="utf-8") if _ENV_PATH.exists() else ""
    lines = env_text.splitlines()

    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def get_all_env_values() -> dict:
    """
    Return all infrastructure .env values for the admin settings panel.
    All values are displayed in the UI -- nothing hidden.
    """
    return {
        "OLLAMA_API_BASE":    OLLAMA_BASE_URL,
        "LINCOLN_LLM_MODEL":  LLM_MODEL,
        "LINCOLN_EMBED_MODEL": EMBED_MODEL,
        "LINCOLN_CHUNK_SIZE": str(CHUNK_SIZE),
        "LINCOLN_UI_PORT":    str(UI_PORT),
        "LINCOLN_VRAM_GB":    str(OLLAMA_VRAM_GB),
    }


# ── Startup diagnostics ───────────────────────────────────────────────────────

def print_startup_summary():
    from lincoln import __version__, __codename__

    print(f"\n{'=' * 55}")
    print(f"  Lincoln v{__version__} -- {__codename__}")
    print(f"{'=' * 55}")
    print(f"  Ollama      : {OLLAMA_BASE_URL}")
    print(f"  LLM model   : {LLM_MODEL}  (default, overridable in UI)")
    print(f"  Embed model : {EMBED_MODEL}  (fixed)")
    print(f"  Chunk size  : {CHUNK_SIZE}")
    print(f"  VRAM cap    : {OLLAMA_VRAM_GB} GB  (ctx window sizing)")
    print(f"  UI          : http://{UI_HOST}:{UI_PORT}")
    print(f"  Database    : {DB_PATH}")
    print(f"  ChromaDB    : {CHROMA_DB_PATH}")
    print(f"  Uploads     : {UPLOADS_DIR}")
    if MLFLOW_TRACKING_URI:
        print(f"  MLflow      : {MLFLOW_TRACKING_URI}")
    else:
        print(f"  MLflow      : not configured")
    print(f"{'=' * 55}")
    print(f"  All settings visible and editable via the UI Settings panel.")
    print(f"  Opening http://{UI_HOST}:{UI_PORT} ...")
    print(f"{'=' * 55}\n")
