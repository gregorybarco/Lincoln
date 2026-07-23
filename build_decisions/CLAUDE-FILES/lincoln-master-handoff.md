# LINCOLN AI — MASTER HANDOFF DOCUMENT
**Last Updated:** 2026-07-23 (P3b deployed, P1-P4 all complete)
**Version:** v0.7.4 (codename: Navigator)
**Project Path:** `B:\Homebrewed_AI\Lincoln`
**GitHub:** https://github.com/gregorybarco/Lincoln (branch: main)
**Reference commit:** dcab251 ("0.7.4 - Fixed token showing- settings- web agent search")

---

## 1. WHAT LINCOLN IS

Lincoln is a **local AI platform** — not a chatbot wrapper. All inference runs via Ollama at `localhost:11434`. No data leaves the machine. The architecture is:

```
Flask UI (localhost:5000)
    └── ReAct Loop (_react_loop in lincoln_routes_chat.py)
         ├── SAFE_TOOLS   → execute autonomously (rag_query, read_file, save_memory)
         ├── SEARCH_TOOLS → auto when web toggle ON (web_search, read_url)
         └── WRITE_TOOLS  → always show approval card (execute_python, execute_fortran, write_file, run_aider)
```

---

## 2. HARDWARE

- CPU: Intel i7-10700
- GPU: NVIDIA RTX 5060 Ti 16GB (Blackwell, CUDA + WDDM)
- RAM: ~30GB usable
- Ollama on B drive

**Models currently in Ollama:**
- `qwen3.5:9b` — default, all chat/agentic tasks (6.6GB)
- `gemma4:12b` — available, not yet benchmarked for code (7.6GB)
- `qwen2.5-coder:latest` — specialist code model (4.7GB)
- `deepseek-coder:latest` — lightweight code model (776MB)
- `minicpm-v4.5:8b` — vision/multimodal (6.1GB), **wired as of 2026-07-23**
- `nomic-embed-text` — fixed embed model, not switchable

---

## 3. STACK

```
lincoln/
  lincoln_configuration.py      — env loader, GOOGLE_API_KEY/CSE_ID, write_env_key admin
  lincoln_database.py           — SQLite, all DB helpers, get_active_system_prompt(), date injection
  lincoln_ollama_service.py     — Ollama comms, stream_chat_with_tools(), context sizing
  lincoln_rag_index_service.py  — ChromaDB RAG, retrieval only
  lincoln_web_search.py         — DDG primary (3 retries, 1s delay) / Google fallback / fetch() for read_url
  lincoln_tool_schemas.py       — ALL tool definitions and tier classifications
  lincoln_ban_list_checker.py   — OptionsPricing ban patterns + protected Lincoln symbols
  lincoln_ocr_service.py        — Tesseract OCR + vision model extraction
  lincoln_jupyter_service.py    — Python/Fortran/C/C++/Julia/R/Bash/Maple execution
  lincoln_git_service.py        — Read-only git status via WSL
  lincoln_cleanup_service.py    — Upload retention, tool path detection

lincoln/app/routes/
  lincoln_routes_chat.py        — ReAct loop, _execute_tool(), send/resolve endpoints, ctx_update SSE
  lincoln_routes_history.py     — Chat history + memory CRUD + auto_save_memory
  lincoln_routes_settings.py    — Settings panel API, admin env write-back, search engine selector
  lincoln_routes_projects.py    — Project management
  lincoln_routes_files.py       — File upload + extraction, vision_model routing
  lincoln_routes_git.py         — Git status endpoint
  lincoln_routes_models.py      — Model list endpoint
  lincoln_routes_jupyter.py     — Code execution endpoint

lincoln/app/templates/lincoln_index.html   — Topbar with ctx indicator element
lincoln/app/static/css/lincoln_main.css    — Ctx indicator styles + Settings 860px + canvas styles
lincoln/app/static/js/
  lincoln_chat.js               — Main chat controller, SSE handler, approval cards, ctx indicator, KaTeX fix, always-on globe
  lincoln_sidebar.js            — History, projects, memory panel, fold toggle, exit project, project filter fix
  lincoln_canvas.js             — Code block management, run buttons
  lincoln_settings.js           — Settings panel (860px tabbed, 10 tabs, admin mode, Google keys, terminal/git buttons)
```

**Launch:** Double-click Lincoln desktop shortcut OR `.\lincoln_start.bat`
**DB:** `B:\Homebrewed_AI\Lincoln\data\lincoln_database.db`
**Deployment:** Manual file copy. Python changes = full restart. JS/CSS changes = hard reload (Ctrl+Shift+R).
**NEVER:** Edit `lincoln/lincoln_routes_settings.py` — that path doesn't exist correctly. Correct path is `lincoln/app/routes/lincoln_routes_settings.py`.

