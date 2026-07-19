# 007 — Project Structure, Package Naming, and File Naming Convention

**Date:** 2026-07-18
**Status:** Accepted

---

## Context

After completing the initial Flask architecture design (ADR-006), the project
structure had two compounding problems:

1. **Artificial separation** between `main_configuration\` and `core\` —
   two Python packages doing the same job (Lincoln internals) with no
   meaningful boundary between them. Adding new services required deciding
   which package they belonged to, a decision with no correct answer.

2. **Generic file names** — `config.py`, `db_service.py`, `index_service.py`
   answer "what kind of thing is this" but not "what does this specific file own
   in this specific system." Six months into the project, opening the wrong file
   before finding the right one becomes a routine tax on productivity.

---

## Decisions

### 1. Single Python Package: `lincoln\`

`main_configuration\` and `core\` are merged into one flat package: `lincoln\`.

All Lincoln Python source lives here. The Flask application lives in `lincoln\app\`
as a sub-package. There is no other Python package in the project.

Import surface:
```python
from lincoln.lincoln_configuration    import LLM_MODEL, OLLAMA_BASE_URL
from lincoln.lincoln_database         import get_all_projects, create_project
from lincoln.lincoln_rag_index_service import build_project_index, query_project_index
from lincoln.lincoln_ollama_service   import stream_chat, get_available_models
```

**Rejected alternative:** keeping `main_configuration\` and `core\` separate.
**Reason:** The boundary between them is arbitrary. There is no rule that
correctly assigns a new file to one vs the other.

### 2. File Naming Convention: `lincoln_<what_it_owns>_<what_it_does>.py`

Every file in the `lincoln\` package is prefixed with `lincoln_` and named
to describe what it owns and what it does. No generic names. No abbreviations.

| File | Owns |
|---|---|
| `lincoln_configuration.py` | Infrastructure config loader — reads .env |
| `lincoln_database.py` | All SQLite persistence — projects, sessions, settings, memory |
| `lincoln_rag_index_service.py` | RAG pipeline — ChromaDB indexing and querying |
| `lincoln_ollama_service.py` | Ollama LLM service — chat, streaming, model discovery |
| `lincoln_memory_service.py` | Session memory — context injection on startup |
| `lincoln_web_search.py` | Web search — DuckDuckGo search and URL fetch |
| `lincoln_routes_chat.py` | Flask routes — chat and streaming |
| `lincoln_routes_projects.py` | Flask routes — project CRUD and index trigger |
| `lincoln_routes_models.py` | Flask routes — model selector |
| `lincoln_routes_settings.py` | Flask routes — settings and system status |
| `lincoln_routes_history.py` | Flask routes — chat history |

This convention applies permanently. Every file added in future sessions
follows the same pattern.

**Rejected alternative:** short generic names (config.py, db.py, etc.)
**Reason:** Generic names require the reader to hold context in their head.
Verbose names answer the question before the file is opened.

### 3. Launcher Separation: `bin\`

All `.bat` launcher files live in `bin\`. No Python source lives in `bin\`.
`bin\` replaces `scripts\` in the Windows PATH.

`scripts\` is retired. The Python logic that was in `scripts\` is absorbed
into the `lincoln\` package. The `.bat` files become one-line thin shells
that call into the package.

### 4. Data Directory Structure

```
data\
  lincoln_database.db   ← SQLite (all structured data)
  chroma_db\            ← ChromaDB vector store
  hashes\               ← per-project file hash caches
  logs\                 ← application logs (future)
```

`data\` is fully gitignored. The database filename matches the naming
convention — `lincoln_database.db` not `lincoln.db` or `data.db`.

### 5. Version in Package, Not Folder

Lincoln version is declared in `lincoln\__init__.py` as `__version__ = "0.4.0"`.
The folder is named `lincoln\` permanently — version numbers never appear
in folder or import paths.

Version roadmap:
```
0.3.0  RAG pipeline complete
0.4.0  Web UI, DB-driven projects, service layer  ← current
0.5.0  Persistent memory
0.6.0  MLflow experiment tracking
1.0.0  QLoRA fine-tuning complete
```

---

## File Migration from Previous Structure

| Old location | New location | Notes |
|---|---|---|
| `main_configuration\config.py` | `lincoln\lincoln_configuration.py` | Simplified — no project registry |
| `main_configuration\__init__.py` | `lincoln\__init__.py` | Now holds `__version__` |
| `core\db_service.py` | `lincoln\lincoln_database.py` | All table names prefixed `lincoln_` |
| `scripts\web_search.py` | `lincoln\lincoln_web_search.py` | Unchanged logic, renamed |
| `scripts\rag_query.py` | `lincoln\lincoln_rag_index_service.py` | Merged into service |
| `scripts\rag_indexer.py` | `lincoln\lincoln_rag_index_service.py` | Merged into service |
| `scripts\lincoln_shell.py` | retired | Flask replaces it |
| `scripts\lincoln.bat` | `bin\lincoln.bat` | Now starts Flask |
| `scripts\rag.bat` | `bin\lincoln_rag_query.bat` | Verbose name |
| `scripts\websearch.bat` | `bin\lincoln_websearch.bat` | Verbose name |
| `scripts\lhelp.bat` | `bin\lincoln_help.bat` | Verbose name |

---

## Checklist

- [x] `lincoln\` package created with all service files
- [x] `bin\` created with all launcher files
- [x] `data\` structure defined
- [x] `scripts\` retired
- [x] `main_configuration\` retired
- [x] Windows PATH updated from `scripts\` to `bin\`
- [x] `.gitignore` updated to cover `data\` and aider noise files
- [ ] `lincoln\app\templates\lincoln_index.html` — HTML shell (next pass)
- [ ] `lincoln\app\static\` — CSS and JS files (next pass)
- [ ] Smoke test: `python -c "from lincoln.lincoln_configuration import print_startup_summary; print_startup_summary()"`
