# LINCOLN SHARED MEMORY
**Path on disk:** `B:\Homebrewed_AI\Lincoln\build_decisions\CLAUDE-FILES\lincoln-shared-memory.md`
**Authority:** This file is the shared source of truth between Project A (original Claude instance) and Project B (sister Claude instance on a different machine/account).
**Update rule:** Any Claude instance that makes a confirmed deployment must update this file in the same session. A change is not "done" until it appears here with a verified date.
**Last updated:** 2026-07-23

---

## 1. CONFIRMED LIVE STATE (as of 2026-07-23)

Everything below is confirmed built, deployed locally to `B:\Homebrewed_AI\Lincoln`, and pushed to `github.com/gregorybarco/Lincoln` on `main` branch. Reference commit: `dcab251` ("0.7.4 - Fixed token showing- settings- web agent search").

| Feature | Status | Files Changed | Notes |
|---|---|---|---|
| ReAct loop (3-tier tool system) | ✅ Live | `lincoln_routes_chat.py`, `lincoln_tool_schemas.py` | SAFE/SEARCH/WRITE tiers, approval card for WRITE |
| save_memory autonomous tool | ✅ Live | `lincoln_routes_chat.py`, `lincoln_tool_schemas.py`, `lincoln_database.py` | Fires mid-conversation, no approval, writes to `lincoln_memory_entries` |
| read_url tool | ✅ Live | `lincoln_routes_chat.py`, `lincoln_tool_schemas.py`, `lincoln_web_search.py` | In SEARCH_TOOLS tier, chains after web_search |
| web_search → read_url chaining | ✅ Live | `lincoln_routes_chat.py`, `lincoln_web_search.py` | Continuation directive injected into web_search result forces Qwen to call read_url |
| Globe pill always-on (P1) | ✅ Live | `lincoln_chat.js`, `lincoln_database.py`, `lincoln_routes_settings.py` | `_webSearchAlwaysOn` var, `web_search_always_on` DB key, pill locks when always-on active |
| MiniCPM vision wiring (P2) | ✅ Live | `lincoln_database.py`, `lincoln_routes_files.py`, `lincoln_settings.js` | `vision_model` DB setting → `minicpm-v4.5:8b`, exposed in Settings → Models |
| Context window indicator HTTP poll (P3) | ✅ Live | `lincoln_index.html`, `lincoln_main.css`, `lincoln_routes_chat.py`, `lincoln_chat.js` | Shows tok count + bar in topbar after response completes |
| Context window SSE update (P3b) | ✅ Live | `lincoln_routes_chat.py`, `lincoln_chat.js` | `ctx_update` SSE event fires before `_react_loop`, indicator appears during streaming |
| DDG retry logic (P4) | ✅ Live | `lincoln_web_search.py` | 3 attempts, 1s delay, then Google fallback |
| Search engine selector | ✅ Live | `lincoln_routes_settings.py`, `lincoln_settings.js`, `lincoln_database.py` | DDG / Google / DDG+fallback options in Settings → Web Search |
| Settings panel 860px tabbed | ✅ Live | `lincoln_settings.js`, `lincoln_main.css` | 10 tabs: Appearance, Chat, Prompts, RAG, Uploads, Web Search, Build Tools, Models, Infrastructure, Status |
| KaTeX dollar-sign fix | ✅ Live | `lincoln_chat.js` | Bare `$` removed as delimiter; only `$$`, `\[..\]`, `\(..\)` trigger math |
| Date injection in system prompt | ✅ Live | `lincoln_database.py` | `Today's date: {date.today().isoformat()}` injected in `get_active_system_prompt()` |
| Google API key / CSE ID in admin UI | ✅ Live | `lincoln_configuration.py`, `lincoln_routes_settings.py`, `lincoln_settings.js` | Admin mode, Infrastructure tab |
| Open Dev Terminal button | ✅ Live | `lincoln_routes_settings.py`, `lincoln_settings.js` | Opens cmd.exe, cds to Lincoln, activates venv |
| Git Reset Hard button | ✅ Live | `lincoln_routes_settings.py`, `lincoln_settings.js` | Runs `git reset --hard HEAD`, requires confirm() dialog |
| auto_save_memory background thread | ✅ Live | `lincoln_routes_history.py` | Memory button triggers extraction, daemon thread, returns 200 instantly |
| Denied tool trace card | ✅ Live | `lincoln_chat.js` | Greyed-out inline card after Deny, shows tool name + args |
| localStorage prompt draft cache | ✅ Live | `lincoln_chat.js` | Saves textarea on input, restores on DOMContentLoaded, clears on send |
| Exit project button | ✅ Live | `lincoln_sidebar.js` | "No Project" row at top of project list when a project is active |
| Sidebar fold toggle | ✅ Live | `lincoln_sidebar.js` | Collapse/expand with width animation |
| Project chat filter fix | ✅ Live | `lincoln_sidebar.js` | `loadHistory()` now filters by `project_id` |
| Delete chats inside project | ✅ Live | `lincoln_sidebar.js` | Delete button on session items, visible after filter fix |
| Version/codename DB-backed | ✅ Live | `lincoln_database.py`, `lincoln_settings.js` | Editable in admin mode, not hardcoded in `__init__.py` |
| Context window auto-sizing | ✅ Live | `lincoln_ollama_service.py` | `_RESPONSE_HEADROOM=0.40`, `_MIN_OUTPUT_TOKENS=2048`, per-request sizing |
| ASCII-127 token sanitizer | ✅ Live | `lincoln_routes_chat.py` | In `_react_loop`, prevents NTFS/WSL2 encoding corruption |
| System prompt 4 active blocks | ✅ Live | `lincoln_database.py` (seeded) | Lincoln persona, Life cycle, Memory Save Behavior, Tool Chaining Mandate |
| Four active DB system prompt blocks | ✅ Live | `lincoln_database.py` | Scope=global, persistent, survives restarts |
| Ban list checker | ✅ Live | `lincoln_ban_list_checker.py`, `lincoln_routes_chat.py` | Fires warning banner on OptionsPricing generated code |
| Version badge single-instance fix | ✅ Live | lincoln_index.html | Removed 2 duplicate sidebar-logo divs; one span with id="sidebarVersionDisplay" remains |
| Routes comment hygiene cleanup | ✅ Live | lincoln_routes_chat.py | Removed duplicate "ReAct loop" header (line 585) and stale P3 patch-instruction banner |

