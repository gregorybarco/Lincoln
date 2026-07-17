"""
Lincoln RAG Indexer
===================
Indexes Project 1 source files (Python + Fortran) into ChromaDB.
All model names and paths come from main_configuration — never hardcoded here.

Usage:
    python scripts\rag_indexer.py               # full index build
    python scripts\rag_indexer.py --dry-run     # list files, no embedding
    python scripts\rag_indexer.py --rebuild     # force re-embed all files
    python scripts\rag_indexer.py --status      # show index stats only
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main_configuration.config import (
    CHROMA_DB_PATH, CHUNK_OVERLAP, CHUNK_SIZE, COLLECTION_NAME,
    EMBED_MODEL, HASH_CACHE_PATH, LLM_MODEL, OLLAMA_BASE_URL, PROJECT_1_PATH,
)

# ── Security exclusions — mirrors Project 1 .gitignore exactly ────────────────

EXCLUDE_DIRS = {
    "__pycache__", ".git", "venv", "env", ".venv",
    "lib64",                                         # ← add this
    "build", "dist", ".eggs", "node_modules", ".idea", ".vscode",
    "tokens", "secrets",
    "0_documentation", "build_bridge", "training_weights",
    "01_raw", "02_interim", "03_parameters", "04_results", "data",
}

EXCLUDE_PATTERNS = {
    "*.csv", "*.parquet", "*.dat", "*.bin",
    "*.npy", "*.npz", "*.pkl", "*.h5", "*.hdf5",
    "*.so", "*.dll", "*.o", "*.obj", "*.mod", "*.smod",
    "*.lib", "*.a", "*.exe", "*.out", "*.pdb",
    "*.pt", "*.pth", "*.ckpt",
    ".env", ".env.*", "*.env",
    "*.key", "*.pem", "*.p12", "*.pfx", "*.crt", "*.cer",
    "*.json", "*.log", "*.suo", "*.user",
}

INCLUDE_EXTENSIONS = {".py", ".f90", ".f", ".for", ".f95", ".f03"}
FORTRAN_EXTENSIONS = {".f90", ".f", ".for", ".f95", ".f03"}

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("lincoln_rag")


# ── Helpers ───────────────────────────────────────────────────────────────────

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def load_hash_cache() -> dict:
    if HASH_CACHE_PATH.exists():
        with open(HASH_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_hash_cache(cache: dict):
    HASH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HASH_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def should_exclude(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    for pattern in EXCLUDE_PATTERNS:
        if path.match(pattern):
            return True
    return False

def collect_source_files(root: Path) -> list[Path]:
    files = []
    dirs_to_visit = [root]
    while dirs_to_visit:
        current = dirs_to_visit.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for p in entries:
            try:
                if p.is_symlink():
                    continue
                if p.is_dir():
                    if p.name not in EXCLUDE_DIRS:
                        dirs_to_visit.append(p)
                elif p.is_file():
                    if p.suffix.lower() in INCLUDE_EXTENSIONS and not should_exclude(p):
                        files.append(p)
            except OSError:
                continue
    return sorted(files)

def lang_of(f: Path) -> str:
    return "fortran" if f.suffix.lower() in FORTRAN_EXTENSIONS else "python"

def print_summary(files: list[Path]):
    py  = sum(1 for f in files if f.suffix == ".py")
    f90 = sum(1 for f in files if f.suffix.lower() in FORTRAN_EXTENSIONS)
    log.info(f"Total : {len(files)} files  ({py} Python, {f90} Fortran)")


# ── Dry run ───────────────────────────────────────────────────────────────────

def dry_run(root: Path):
    log.info(f"DRY RUN — scanning: {root}")
    log.info("Nothing will be embedded or written.")
    log.info("-" * 60)
    files = collect_source_files(root)
    if not files:
        log.warning("No files found. Check LINCOLN_PROJECT_PATH in .env")
        return
    for f in files:
        print(f"  [{lang_of(f):7s}]  {f.relative_to(root)}")
    log.info("-" * 60)
    print_summary(files)
    log.info("DRY RUN complete. Review above before running the full index.")


# ── Core pipeline ─────────────────────────────────────────────────────────────

def build_index(rebuild: bool = False):
    try:
        import chromadb
        from llama_index.core import Settings, VectorStoreIndex
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.core.schema import Document
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.llms.ollama import Ollama
        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.core import StorageContext
    except ImportError as e:
        log.error(f"Missing dependency: {e}")
        sys.exit(1)

    root = Path(PROJECT_1_PATH)
    if not root.exists():
        log.error(f"Project path not found: {root}")
        log.error("Set LINCOLN_PROJECT_PATH in .env")
        sys.exit(1)

    log.info(f"Embed model : {EMBED_MODEL}")
    log.info(f"LLM model   : {LLM_MODEL}")
    log.info(f"Ollama      : {OLLAMA_BASE_URL}")
    log.info(f"Project     : {root}")

    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_BASE_URL,
                                            ollama_additional_kwargs={"mirostat": 0})
    Settings.llm = Ollama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=120.0)
    Settings.node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    chroma_client     = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    chroma_collection = chroma_client.get_or_create_collection(COLLECTION_NAME)
    vector_store      = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context   = StorageContext.from_defaults(vector_store=vector_store)

    all_files = collect_source_files(root)
    print_summary(all_files)
    if not all_files:
        log.warning("No files found. Run --dry-run to debug.")
        return

    cache     = {} if rebuild else load_hash_cache()
    to_index  = []
    unchanged = 0
    for f in all_files:
        h = file_hash(f)
        if not rebuild and cache.get(str(f)) == h:
            unchanged += 1
        else:
            to_index.append(f)

    log.info(f"Unchanged : {unchanged}  |  To embed : {len(to_index)}")
    if not to_index:
        log.info("Index is up to date.")
        _print_stats(chroma_collection)
        return

    documents = []
    for f in to_index:
        try:
            documents.append(Document(
                text=f.read_text(encoding="utf-8", errors="replace"),
                metadata={"file_path": str(f.relative_to(root)),
                          "file_name": f.name,
                          "extension": f.suffix.lower(),
                          "language":  lang_of(f)},
                doc_id=str(f.relative_to(root)),
            ))
        except Exception as e:
            log.warning(f"Skipping {f.name}: {e}")

    log.info(f"Embedding {len(documents)} documents...")
    t0 = time.time()
    try:
        VectorStoreIndex.from_documents(documents, storage_context=storage_context,
                                         show_progress=True)
    except Exception as e:
        log.error(f"Indexing failed: {e}")
        log.error("Is Ollama running? Is nomic-embed-text pulled?")
        raise

    log.info(f"Embedded {len(documents)} files in {time.time() - t0:.1f}s")
    for f in to_index:
        cache[str(f)] = file_hash(f)
    save_hash_cache(cache)
    log.info(f"Hash cache updated — {len(cache)} entries")
    _print_stats(chroma_collection)
    log.info("Index complete. Lincoln can now query Project 1.")

def _print_stats(col):
    log.info(f"ChromaDB '{COLLECTION_NAME}': {col.count()} vectors stored")


# ── Status ────────────────────────────────────────────────────────────────────

def show_status():
    try:
        import chromadb
    except ImportError:
        log.error("chromadb not installed"); sys.exit(1)

    root = Path(PROJECT_1_PATH)
    log.info(f"LLM model    : {LLM_MODEL}")
    log.info(f"Embed model  : {EMBED_MODEL}")
    log.info(f"Project path : {root}  ({'exists' if root.exists() else 'NOT FOUND'})")
    log.info(f"ChromaDB     : {CHROMA_DB_PATH}  ({'exists' if Path(CHROMA_DB_PATH).exists() else 'not yet built'})")
    if Path(CHROMA_DB_PATH).exists():
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        try:
            log.info(f"Vectors      : {client.get_collection(COLLECTION_NAME).count()}")
        except Exception:
            log.info(f"Collection '{COLLECTION_NAME}' not yet created.")
    log.info(f"Hash cache   : {len(load_hash_cache())} files tracked")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lincoln RAG Indexer")
    parser.add_argument("--dry-run", action="store_true", help="List files without embedding")
    parser.add_argument("--rebuild", action="store_true", help="Force re-embed all files")
    parser.add_argument("--status",  action="store_true", help="Show index stats and exit")
    args = parser.parse_args()

    root = Path(PROJECT_1_PATH)
    if args.status:
        show_status()
    elif args.dry_run:
        if not root.exists():
            log.error(f"Project path not found: {root}")
            log.error("Set LINCOLN_PROJECT_PATH in .env")
            sys.exit(1)
        dry_run(root)
    else:
        build_index(rebuild=args.rebuild)

if __name__ == "__main__":
    main()
