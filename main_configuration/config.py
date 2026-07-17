"""
Lincoln — Central Configuration
================================
Single source of truth for all model names, paths, and tunables.

To swap models, set env vars in Lincoln's .env — no script changes needed:
    LINCOLN_LLM_MODEL=gemma4:12b
    LINCOLN_EMBED_MODEL=nomic-embed-text-v2-moe

WARNING: Changing LINCOLN_EMBED_MODEL requires a full index rebuild:
    python scripts\rag_indexer.py --rebuild
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load Lincoln's .env from the project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
# ── Paths ─────────────────────────────────────────────────────────────────────

LINCOLN_ROOT    = Path(__file__).resolve().parent.parent
SCRIPTS_DIR     = LINCOLN_ROOT / "scripts"
CHROMA_DB_PATH  = str(LINCOLN_ROOT / "data" / "chroma_db")
HASH_CACHE_PATH = LINCOLN_ROOT / "data" / "file_hashes.json"

# Set LINCOLN_PROJECT_PATH in .env — never hardcode a project path here
PROJECT_1_PATH  = os.getenv("LINCOLN_PROJECT_PATH", r"C:\path\to\your\Project1")

# ── Ollama ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

# ── Models — change in .env, not here ────────────────────────────────────────

LLM_MODEL   = os.getenv("LINCOLN_LLM_MODEL",  "qwen3.5:9b")
EMBED_MODEL = os.getenv("LINCOLN_EMBED_MODEL", "nomic-embed-text")

# ── RAG tunables ──────────────────────────────────────────────────────────────

COLLECTION_NAME = os.getenv("LINCOLN_COLLECTION",    "project1_source")
CHUNK_SIZE      = int(os.getenv("LINCOLN_CHUNK_SIZE",    "512"))
CHUNK_OVERLAP   = int(os.getenv("LINCOLN_CHUNK_OVERLAP", "50"))
DEFAULT_TOP_K   = int(os.getenv("LINCOLN_TOP_K",         "5"))