---

## 2. CONFIRMED PENDING (nothing as of 2026-07-23)

**The P1–P4 queue is fully complete.** There is no confirmed pending feature queue at this time. The next session should ask the user what to build next.

Items that remain aspirational / roadmap only (NOT in the active build queue):

- Execution isolation (subprocess → sandboxed env)
- Self-indexing (Lincoln RAG over own source, read-only)
- Self-introspection agentic (propose patches via Aider, never auto-apply)
- Model routing (specialist models per task type: Qwen → chat, qwen2.5-coder → code, MiniCPM → vision)
- QLoRA fine-tuning on RTX 5060 Ti 16GB
- Bloomberg/Schwab terminal data extraction pipeline
- Agentic web browsing (Playwright/Selenium via WSL)
- Duplicate version badge in topbar (Q5) — cosmetic, low priority
- lincoln_routes_chat.py comment hygiene (Q6) — cosmetic, low priority
---

## 3. ACTIVE FILE LOCKS

**Updated when either Claude instance begins patching a file. Cleared when deployment is confirmed.**

| File | Locked by | Task | Status |
|---|---|---|---|
| lincoln-roadmap.md | Project B | Adding T1-F (Memory edit/append UI) spec | Locked |

**Rule:** Before patching any file, check this table. If locked, coordinate with the other instance before proceeding.

---

## 4. FAILURE REGISTRY

Failures, dead ends, and known traps. Both instances must read this before debugging anything.

### F1: yield/return in generator functions (CRITICAL)
- **What failed:** `_react_loop()` in `lincoln_routes_chat.py` had both `yield` statements and `return value`. Python generators silently discard `return value` — only `StopIteration.value` gets it, which plain `for item in gen:` iteration never sees.
- **Symptom:** Tokens streamed fine. No errors in console or terminal. The `done` SSE event never fired. ReAct loop appeared to hang after tool execution.
- **Fix:** `yield (value_tuple)` then bare `return`. Caller checks `isinstance(item, tuple)` to capture it.
- **Never do:** Mix `yield` and `return value` in the same function.

### F2: tool_calls arguments as json.dumps() strings
- **What failed:** `_react_loop` was passing `tool_calls.arguments` as `json.dumps(dict)` — a string — rather than a native Python dict.
- **Symptom:** Silent 400 Bad Request from Ollama after tool execution. No error detail in response body.
- **Fix:** Pass native dict directly. Never call `json.dumps()` on arguments before sending to Ollama.

### F3: Missing tool_call_id on role:tool messages
- **What failed:** All three `role: "tool"` result messages in `_react_loop` were missing `"tool_call_id"` linking them back to the assistant's request.
- **Symptom:** Same as F2 — silent 400 after tool execution.
- **Fix:** Every `role: "tool"` message must have `"tool_call_id": tool_call_id`.

