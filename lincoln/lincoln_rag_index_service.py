"""
Lincoln RAG Index Service
=========================
Owns all ChromaDB and LlamaIndex interactions for Lincoln.

Owns:
  - Building and updating ChromaDB vector indexes for projects
  - Querying project indexes and returning ranked source chunks
  - File collection and hash-based incremental indexing
  - Security exclusion rules (no secrets, no binaries, no data files)

Rules:
  - No route or other service imports ChromaDB or LlamaIndex directly.
    All vector store interactions flow through this module.
  - Project data (path, collection name) always comes from lincoln_database.py.
    This service never reads project config from .env or hardcoded values.
  - The embed model is fixed at the value from lincoln_configuration.py.
    This service never accepts an embed model as a parameter.
  - Hash caches are stored per-project in data\hashes\ so incremental
    re-indexing only processes files that have changed since the last run.

Used by:
  - lincoln\app\routes\lincoln_routes_projects.py  (index build triggered from UI)
  - lincoln\app\routes\lincoln_routes_chat.py      (RAG query on each chat message)
  - bin\lincoln_rag_query.bat                      (terminal query shortcut)
  - bin\lincoln_rag_indexer.bat                    (terminal index shortcut)
"""

import hashlib
import json
import logging
import time
from pathlib import Path

from lincoln.lincoln_configuration import (
    CHROMA_DB_PATH,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DEFAULT_TOP_K,
    EMBED_MODEL,
    HASHES_DIR,
    LLM_MODEL,
    OLLAMA_BASE_URL,
)

log = logging.getLogger("lincoln.rag_index_service")


# ── File collection rules ─────────────────────────────────────────────────────
# These exclusion rules mirror the OptionsPricing .gitignore exactly.
# They apply to all projects — no secrets, binaries, or data files reach
# the embedding pipeline regardless of which project is being indexed.

_EXCLUDE_DIRS = {
    "__pycache__", ".git", "venv", "env", ".venv", "lib64",
    "build", "dist", ".eggs", "node_modules", ".idea", ".vscode",
    "tokens", "secrets", "0_documentation", "build_bridge",
    "training_weights", "01_raw", "02_interim", "03_parameters",
    "04_results", "data",
}

_EXCLUDE_PATTERNS = {
    "*.csv", "*.parquet", "*.dat", "*.bin",
    "*.npy", "*.npz", "*.pkl", "*.h5", "*.hdf5",
    "*.so", "*.dll", "*.o", "*.obj", "*.mod", "*.smod",
    "*.lib", "*.a", "*.exe", "*.out", "*.pdb",
    "*.pt", "*.pth", "*.ckpt",
    ".env", ".env.*", "*.env",
    "*.key", "*.pem", "*.p12", "*.pfx", "*.crt", "*.cer",
    "*.json", "*.log", "*.suo", "*.user",
}

_INCLUDE_EXTENSIONS = {".py", ".f90", ".f", ".for", ".f95", ".f03", ".md"}
_FORTRAN_EXTENSIONS = {".f90", ".f", ".for", ".f95", ".f03"}


# ── Internal file utilities ───────────────────────────────────────────────────

def _compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file for incremental indexing."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_hash_cache_path(project_name: str) -> Path:
    """Return the path to the per-project hash cache file."""
    HASHES_DIR.mkdir(parents=True, exist_ok=True)
    return HASHES_DIR / f"lincoln_hashes_{project_name}.json"


def _load_hash_cache(project_name: str) -> dict:
    cache_path = _get_hash_cache_path(project_name)
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_hash_cache(project_name: str, cache: dict):
    cache_path = _get_hash_cache_path(project_name)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _should_exclude(path: Path) -> bool:
    """Return True if this file should be excluded from indexing."""
    for part in path.parts:
        if part in _EXCLUDE_DIRS:
            return True
    for pattern in _EXCLUDE_PATTERNS:
        if path.match(pattern):
            return True
    return False


def _get_language(file_path: Path) -> str:
    """Return the language label for a source file."""
    suffix = file_path.suffix.lower()
    if suffix in _FORTRAN_EXTENSIONS:
        return "fortran"
    if suffix == ".md":
        return "markdown"
    return "python"