---

## 4. NON-NEGOTIABLE ARCHITECTURAL PRINCIPLES

1. **No Docker.** Ever.
2. **No cloud exposure.** All inference via localhost:11434. All data in local SQLite + ChromaDB.
3. **Everything configurable via Settings UI.** No hardcoding in Python files or .env. All settings in SQLite `_DEFAULT_SETTINGS` table, exposed in Settings panel, read at runtime.
4. **No hardcoded model names.** LLM switchable from UI per session. Embed model fixed in .env.
5. **Aider always suggestion-only.** Never auto-commits.
6. **ASCII-127 Law.** All Fortran and Python source files stay within 7-bit ASCII. Unicode causes silent encoding corruption at NTFS/WSL2 boundary and fatal crackfortran crashes.
7. **Purpose over theatre.** No arbitrary limits, no fake safety theatre.
8. **Patches as inline chat code blocks — never file artifacts.** Artifacts corrupt indentation.
9. **Always fetch live GitHub raw URL before patching.** Never patch from memory.
10. **Select-String verification after deployment.** Confirm file changed on disk before assuming success.

---

## 5. BANNED CODING PATTERNS

### Python
1. **NEVER mix `yield` and `return value` in the same function.** Use `yield (value_tuple)` then bare `return`. Caller checks `isinstance(item, tuple)`. This was the root cause of the ReAct loop never firing `done` — silent failure, no errors, tokens streamed fine.
2. **NEVER assume a JS/CSS/HTML file was redeployed** just because the UI shows a new version. Check with `Select-String` on disk. Python files need full restart; JS/CSS need hard reload.
3. **NEVER trust an empty devtools console** as proof nothing is wrong. Add `console.error`/logging to all catch-all blocks during debugging.
4. **marked.js v9 renderer:** `renderer.code` receives a single token object `{type, raw, lang, text, escaped}` — NOT three positional args. Lincoln pins marked@9.1.6 in CDN.

### Tool Call Schema
1. **`tool_calls` arguments MUST be native Python dicts.** NEVER `json.dumps(arguments)`.
2. **Tool result messages MUST use `"role": "tool"`.** Never `"role": "user"`.
3. **Every assistant tool-call message MUST have `"id": tool_call_id` and `"type": "function"`.**
4. **Every tool result message MUST have `"tool_call_id": tool_call_id`.**
5. **Never inject meta-prompting into tool result content.** Tool responses = raw data only.

---

## 6. CONFIRMED WORKING AS OF 2026-07-23

### ReAct Loop
- Full ReAct loop end-to-end working.
- SAFE_TOOLS: `rag_query`, `read_file`, `save_memory` — autonomous, no approval.
- SEARCH_TOOLS: `web_search`, `read_url` — auto when globe toggle ON.
- WRITE_TOOLS: `execute_python`, `execute_fortran`, `write_file`, `run_aider` — always approval card.

### Globe Pill Always-On (P1 — COMPLETE)
- `_webSearchAlwaysOn` in `lincoln_chat.js`. DB key `web_search_always_on`.
- Pill locks when always-on active — manual toggle-off blocked.
- `syncAlwaysOnSearch(forcedValue?)` — accepts optional bypass param to avoid race condition with settings save.

### MiniCPM Vision Wiring (P2 — COMPLETE)
- `vision_model` DB setting defaulting to `minicpm-v4.5:8b`.
- Wired into `lincoln_routes_files.py` — when `mode=vision`, passes vision_model from DB.
- Exposed in Settings → Models tab.

### Context Window Indicator (P3 + P3b — COMPLETE)
- P3: HTTP poll — `/api/chat/context_usage` endpoint, updates indicator after response completes.
- P3b: SSE stream — `ctx_update` event fires before `_react_loop`. Indicator appears DURING streaming, then updates again with final count after `done`.
- `_applyCtxUpdate(tokens, ceiling)` in `lincoln_chat.js`.
- Progress bar with colour thresholds: amber at 75%, red at 90%.

### DDG Retry Logic (P4 — COMPLETE)
- 3 attempts, 1s delay between retries, then Google fallback.
- In `lincoln_web_search.py`.

### Web Search + read_url Chaining
- Continuation directive injected into web_search tool result forces Qwen to call read_url.
- Terminal sequence: `web_search fired → read_url fired → read_url fired again`.
- `🌐 N web results used` indicator in chat.

