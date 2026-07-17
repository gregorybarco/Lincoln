# 005 — RAG Pipeline: LlamaIndex + ChromaDB + nomic-embed-text

**Date:** 2026-07-17  
**Status:** Accepted  

---

## Context

Lincoln needs to answer questions about Project 1 (~70 Python and Fortran source files) without manual file pasting. The pipeline must be fully local, never expose secrets to the LLM, and be model-agnostic — embedding and generation models swap via `.env` with no script changes.

---

## Decision

| File | Location | Role |
|------|----------|------|
| `config.py` | `main_configuration\` | Single source of truth for all models and paths |
| `__init__.py` | `main_configuration\` | Makes it an importable Python package |
| `rag_indexer.py` | `scripts\` | Embeds Project 1 source into ChromaDB |
| `rag_query.py` | `scripts\` | Queries the index, synthesizes answers |

All scripts import from `main_configuration.config`. No model name appears in any script.

**Embedding model:** `LINCOLN_EMBED_MODEL` in `.env` (default: `nomic-embed-text`)  
**LLM:** `LINCOLN_LLM_MODEL` in `.env` (default: `qwen3.5:9b`)  
**Vector store:** ChromaDB persistent at `data\chroma_db\`  
**Hash cache:** `data\file_hashes.json` — incremental re-indexing on file change  

---

## Model Swap Procedure

Edit `.env` only — no script changes needed:

```
LINCOLN_LLM_MODEL=gemma4:12b
LINCOLN_EMBED_MODEL=nomic-embed-text-v2-moe
```

**Important:** Changing `LINCOLN_EMBED_MODEL` requires a full rebuild because vectors from different embedding models are incompatible:

```powershell
python scripts\rag_indexer.py --rebuild
```

---

## Note on .aider.conf.yml

Aider requires a literal model string — it cannot read env vars at config parse time. The model in `.aider.conf.yml` must be updated manually when swapping LLMs for use inside Aider. All RAG scripts (indexer, query) correctly read from `.env` via `main_configuration.config`.

---

## Security Design

Exclusions mirror Project 1's `.gitignore` exactly. Only `.py` and Fortran source reach the embedding pipeline:

- `tokens\`, `secrets\` — credential directories excluded  
- `.env`, `*.key`, `*.pem`, `*.json` — secrets excluded  
- All data, compiled, weight, and log types excluded  
- Medallion data lake dirs excluded  
- Project 1 Python source confirmed free of hardcoded secrets  

---

## Workflow

```powershell
# Always dry-run first
python scripts\rag_indexer.py --dry-run

# Build the index
python scripts\rag_indexer.py

# Check status
python scripts\rag_indexer.py --status

# Query from terminal
python scripts\rag_query.py "how does the Monte Carlo pricer work"

# Query from inside Aider
/run python scripts\rag_query.py "explain the Fortran entry points" --top-k 8
```

---

## Checklist

- [x] All model names in `main_configuration\config.py`, overridable via `.env`
- [x] No model strings hardcoded in any script
- [x] `tokens\` and `secrets\` excluded from indexer
- [x] `.env` and `*.json` excluded from indexer
- [x] Dry-run flag implemented
- [x] Project 1 confirmed clean — no hardcoded secrets in Python source
- [x] Project 1 in its own git repo
- [ ] `data\` added to Lincoln `.gitignore`
- [ ] `LINCOLN_PROJECT_PATH` set in Lincoln `.env`
- [ ] `LINCOLN_LLM_MODEL` and `LINCOLN_EMBED_MODEL` set in Lincoln `.env`
- [ ] Dry run reviewed and approved
- [ ] Full index built and vector count verified