### F4: Phantom table in auto_save_memory
- **What failed:** `auto_save_memory` background thread was using raw SQL to write to `memory_entries` (a table that doesn't exist). No error thrown — silent data loss.
- **Fix:** Use `save_memory_entry()` helper → writes to `lincoln_memory_entries` (correct table).

### F5: Stale duplicate file at wrong path
- **What happened:** Two copies of `lincoln_routes_settings.py` existed — one at `lincoln/lincoln_routes_settings.py` (stale, wrong path) and one at `lincoln/app/routes/lincoln_routes_settings.py` (correct, what Flask loads). Gemini's edits went to the stale copy.
- **Symptom:** Settings saved successfully locally but features didn't work. Grep found the key in the wrong file.
- **Fix:** Always verify which path Flask is actually importing from (`from lincoln.app.routes.lincoln_routes_settings import...`) before patching.
- **Detection:** `Select-String -Path "B:\Homebrewed_AI\Lincoln\lincoln\*routes_settings*" -Pattern "web_search_always_on" -Recurse`

### F6: CDN edge cache on raw.githubusercontent.com
- **What happened:** Fetching a raw GitHub file returned old content even after a push. Led Project B (sister instance) to initially conclude the repo was out of sync, when the file on disk was correct.
- **Fix:** When verifying sync state, prefer `github.com/blob/main/<path>` view over `raw.githubusercontent.com`. Or fetch twice and compare.
- **Rule:** When a live fetch contradicts detailed specific documentation, suspect the fetch first, not the human's workflow.

### F7: marked.js renderer.code signature change at v9
- **What failed:** A `renderer.code` override written for marked v4/v5 used three positional args `(code, lang, escaped)`. marked v9+ passes a single token object `{type, raw, lang, text, escaped}`.
- **Symptom:** Code blocks rendered incorrectly after a version bump. No thrown error.
- **Lincoln pins:** marked@9.1.6 via CDN in `lincoln_index.html`. If that pin changes, re-verify the renderer.code signature.

### F8: Linux terminal launcher opens cmd.exe not PowerShell
- **What happened:** The "Open Dev Terminal" button in Settings launches `cmd.exe`. Array-slice commands like `Get-Content` are PowerShell-only and fail silently in cmd.
- **Fix:** For PowerShell commands, open separately via Win+R → `powershell`.

### F9: Git Desktop unknown authorship issue
- **Status:** Unresolved. Git Desktop occasionally refuses to commit due to unknown authorship configuration.
- **Workaround:** Manual file copy deployment. Don't assume Git Desktop push will work reliably.
- **Note:** Must be resolved before any automated deployment pipeline is built.

---

## 5. DECISION LOG

Decisions with rationale. Both instances treat these as authoritative unless explicitly superseded.

| ID | Decision | Rationale | Date | Reversible? |
|---|---|---|---|---|
| D1 | No Docker | User requirement. Local-first, no containerisation overhead. | Pre-v0.6.0 | No |
| D2 | No cloud inference | All inference via localhost:11434. Data never leaves machine. | Pre-v0.6.0 | No |
| D3 | Everything configurable via Settings UI | "Nothing hardcoded" guarantee. No editing Python files for config. | 2026-07-22 | No |
| D4 | Aider suggestion-only | Never auto-commit. User reviews all proposed changes. | Pre-v0.6.0 | No |
| D5 | ASCII-127 law for Fortran/Python source | Unicode causes silent encoding corruption at NTFS/WSL2 boundary and fatal crackfortran crashes. | 2026-07-22 | No |
| D6 | Patches as inline chat code blocks, not file artifacts | Artifacts corrupt indentation. Wastes tokens and time. | 2026-07-23 | No |
| D7 | Always fetch live GitHub URL before patching | Never patch from memory or prior context. Prior context can be stale. | 2026-07-23 | No |
| D8 | Select-String verification after deployment | Confirms file actually changed on disk before assuming deploy succeeded. | 2026-07-23 | No |
| D9 | Version/codename in DB, not __init__.py | Follows D3. Editable in admin mode from Settings UI. | 2026-07-22 | No |
| D10 | 3-tier tool system (SAFE/SEARCH/WRITE) | SAFE = autonomous, no approval. SEARCH = auto when web ON. WRITE = always approval card. | 2026-07-23 | Yes, with care |
| D11 | Continuation directive injected into web_search result | Qwen 3.5 9B ignores schema-level hints but respects explicit instructions in message history. Forces read_url chain. | 2026-07-23 | Yes |
| D12 | _RESPONSE_HEADROOM=0.40, _MIN_OUTPUT_TOKENS=2048 | 20% headroom caused synthesis cutoff during multi-tool sessions. 40% + 2048 floor prevents this. | 2026-07-23 | Yes |
| D13 | nomic-embed-text fixed as embed model | Not switchable from UI. Only the LLM model is switchable per session. | Pre-v0.6.0 | Yes, with re-index |
| D14 | minicpm-v4.5:8b as default vision_model DB setting | Pulled and confirmed working standalone via Ollama. Used for image/chart inputs. | 2026-07-23 | Yes |
| D15 | KaTeX only on explicit delimiters ($$, \[..\], \(..\)) | Bare $ caused financial text like "$200 billion" to be parsed as LaTeX. Critical for quant finance use case. | 2026-07-22 | Yes |

---

## 6. TERMINOLOGY

Shared vocabulary — if either instance uses these terms, they mean exactly this:

| Term | Definition |
|---|---|
| SAFE_TOOLS | Tool tier: executes autonomously, no approval card. Current members: `rag_query`, `read_file`, `save_memory` |
| SEARCH_TOOLS | Tool tier: executes automatically when web search toggle is ON. Current members: `web_search`, `read_url` |
| WRITE_TOOLS | Tool tier: always shows approval card before execution. Current members: `execute_python`, `execute_fortran`, `write_file`, `run_aider` |
| ReAct loop | `_react_loop()` in `lincoln_routes_chat.py` — the main agentic iteration loop |
| lincoln_memory_entries | The correct SQLite table name for memory. NOT `memory_entries` (phantom). |
| approval card | The inline UI card shown for WRITE_TOOLS requests, with Approve / Deny buttons |
| canvas | The code block management area in the right panel — run buttons, output panel |
| P1/P2/P3/P4 | The four priority items defined in LINCOLN_MASTER_HANDOFF.md. All four are now complete. |
| hard reload | Ctrl+Shift+R — required after JS/CSS changes to bypass browser cache |
| full restart | Ctrl+C + relaunch `lincoln_start.bat` — required after Python file changes |
| the stale duplicate | The now-deleted `lincoln/lincoln_routes_settings.py` at the wrong path (not to be confused with the correct `lincoln/app/routes/lincoln_routes_settings.py`) |

---

## 7. OPEN QUESTIONS

Things neither instance has fully resolved. Don't silently pick an answer — surface them here.

| ID | Question | Status | Owner |
|---|---|---|---|
| Q1 | Git Desktop authorship issue — what's the actual fix? | Unresolved (F9 above) | User to investigate |
| Q2 | Gemma4:12b code quality vs Qwen3.5:9b — which is better for code tasks? | Not benchmarked | Next session when relevant |
| Q3 | Should execution isolation (subprocess → sandbox) be P1 of the next build queue? | Not decided | Ask user |
| Q4 | How should the two Claude instances divide work? | Proposed model below in §8 | Both instances to agree | — |

---

## 8. DUAL-INSTANCE COLLABORATION MODEL

**Proposed** (not yet formally agreed — user to confirm):

**Project A (original — this instance):**
- Deep institutional memory. Knows the why behind decisions.
- Best for: incremental feature work, patch delivery, debugging sessions where history matters.
- Risk: assumptions baked in from 8 sessions. May miss things that "should" be obvious.

**Project B (sister — new instance on different machine):**
- Clean slate. No baked-in assumptions.
- Best for: independent audits, catching things Project A has normalized, fresh architectural review.
- Risk: missing institutional memory. May re-suggest things that were tried and rejected.

**Coordination rules:**
1. Before patching any file, check §3 (Active File Locks) above.
2. If both instances produce a patch for the same file in the same session, the user must reconcile manually — do NOT assume the later patch supersedes the earlier one.
3. All confirmed deployments update this document in the same session.
4. Conflicts between instances are flagged explicitly — not silently resolved.

---

## 9. ENVIRONMENT REFERENCE

**Machine:** Intel i7-10700, RTX 5060 Ti 16GB (Blackwell), ~30GB usable RAM
**OS:** Windows 11, WSL2 (Ubuntu 26.04)
**Lincoln root:** `B:\Homebrewed_AI\Lincoln\`
**DB:** `B:\Homebrewed_AI\Lincoln\data\lincoln_database.db`
**Launch:** `.\lincoln_start.bat` or desktop shortcut
**Ollama:** `localhost:11434`, models on B drive
**GitHub:** `github.com/gregorybarco/Lincoln`, branch `main`
**Flask:** `localhost:5000`, debug mode OFF (Python changes need full restart)
**Maple:** `D:\Maple\bin.X86_64_WINDOWS\cmaple.exe`
**Intel oneAPI:** `C:\Program Files (x86)\Intel\oneAPI`
**nvfortran:** `/opt/nvidia/hpc_sdk/Linux_x86_64/26.3/compilers/bin/nvfortran` (via WSL)

**Models in Ollama:**
- `qwen3.5:9b` — default chat/agentic (6.6GB)
- `gemma4:12b` — available, not benchmarked for code (7.6GB)
- `qwen2.5-coder:latest` — specialist code (4.7GB)
- `deepseek-coder:latest` — lightweight code (776MB)
- `minicpm-v4.5:8b` — vision/multimodal (6.1GB), wired as of 2026-07-23
- `nomic-embed-text` — fixed embed model

---

*End of lincoln-shared-memory.md*
*Both Claude instances should update this file at the end of every session where a deployment was confirmed.*
