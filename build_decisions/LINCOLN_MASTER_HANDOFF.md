# LINCOLN AI — MASTER HANDOFF DOCUMENT
**Last Updated:** 2026-07-23 (Session end)  
**Version:** v0.7.1 (codename: Navigator)  
**Project Path:** `B:\Homebrewed_AI\Lincoln`  
**GitHub:** https://github.com/gregorybarco

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
- `qwen3.5:9b` — default, used for all chat/agentic tasks (6.6GB)
- `gemma4:12b` — available, not yet benchmarked for code (7.6GB)
- `qwen2.5-coder:latest` — specialist code model (4.7GB)
- `deepseek-coder:latest` — lightweight code model (776MB)
- `minicpm-v4.5:8b` — vision/multimodal model (6.1GB), pulled but NOT yet wired into Lincoln
- `nomic-embed-text` — fixed embed model, not switchable

---

## 3. STACK

```
lincoln/
  lincoln_configuration.py      — env loader, GOOGLE_API_KEY/CSE_ID, write_env_key admin
  lincoln_database.py           — SQLite, all DB helpers, get_active_system_prompt()
  lincoln_ollama_service.py     — Ollama comms, stream_chat_with_tools(), context sizing
  lincoln_rag_index_service.py  — ChromaDB RAG, retrieval only
  lincoln_web_search.py         — DDG primary / Google fallback, fetch() for read_url
  lincoln_tool_schemas.py       — ALL tool definitions and tier classifications
  lincoln_ban_list_checker.py   — OptionsPricing ban patterns + protected Lincoln symbols
  lincoln_ocr_service.py        — Tesseract OCR + vision model extraction
  lincoln_jupyter_service.py    — Python/Fortran/C/C++/Julia/R/Bash/Maple execution
  lincoln_git_service.py        — Read-only git status via WSL
  lincoln_cleanup_service.py    — Upload retention, tool path detection

lincoln/app/routes/
  lincoln_routes_chat.py        — ReAct loop, _execute_tool(), send/resolve endpoints
  lincoln_routes_history.py     — Chat history + memory CRUD + auto_save_memory
  lincoln_routes_settings.py    — Settings panel API, admin env write-back
  lincoln_routes_projects.py    — Project management
  lincoln_routes_files.py       — File upload + extraction
  lincoln_routes_git.py         — Git status endpoint
  lincoln_routes_models.py      — Model list endpoint
  lincoln_routes_jupyter.py     — Code execution endpoint

lincoln/app/templates/lincoln_index.html
lincoln/app/static/css/lincoln_main.css
lincoln/app/static/js/
  lincoln_chat.js               — Main chat controller, SSE handler, approval cards
  lincoln_sidebar.js            — History, projects, memory panel
  lincoln_canvas.js             — Code block management, run buttons
  lincoln_settings.js           — Settings panel (860px tabbed layout)
```

**Launch:** Double-click Lincoln desktop shortcut OR `.\lincoln_start.bat` from PowerShell.  
**DB:** `B:\Homebrewed_AI\Lincoln\data\lincoln_database.db`  
**Deployment:** Manual file copy (no auto-deploy). Python .py changes require full restart. JS/CSS changes require hard reload (Ctrl+Shift+R).

---

## 4. NON-NEGOTIABLE ARCHITECTURAL PRINCIPLES

1. **No Docker.** Ever.
2. **No cloud exposure.** All inference via localhost:11434. All data in local SQLite + ChromaDB.
3. **Everything configurable via Settings UI.** No hardcoding in Python files or .env. All settings in SQLite `_DEFAULT_SETTINGS` table, exposed in Settings panel, read at runtime. Violations: editing `__init__.py` for version (banned), editing `.env` directly for keys (banned), hardcoding paths in Python (banned).
4. **No hardcoded model names.** LLM switchable from UI per session. Embed model fixed in .env.
5. **Aider always suggestion-only.** Never auto-commits. User reviews all proposed changes.
6. **ASCII-127 Law.** All Fortran and Python source files must stay within 7-bit ASCII (0-127). Unicode causes silent encoding corruption at NTFS/WSL2 boundary and fatal crackfortran crashes.
7. **Purpose over theatre.** No arbitrary limits, no fake safety theatre.

---

## 5. BANNED CODING PATTERNS (CRITICAL — READ BEFORE PATCHING)

### Python
1. **NEVER mix `yield` and `return value` in the same function.** If a function has any `yield` it is a generator. `return value` silently discards the value. Fix: `yield (value_tuple)` then bare `return`. Caller checks `isinstance(item, tuple)`.
2. **NEVER assume a JS/CSS/HTML file was redeployed** just because the UI shows a new version. Check with `Select-String` on disk. Flask serves static files fresh but Python files load once at process start — `.py` changes require full restart (Ctrl+C + relaunch).
3. **NEVER trust an empty devtools console** as proof nothing is wrong. Swallowed exceptions (`except: pass`) produce zero errors. Add `console.error`/logging to all catch-all blocks during debugging.
4. **marked.js v9 renderer:** `renderer.code` receives a single token object `{type, raw, lang, text, escaped}` — NOT the old three positional args. Lincoln pins marked@9.1.6 in CDN.