def collect_indexable_files(project_path: Path) -> list[Path]:
    """
    Walk a project directory and collect all files eligible for indexing.
    Applies security exclusion rules — no secrets, binaries, or data files.

    Args:
        project_path : Root directory of the project to scan

    Returns:
        Sorted list of eligible file paths
    """
    files          = []
    dirs_to_visit  = [project_path]

    while dirs_to_visit:
        current = dirs_to_visit.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if entry.name not in _EXCLUDE_DIRS:
                        dirs_to_visit.append(entry)
                elif entry.is_file():
                    if (
                        entry.suffix.lower() in _INCLUDE_EXTENSIONS
                        and not _should_exclude(entry)
                    ):
                        files.append(entry)
            except OSError:
                continue

    return sorted(files)


# ── Index build ───────────────────────────────────────────────────────────────

def build_project_index(project: dict, force_rebuild: bool = False) -> int:
    """
    Build or incrementally update the ChromaDB vector index for a project.
    Only files that have changed since the last index run are re-embedded.

    Args:
        project       : Project dict from lincoln_database.get_project_by_id()
                        Required keys: id, name, display_name, path, collection
        force_rebuild : If True, re-embed all files regardless of hash cache.
                        Use when switching embed models (full rebuild required).

    Returns:
        Total vector count in the collection after indexing.

    Raises:
        FileNotFoundError : If the project path does not exist on disk.
        ImportError       : If ChromaDB or LlamaIndex dependencies are missing.
    """
    import chromadb
    from llama_index.core import Settings, StorageContext, VectorStoreIndex
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.schema import Document
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.chroma import ChromaVectorStore

    project_path = Path(project["path"])
    collection   = project["collection"]
    project_name = project["name"]

    if not project_path.exists():
        raise FileNotFoundError(
            f"Project path does not exist: {project_path}\n"
            f"Update the project path from the Lincoln UI."
        )

    log.info(f"Building index for project '{project['display_name']}'")
    log.info(f"  Path       : {project_path}")
    log.info(f"  Collection : {collection}")
    log.info(f"  Embed      : {EMBED_MODEL}")
    log.info(f"  Chunk size : {CHUNK_SIZE}  overlap: {CHUNK_OVERLAP}")

    # Configure LlamaIndex settings
    Settings.embed_model = OllamaEmbedding(
        model_name=EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
        ollama_additional_kwargs={"mirostat": 0},
    )
    Settings.llm = Ollama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        request_timeout=120.0,
    )
    Settings.node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    # Connect to ChromaDB collection
    Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    chroma_client     = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    chroma_collection = chroma_client.get_or_create_collection(collection)
    vector_store      = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context   = StorageContext.from_defaults(vector_store=vector_store)

    # Collect and filter files
    all_files = collect_indexable_files(project_path)
    py_count  = sum(1 for f in all_files if f.suffix == ".py")
    f90_count = sum(1 for f in all_files if f.suffix.lower() in _FORTRAN_EXTENSIONS)
    md_count  = sum(1 for f in all_files if f.suffix.lower() == ".md")
    log.info(f"  Files found: {len(all_files)} ({py_count} Python, {f90_count} Fortran, {md_count} Markdown)")

    if not all_files:
        log.warning("No indexable files found. Check project path and exclusion rules.")
        return chroma_collection.count()

    # Determine which files need re-embedding
    hash_cache = {} if force_rebuild else _load_hash_cache(project_name)
    to_index   = []
    unchanged  = 0

    for file_path in all_files:
        file_hash = _compute_file_hash(file_path)
        if not force_rebuild and hash_cache.get(str(file_path)) == file_hash:
            unchanged += 1
        else:
            to_index.append(file_path)

    log.info(f"  Unchanged: {unchanged}  |  To embed: {len(to_index)}")

    if not to_index:
        count = chroma_collection.count()
        log.info(f"  Index is up to date. Vectors: {count}")
        return count

    # Build document objects
    documents = []
    for file_path in to_index:
        try:
            documents.append(Document(
                text=file_path.read_text(encoding="utf-8", errors="replace"),
                metadata={
                    "file_path":    str(file_path.relative_to(project_path)),
                    "file_name":    file_path.name,
                    "extension":    file_path.suffix.lower(),
                    "language":     _get_language(file_path),
                    "project_name": project_name,
                },
                doc_id=f"{project_name}::{file_path.relative_to(project_path)}",
            ))
        except Exception as e:
            log.warning(f"  Skipping {file_path.name}: {e}")

    # Embed and store
    log.info(f"  Embedding {len(documents)} documents...")
    start_time = time.time()
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )
    elapsed = time.time() - start_time
    log.info(f"  Embedded in {elapsed:.1f}s")

    # Update hash cache
    for file_path in to_index:
        hash_cache[str(file_path)] = _compute_file_hash(file_path)
    _save_hash_cache(project_name, hash_cache)

    count = chroma_collection.count()
    log.info(f"  Index complete. Vectors: {count}")
    return count