### Memory (save_memory tool)
- Fires autonomously mid-conversation, no approval.
- Writes to `lincoln_memory_entries` via `save_memory_entry()`.
- Tags: `preference`, `decision`, `constraint`, `fact`, `code_style`, `persona`.

### Context Window Sizing
- `_RESPONSE_HEADROOM = 0.40`, `_MIN_OUTPUT_TOKENS = 2048`.
- Per-request sizing — no hardcoded values, no user input.

### Settings Panel
- 860px wide, left-nav tabbed, 10 sections.
- Version/codename DB-backed (admin mode).
- Google API key + CSE ID editable (admin mode).
- Open Dev Terminal + Git Reset Hard buttons (admin mode).
- Search engine selector: DDG / Google / DDG+fallback.

### Four Active System Prompt Blocks
1. Lincoln persona
2. Lincoln Life cycle
3. Memory Save Behavior
4. Tool Chaining Mandate

---

## 7. PENDING ITEMS

**Nothing in the confirmed queue.** P1, P2, P3, P3b, and P4 are all complete.

Ask the user what to build next at the start of the next session.

---

## 8. ROADMAP (not confirmed, not in active queue)

**Build order before advancing to multi-agent (Tier 3):**
1. Execution isolation (subprocess → sandboxed env)
2. Self-indexing (Lincoln RAG over own source, read-only)
3. Self-introspection agentic (propose patches via Aider, never auto-apply)
4. Model routing (specialist models per task)
5. True multi-agent (parallel agents, shared memory pool)

**Long-term goals:**
- QLoRA fine-tuning on RTX 5060 Ti 16GB
- Bloomberg/Schwab terminal data extraction pipeline
- Agentic web browsing (Playwright/Selenium via WSL)
- Commercialisation: private enterprise AI, financial research tools

---

## 9. SESSION HANDOFF PROTOCOL (EVERY NEW SESSION — MANDATORY)

1. Call `recent_chats` (n=8 minimum).
2. Read all `userMemories` entries in full.
3. Fetch the three CLAUDE-FILES URLs from GitHub in this order:
   - https://raw.githubusercontent.com/gregorybarco/Lincoln/main/build_decisions/CLAUDE-FILES/Lincoln-file-tree.md
   - https://raw.githubusercontent.com/gregorybarco/Lincoln/main/build_decisions/CLAUDE-FILES/lincoln-master-handoff.md
   - https://raw.githubusercontent.com/gregorybarco/Lincoln/main/build_decisions/CLAUDE-FILES/lincoln-shared-memory.md
4. Fetch any specific source files needed for the task using URLs from the file tree.
5. Cross-check — identify anything in recent chats NOT yet captured in shared memory.
6. Confirm to user: "Reviewed memory, recent chats, handoff doc, shared memory. Pending queue is [X]. What should we build next?"
7. Only THEN begin any build or patch work.

If Claude skips this, prompt: **"Check recent chats and memory first."**

---

## 10. KEY BUGS FIXED (CUMULATIVE)

| Session | Bug | Root Cause | Fix |
|---|---|---|---|
| 2026-07-23 | `save_memory` 400 error | `tool_calls.arguments` was `json.dumps()` string | Native dict |
| 2026-07-23 | Tool result 400 error | Missing `tool_call_id` on `role:tool` messages | Added to all 3 append sites in `_react_loop` |
| 2026-07-23 | Memory writes to phantom table | Raw SQL `CREATE TABLE memory_entries` | Replaced with `save_memory_entry()` |
| 2026-07-23 | Response cuts off mid-synthesis | 20% headroom too small | Increased to 40% + 2048 floor |
| 2026-07-23 | read_url not chaining after search | Qwen ignores schema-level hints | Continuation directive injected into search tool result |
| 2026-07-23 | ReAct done event never fires | yield/return mix in generator | `yield (tuple)` + bare `return` + isinstance check |
| 2026-07-23 | Globe pill state inconsistency | `toggleWebSearch` didn't respect `_webSearchAlwaysOn` | Manual toggle-off blocked when always-on active |
| 2026-07-23 | Settings patch went to wrong file | Stale duplicate at `lincoln/lincoln_routes_settings.py` | Stale copy deleted; correct path is `lincoln/app/routes/lincoln_routes_settings.py` |
| 2026-07-22 | KaTeX mangles financial text | Bare `$` treated as math delimiter | Removed bare `$` from KaTeX config |
| 2026-07-22 | Date in web search queries stale | Qwen doesn't know current date | `date.today().isoformat()` injected in system prompt |