### Tool Call Schema (Ollama payload — causes silent 400 errors if violated)
1. **`tool_calls` arguments MUST be native Python dicts.** NEVER `json.dumps(arguments)`. This was the root cause of the 400 Bad Request after save_memory fired.
2. **Tool result messages MUST use `"role": "tool"`.** Never disguise as `"role": "user"`.
3. **Every assistant tool-call message MUST have `"id": tool_call_id` and `"type": "function"`** alongside the function dict.
4. **Every tool result message MUST have `"tool_call_id": tool_call_id`** linking it back to the assistant's request.
5. **Never inject meta-prompting into tool result content.** Tool responses = raw data only. Guidance goes in the system prompt.

---

## 6. CONFIRMED WORKING AS OF 2026-07-23

### ReAct Loop
- Full ReAct loop end-to-end working: approval card fires, Python executes, stdout returned, loop completes, markdown renders, canvas pins code blocks.
- SAFE_TOOLS execute autonomously (no approval): `rag_query`, `read_file`, `save_memory`
- SEARCH_TOOLS execute when web toggle ON: `web_search`, `read_url`
- WRITE_TOOLS always show approval card: `execute_python`, `execute_fortran`, `write_file`, `run_aider`

### Memory (save_memory tool)
- `save_memory` fires **autonomously mid-conversation** — no button, no approval.
- Writes to correct `lincoln_memory_entries` table via `save_memory_entry()`.
- Tags: `preference`, `decision`, `constraint`, `fact`, `code_style`, `persona`
- Terminal confirms: `[Lincoln] save_memory: tag=code_style fact=...`
- Memory panel (Settings → Memory) shows entries correctly.

### Web Search + read_url Chaining
- `web_search → read_url` chaining working autonomously.
- Lincoln searches DDG, selects relevant URLs, fetches full page content via BeautifulSoup4, synthesizes complete answer.
- Terminal sequence: `web_search fired → read_url fired → read_url fired again`
- Web results indicator shows in chat: `🌐 N web results used`
- Continuation directive injected into web_search result forces Qwen to call read_url before answering.

### Context Window Sizing
- `_RESPONSE_HEADROOM = 0.40` (was 0.20) — 40% of window reserved for output.
- `_MIN_OUTPUT_TOKENS = 2048` — hard floor, always reserves at least 2048 tokens for output.
- Terminal now shows: `num_ctx -- input_est=X + headroom(40%) + floor(2048) -> window=Y output_reserved=Z`
- Prevents synthesis cutoff on long agentic sessions with multiple tool results.

### auto_save_memory (Memory button)
- Fixed phantom table bug: was writing to `memory_entries`, now uses `save_memory_entry()` → correct `lincoln_memory_entries` table.
- Improved extraction prompt with `NOTHING_TO_SAVE` sentinel.
- Runs in background daemon thread — returns 200 OK instantly, no UI hang.

### Settings Panel
- 860px wide, left-nav tabbed layout, 10 sections.
- Version/codename DB-backed (admin mode).
- Google API key + CSE ID editable from UI (admin mode).
- Open Dev Terminal + Git Reset buttons in Infrastructure tab.
- All system prompt blocks editable, persistent in DB.

### Four Active System Prompt Blocks (in DB, not hardcoded)
1. **Lincoln persona** — identity, formatting rules, autonomous multi-step directive
2. **Lincoln Life cycle** — agent phases, behavioral silos
3. **Memory Save Behavior** — when and how to call save_memory proactively
4. **Tool Chaining Mandate** — after web_search always call read_url; dedup before saving memory

---

## 7. PENDING ITEMS (PRIORITY ORDER)

### P1 — Globe pill always-on mode
**What:** The web search globe pill in the input bar resets to OFF after every message send (`_resetWebSearchPill()` called in `sendMessage()`). User has to click it before every message.  
**What it should do:** When `web_search_always_on` DB setting is true, pill starts active every message and `_resetWebSearchPill()` skips the reset.  
**Files:** `lincoln_chat.js` (modify `_resetWebSearchPill()` to check setting), `lincoln_database.py` (add `web_search_always_on` to `_DEFAULT_SETTINGS` if not already there).  
**Note:** `syncAlwaysOnSearch()` was reportedly built by Gemini but may not be in the deployed JS — verify before building.

### P2 — MiniCPM vision wiring
**What:** `minicpm-v4.5:8b` (6.1GB) is already pulled in Ollama and shows up in the model list. It is a multimodal vision model — it can read images, charts, screenshots.  
**What it's for:** Bloomberg OVDV screenshots, option chain exports, any image the user attaches. Currently Lincoln uses Tesseract OCR for text images and has no route for chart/diagram images through the LLM.  
**What needs building:** When user attaches an image, Lincoln should route it to MiniCPM rather than Qwen. Specifically: in `lincoln_routes_files.py` upload handler, when `mode=vision` is requested, call MiniCPM via Ollama with the image base64. The `lincoln_ocr_service.py` `extract_text_vision_model()` function already exists and calls Ollama `/api/generate` with `images: [base64]` — just needs MiniCPM wired as the default vision model in DB settings.  
**Files:** `lincoln_database.py` (add `vision_model` setting defaulting to `minicpm-v4.5:8b`), `lincoln_routes_files.py` (pass `vision_model` from DB setting), `lincoln_settings.js` (expose vision model in Models tab).