# ── Index query ───────────────────────────────────────────────────────────────

def query_project_index(
    question:     str,
    collection:   str,
    project_name: str = "",
    top_k:        int = DEFAULT_TOP_K,
) -> dict:
    """
    Query a project's ChromaDB index and return the answer with source references.

    Args:
        question     : Natural language question
        collection   : ChromaDB collection name (from project dict)
        project_name : Display name for logging (optional)
        top_k        : Number of source chunks to retrieve (default from config)

    Returns:
        Dict with keys:
          answer  : str — synthesized answer from the LLM
          sources : list of dicts — each with file_path, language, score, snippet

    Raises:
        FileNotFoundError : If ChromaDB does not exist at CHROMA_DB_PATH
        ValueError        : If the collection has not been indexed yet
    """
    import chromadb
    from llama_index.core import Settings, StorageContext, VectorStoreIndex
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.chroma import ChromaVectorStore

    if not Path(CHROMA_DB_PATH).exists():
        raise FileNotFoundError(
            f"ChromaDB not found at {CHROMA_DB_PATH}. "
            f"Index this project first from the Lincoln UI."
        )

    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    Settings.llm         = Ollama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=180.0)

    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        chroma_collection = chroma_client.get_collection(collection)
    except Exception:
        raise ValueError(
            f"Collection '{collection}' has not been indexed yet. "
            f"Index this project from the Lincoln UI first."
        )

    vector_store    = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index           = VectorStoreIndex.from_vector_store(
        vector_store,
        storage_context=storage_context,
    )
    query_engine = index.as_query_engine(
        similarity_top_k=top_k,
        response_mode="compact",
    )

    log.info(f"RAG query | project: {project_name} | top_k: {top_k}")
    log.info(f"  Question: {question!r}")

    response = query_engine.query(question)
    answer   = str(response)

    sources = []
    if hasattr(response, "source_nodes"):
        for node in response.source_nodes:
            meta = node.metadata
            sources.append({
                "file_path": meta.get("file_path", "unknown"),
                "file_name": meta.get("file_name", "unknown"),
                "language":  meta.get("language", "unknown"),
                "score":     round(getattr(node, "score", 0) or 0, 3),
                "snippet":   node.text[:300].replace("\n", " "),
            })

    log.info(f"  Answer generated. Sources: {len(sources)}")
    return {"answer": answer, "sources": sources}


# ── Dry run — file preview ────────────────────────────────────────────────────

def dry_run_project(project: dict) -> dict:
    """
    Preview which files would be indexed for a project without embedding anything.
    Used by the UI to show a file count preview before triggering an index build.

    Args:
        project : Project dict from lincoln_database

    Returns:
        Dict with keys: files (list of file info dicts), total, by_language
    """
    project_path = Path(project["path"])

    if not project_path.exists():
        return {"error": f"Path does not exist: {project_path}"}

    all_files   = collect_indexable_files(project_path)
    file_infos  = []
    by_language = {}

    for file_path in all_files:
        lang = _get_language(file_path)
        by_language[lang] = by_language.get(lang, 0) + 1
        file_infos.append({
            "path":     str(file_path.relative_to(project_path)),
            "name":     file_path.name,
            "language": lang,
        })

    return {
        "files":       file_infos,
        "total":       len(file_infos),
        "by_language": by_language,
    }
