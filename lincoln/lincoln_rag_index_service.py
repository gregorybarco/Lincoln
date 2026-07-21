"""
Lincoln RAG Index Service  v0.6.0
===================================
Owns all ChromaDB and LlamaIndex interactions for Lincoln.

Changes in v0.6.0:
  - BUG FIX (B2): build_project_index() and dry_run_project() now use 'path'
    as the RAG source. 'code_path' is the Aider edit target, NOT the index root.
    Fallback to code_path only when path == '.' and code_path is explicitly set.
  - Switched from query_engine.query() to retrieval-only (retriever.retrieve()).
    Eliminates the hidden second LLM call on every RAG query. Reduces latency
    and removes a silent failure point.
  - Added language extensions: Julia, R, MATLAB, Mathematica, Maple, SAS, Stata,
    GAMS, AMPL, LP/MPS, Wolfram Language, RMarkdown.
  - rag_snippet_chars read from DB settings (configurable from UI).
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

_EXCLUDE_DIRS = {
    "__pycache__", ".git", "venv", "env", ".venv", "lib64",
    "build", "dist", ".eggs", "node_modules", ".idea", ".vscode",
    "tokens", "secrets", "0_documentation", "build_bridge",
    "training_weights", "01_raw", "02_interim", "03_parameters",
    "04_results", ".next", ".nuxt", "coverage", ".cache",
    "CMakeFiles", "x64", "x86", "Debug", "Release",
    "_tmp_build", "built_outputs",
}

_EXCLUDE_PATTERNS = {
    # Data and binary formats
    "*.csv", "*.parquet", "*.dat", "*.bin",
    "*.npy", "*.npz", "*.pkl", "*.h5", "*.hdf5",
    # Compiled outputs
    "*.so", "*.dll", "*.o", "*.obj", "*.mod", "*.smod",
    "*.lib", "*.a", "*.exe", "*.out", "*.pdb", "*.class",
    "*.pyc", "*.pyo",
    # ML weights
    "*.pt", "*.pth", "*.ckpt", "*.onnx",
    # Secrets
    ".env", ".env.*", "*.env",
    "*.key", "*.pem", "*.p12", "*.pfx", "*.crt", "*.cer",
    # Noise
    "*.log", "*.suo", "*.user", "*.lock",
    # Large generated files
    "package-lock.json", "yarn.lock", "*.min.js", "*.min.css",
    "*.map",
}

_INCLUDE_EXTENSIONS = {
    # Python
    ".py", ".pyi",
    # Fortran
    ".f90", ".f", ".for", ".f95", ".f03", ".f08", ".fpp",
    # C / C++
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
    # Java / Kotlin / Scala
    ".java", ".kt", ".kts", ".scala",
    # JavaScript / TypeScript
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".svelte", ".vue",
    # C# / F# / VB
    ".cs", ".fs", ".fsx", ".vb",
    # Go / Rust / Swift / Zig
    ".go", ".rs", ".swift", ".zig",
    # Shell / scripting
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    # Config and data
    ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".xml", ".gradle", ".cmake",
    # Docs / markdown
    ".md", ".rst", ".txt", ".tex",
    # SQL
    ".sql",
    # Ruby / PHP / Perl / Lua / R
    ".rb", ".php", ".pl", ".lua", ".r",
    # Julia
    ".jl",
    # MATLAB / Octave
    ".m",
    # Mathematica / Wolfram
    ".nb", ".wl",
    # R extended
    ".Rmd", ".rmd",
    # Stats / Econometrics
    ".sas", ".do", ".ado",
    # Optimisation
    ".gms", ".ampl", ".lp", ".mps",
    # Maple
    ".mw", ".mpl", ".maple", ".mm",
    # LaTeX / BibTeX
    ".latex", ".bib",
}

_LANG_MAP = {
    ".py": "python",      ".pyi": "python",
    ".f90": "fortran",    ".f": "fortran",   ".for": "fortran",
    ".f95": "fortran",    ".f03": "fortran", ".f08": "fortran", ".fpp": "fortran",
    ".c": "c",            ".cc": "cpp",      ".cpp": "cpp",     ".cxx": "cpp",
    ".h": "c/cpp",        ".hh": "cpp",      ".hpp": "cpp",     ".hxx": "cpp",
    ".java": "java",      ".kt": "kotlin",   ".scala": "scala",
    ".js": "javascript",  ".mjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript",  ".tsx": "typescript",
    ".html": "html",      ".htm": "html",
    ".css": "css",        ".scss": "scss",   ".sass": "sass",
    ".cs": "csharp",      ".fs": "fsharp",
    ".go": "go",          ".rs": "rust",     ".swift": "swift",
    ".sh": "shell",       ".bash": "shell",  ".ps1": "powershell",
    ".bat": "batch",      ".cmd": "batch",
    ".sql": "sql",
    ".md": "markdown",    ".rst": "markdown",
    ".rb": "ruby",        ".php": "php",     ".lua": "lua",
    ".toml": "toml",      ".yaml": "yaml",   ".yml": "yaml",
    ".xml": "xml",        ".cmake": "cmake",
    ".r": "r",
    # New in v0.6.0
    ".jl": "julia",
    ".m": "matlab",
    ".nb": "mathematica", ".wl": "wolfram",
    ".Rmd": "rmarkdown",  ".rmd": "rmarkdown",
    ".sas": "sas",
    ".do": "stata",       ".ado": "stata",
    ".gms": "gams",
    ".ampl": "ampl",
    ".lp": "lp",          ".mps": "mps",
    ".mw": "maple",       ".mpl": "maple",
    ".maple": "maple",    ".mm": "maple",
    ".latex": "latex",    ".bib": "bibtex",
    ".txt": "text",       ".tex": "latex",
}


def _get_language(file_path: Path) -> str:
    return _LANG_MAP.get(file_path.suffix.lower(), "text")


# ── File hashing ──────────────────────────────────────────────────────────────

def _compute_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_hash_cache_path(project_name: str) -> Path:
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
    for part in path.parts:
        if part in _EXCLUDE_DIRS:
            return True
    for pattern in _EXCLUDE_PATTERNS:
        if path.match(pattern):
            return True
    return False


# ── RAG source path resolution ────────────────────────────────────────────────

def _resolve_rag_source_path(project: dict) -> Path | None:
    """
    BUG FIX (B2): 'path' is the RAG source folder.
    'code_path' is the Aider edit target -- never the index root.
    Only fall back to code_path when path is '.' (conversation-only project)
    AND code_path is explicitly set.
    """
    raw_path = project.get("path", "")
    if raw_path and raw_path != ".":
        p = Path(raw_path)
        return p if p.exists() else None

    # path is '.' -- conversation-only project, check code_path as fallback
    code_path = project.get("code_path", "")
    if code_path and code_path.strip():
        p = Path(code_path)
        return p if p.exists() else None

    return None


# ── File collection ───────────────────────────────────────────────────────────

def collect_indexable_files(project_path: Path) -> list[Path]:
    files         = []
    dirs_to_visit = [project_path]

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
    import chromadb
    from llama_index.core import Settings, StorageContext, VectorStoreIndex
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.schema import Document
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.chroma import ChromaVectorStore

    project_path = _resolve_rag_source_path(project)
    if not project_path:
        raise FileNotFoundError(
            f"No valid RAG source folder is set for project '{project['display_name']}'.\n"
            f"Open project settings -> set a RAG source folder -> then index.\n"
            f"Note: 'RAG source folder' (path) is separate from the Aider code folder (code_path)."
        )

    collection   = project["collection"]
    project_name = project["name"]

    log.info(f"Building index for project '{project['display_name']}'")
    log.info(f"  Path       : {project_path}")
    log.info(f"  Collection : {collection}")
    log.info(f"  Embed      : {EMBED_MODEL}")
    log.info(f"  Chunk size : {CHUNK_SIZE}  overlap: {CHUNK_OVERLAP}")

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

    Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    chroma_client     = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    chroma_collection = chroma_client.get_or_create_collection(collection)
    vector_store      = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context   = StorageContext.from_defaults(vector_store=vector_store)

    all_files = collect_indexable_files(project_path)
    by_lang   = {}
    for f in all_files:
        lang = _get_language(f)
        by_lang[lang] = by_lang.get(lang, 0) + 1
    lang_summary = ", ".join(f"{v} {k}" for k, v in sorted(by_lang.items()))
    log.info(f"  Files found: {len(all_files)} ({lang_summary or 'none'})")

    if not all_files:
        log.warning("No indexable files found. Check project path and exclusion rules.")
        return chroma_collection.count()

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

    log.info(f"  Embedding {len(documents)} documents...")
    start_time = time.time()
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )
    elapsed = time.time() - start_time
    log.info(f"  Embedded in {elapsed:.1f}s")

    for file_path in to_index:
        hash_cache[str(file_path)] = _compute_file_hash(file_path)
    _save_hash_cache(project_name, hash_cache)

    count = chroma_collection.count()
    log.info(f"  Index complete. Vectors: {count}")
    return count


# ── Index query -- retrieval only (no hidden second LLM call) ─────────────────

def query_project_index(
    question:     str,
    collection:   str,
    project_name: str = "",
    top_k:        int = DEFAULT_TOP_K,
) -> dict:
    """
    Query a project's ChromaDB index and return retrieved source chunks.

    v0.6.0 CHANGE: Uses retriever.retrieve() instead of query_engine.query().
    This eliminates the hidden second LLM call that previously ran inside
    LlamaIndex before returning. The retrieved chunks are formatted as plain
    text and injected directly into the main streaming call's system prompt.

    Returns:
        Dict with keys:
          answer  : str -- formatted retrieved chunks (NOT an LLM-synthesised answer)
          sources : list of dicts -- each with file_path, language, score, snippet
    """
    import chromadb
    from llama_index.core import Settings, StorageContext, VectorStoreIndex
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.vector_stores.chroma import ChromaVectorStore

    # Read snippet length from settings
    try:
        from lincoln.lincoln_database import get_setting
        snippet_chars = int(get_setting("rag_snippet_chars", "500"))
    except Exception:
        snippet_chars = 500

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

    # Retrieval only -- no LLM call inside LlamaIndex
    retriever = index.as_retriever(similarity_top_k=top_k)

    log.info(f"RAG query | project: {project_name} | top_k: {top_k}")
    log.info(f"  Question: {question!r}")

    nodes = retriever.retrieve(question)

    sources = []
    context_parts = []

    for node in nodes:
        meta    = node.metadata
        snippet = node.text[:snippet_chars].replace("\n", " ")
        score   = round(getattr(node, "score", 0) or 0, 3)

        sources.append({
            "file_path": meta.get("file_path", "unknown"),
            "file_name": meta.get("file_name", "unknown"),
            "language":  meta.get("language", "unknown"),
            "score":     score,
            "snippet":   snippet,
        })

        # Format chunk for context injection
        file_label = meta.get("file_path", "unknown")
        lang_label = meta.get("language", "")
        context_parts.append(
            f"[Source: {file_label} | score: {score}]\n"
            f"```{lang_label}\n{node.text.strip()}\n```"
        )

    # The 'answer' field is now the formatted context, not an LLM synthesis
    formatted_context = "\n\n".join(context_parts)

    log.info(f"  Retrieved {len(nodes)} chunks for context injection.")
    return {"answer": formatted_context, "sources": sources}


# ── Dry run -- file preview ───────────────────────────────────────────────────

def dry_run_project(project: dict) -> dict:
    """
    Preview which files would be indexed for a project without embedding anything.
    BUG FIX (B2): uses _resolve_rag_source_path(), same as build_project_index().
    """
    project_path = _resolve_rag_source_path(project)

    if not project_path:
        return {
            "error": (
                "No valid RAG source folder set. "
                "Open project settings to add a RAG source folder path. "
                "Note: the Aider code folder is separate from the RAG source folder."
            )
        }

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