### P3 — Context window indicator on project screen
**What:** When a project is active, the project home screen shows "0 vectors" and chat count. It should also show a visual indicator of how much of the context window is currently being used — similar to how Claude shows context usage in the project view.  
**What it displays:** Tokens used in current session / total window ceiling, as a progress bar or percentage. E.g. `4,432 / 131,072 tokens (3%)`.  
**Why useful:** Lets user see at a glance how much context is left before the session needs to be reset.  
**Files:** `lincoln_index.html` (add indicator element to project home section), `lincoln_sidebar.js` or `lincoln_chat.js` (update indicator after each message using the `num_ctx` data from the backend — or expose a `/api/chat/context_usage` endpoint).

### P4 — DDG retry logic
**What:** DuckDuckGo occasionally rate-limits or times out, returning an error. When this happens the current code raises a `RuntimeError` and falls through to Google fallback. But DDG sometimes fails on the first attempt and succeeds immediately on retry.  
**What needs building:** In `lincoln_web_search.py`, wrap `_search_ddg()` in a retry loop: try up to 3 times with a 1-second delay between attempts before falling back to Google. Use `time.sleep(1)` between retries.  
**Files:** `lincoln_web_search.py` only.

---

## 8. MULTI-AGENT VISION (ROADMAP)

Lincoln is being built toward a multi-agent architecture:

**Tier 1** — Chatbot with manual tools (done, pre-v0.7.0)  
**Tier 2** — ReAct loop, model decides tool calls, human approval gate on writes (CURRENT)  
**Tier 3** — Multi-agent routing, specialist models, parallel execution  
**Tier 4** — Autonomous long-horizon, self-correcting across sessions  

**Required build order before advancing:**
1. Execution isolation (subprocess → sandboxed env)
2. Self-indexing (Lincoln RAG over own source, read-only)
3. Self-introspection agentic (propose patches via Aider, never auto-apply)
4. Model routing (specialist models per task type)
5. True multi-agent (parallel agents, shared memory pool)

**Model routing plan (when ready):**
- Conversational/reasoning → `qwen3.5:9b`
- Code generation/debugging → `qwen2.5-coder` or `deepseek-coder`
- Vision/OCR → `minicpm-v4.5:8b`
- Numerical/exact computation → deterministic tools (Fortran, Maple, Python)

**Memory as shared agent state:** `lincoln_memory_entries` already has `project_id` and `tag` columns. For multi-agent, add `agent_id TEXT DEFAULT 'lincoln'` column. Each specialist agent reads all project memory and writes with its own `agent_id` tag.

---

## 9. LONG-TERM GOALS

1. **QLoRA fine-tuning** on RTX 5060 Ti 16GB — fine-tune Qwen or Gemma on OptionsPricing + BARCO_CORE data for domain-specific financial modelling. MLflow experiment tracking prerequisite.
2. **Lincoln self-maintenance** — LLM has read access to own source via RAG project; proposes patches via Aider suggestion mode; user reviews and approves.
3. **Bloomberg/Schwab terminal integration** — OCR pipeline operational; future: structured data extraction from OVDV, option chains, Greeks tables into pandas DataFrames stored locally.
4. **Agentic web browsing** — Playwright/Selenium via WSL for job application automation, web form filling, data collection.
5. **Commercialisation path** — private enterprise AI, financial research tools, secure multimodal extraction.

---

## 10. SESSION HANDOFF PROTOCOL (EVERY NEW CLAUDE SESSION)

**THIS IS MANDATORY. Do not skip.**

At the START of every new Claude session working on Lincoln:
1. Call `recent_chats` to pull last 5-10 sessions.
2. Read all `userMemories` entries in full.
3. Read this document if it is in the project files.
4. Cross-check — identify anything in recent chats NOT yet captured and add it.
5. Confirm to the user: "I have reviewed memory entries 1-N, recent chats, and the handoff document. Here is what I know is pending..." then list current priority queue.
6. Only THEN begin any build, patch, or planning work.

If Claude skips this step, prompt: **"Check recent chats and memory first."**

---

## 11. KEY BUGS FIXED THIS SESSION (2026-07-23)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `save_memory` 400 error | `tool_calls.arguments` was `json.dumps()` string | Changed to native dict |
| Tool result 400 error | Missing `tool_call_id` on `role:tool` messages | Added to all 3 append sites in `_react_loop` |
| Memory writes to phantom table | Raw SQL `CREATE TABLE memory_entries` (wrong name) | Replaced with `save_memory_entry()` call |
| Response cuts off mid-synthesis | 20% headroom too small for multi-tool sessions | Increased to 40% + 2048 token floor |
| read_url not chaining after search | Qwen ignores schema-level hints | Injected `NEXT REQUIRED ACTION: Call read_url` into search tool result |
