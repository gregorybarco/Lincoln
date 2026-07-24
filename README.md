# Lincoln

A local AI platform built on open source tools with zero cloud dependency.
Not a chatbot wrapper — a full agentic system with tool use, memory, and RAG,
running entirely on local hardware.

## Purpose
- Local-first AI agent, no data ever leaves the machine.
- Agentic research and coding assistant for mathematical finance work
  (options pricing, quantitative research, Fortran/Python numerical code).

## Architecture

```
Flask UI (localhost:5000)
    └── ReAct Loop (_react_loop in lincoln_routes_chat.py)
         ├── SAFE_TOOLS   → execute autonomously (rag_query, read_file, save_memory)
         ├── SEARCH_TOOLS → auto when web toggle ON (web_search, read_url)
         └── WRITE_TOOLS  → always show approval card (execute_python, execute_fortran, write_file, run_aider)
```

## Launch
Double-click the Lincoln desktop shortcut, or run:
```
.\lincoln_start.bat
```
Opens Lincoln at `localhost:5000`.

## Stack
- **Ollama** — local model serving (`localhost:11434`)
- **Qwen 3.5 9B** — default reasoning/agentic model (switchable per session from the UI)
- **ChromaDB + LlamaIndex + nomic-embed-text** — RAG pipeline over project source
- **Aider** — suggestion-only code assistance layer (never auto-commits)
- **Flask** — web UI and backend
- **SQLite** — chat history, memory, settings

## Capabilities
- Multi-tier tool system: safe tools run autonomously, search tools run when
  web search is toggled on, write/execution tools always require approval.
- Persistent memory (`save_memory`) — Lincoln can save facts, preferences,
  decisions, and constraints mid-conversation, tagged and editable from the
  sidebar.
- Code execution sandbox: Python (persistent Jupyter kernel), plus
  Fortran, C, C++, Julia, R, Bash, and Maple via WSL2/subprocess.
- Vision input via MiniCPM for images and charts.
- Fully configurable from the in-app Settings panel — no hardcoded config.

## Status
Operational, v0.7.4 (codename: Navigator). Core agentic loop, RAG, memory,
vision, and settings are all live. See `build_decisions/CLAUDE-FILES/lincoln-roadmap.md`
for the active development roadmap.

## Non-negotiables
- No Docker.
- No cloud inference — everything runs via `localhost:11434`.
- Nothing hardcoded — all settings configurable via the UI.