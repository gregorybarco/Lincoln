# LINCOLN ROADMAP
**Created:** 2026-07-23
**Authority:** This is the canonical record of Gregory's stated vision for Lincoln,
extracted from all chat sessions v0.4.1 through v0.7.4. Neither Claude instance
should treat anything here as "confirmed pending" — items move to the active build
queue only when the user explicitly says "build this next."
**Update rule:** Any session that surfaces a new long-term goal adds it here.
Completed items move to lincoln-shared-memory.md §1 and lincoln-master-handoff.md §10.

---

## TIER 0 — FOUNDATION (COMPLETE as of v0.7.4)

Everything below is confirmed live in GitHub main (ref: dcab251).

| Feature | Notes |
|---|---|
| ReAct loop (3-tier tool system) | SAFE / SEARCH / WRITE tiers |
| save_memory autonomous tool | Writes to lincoln_memory_entries mid-conversation |
| web_search → read_url chaining | Continuation directive forces Qwen to chain |
| Globe pill always-on | Pill locks when always-on active |
| MiniCPM vision wiring | vision_model DB setting → minicpm-v4.5:8b |
| Context window indicator (SSE) | Appears during streaming, updates after done |
| DDG retry + Google fallback | 3 retries, 1s delay |
| Settings panel 860px tabbed | 10 tabs, admin mode, Google keys, terminal, git reset |
| Per-project context injection | Injected into system prompt |
| Ban list checker | Fires on OptionsPricing protected symbols |
| Approval cards + denied trace | WRITE_TOOLS always show approval card |
| KaTeX financial-safe rendering | Bare $ removed as delimiter |
| Date injection in system prompt | Today's date injected at get_active_system_prompt() |
| Admin mode UI | Version/codename DB-backed, editable from Settings |

---

## TIER 1 — INTELLIGENCE LAYER (next logical build phase)

These are the features closest to the existing foundation. Build these before
attempting Tier 2 or Tier 3.

### T1-A: Model Routing by Task Type
**What:** Lincoln auto-selects the right model based on what it detects in the message.
No more manual model pill switching.
**Routing logic (proposed):**
- Code generation / debugging → `qwen2.5-coder:latest`
- Vision / chart / image inputs → `minicpm-v4.5:8b`
- Lightweight fast tasks → `deepseek-coder:latest`
- Default conversation / research / agentic → `qwen3.5:9b`
**Files likely touched:** `lincoln_ollama_service.py`, `lincoln_routes_chat.py`,
`lincoln_tool_schemas.py`, `lincoln_chat.js` (model pill UI update)
**Decision needed:** Whether model routing is per-message or per-session.
**Status:** Not started.

### T1-B: Self-Indexing
**What:** Lincoln RAG-indexes its own source code into a separate ChromaDB collection
so it can answer questions about its own architecture, find its own functions,
and propose targeted patches.
**Constraint:** Read-only. Lincoln never modifies its own source autonomously.
**Files likely touched:** `lincoln_rag_index_service.py`, `lincoln_database.py`
(new collection), `lincoln_routes_projects.py` (trigger re-index on deploy)
**Status:** Not started.

### T1-C: Multi-Iterative Web Search
**What:** After `web_search → read_url`, Lincoln evaluates whether it has enough
information and decides to search again with a refined query. True research loop
rather than single-fire search.
**Current state:** Continuation directive forces one read_url chain. Model stops
after that and synthesizes. Does not re-search.
**Files likely touched:** `lincoln_routes_chat.py` (_react_loop), system prompt
(Tool Chaining Mandate block needs updating)
**Status:** Not started.

### T1-D: Think Mode (Fast / Normal / Deep)
**What:** Collapsible reasoning block with visible streaming of Qwen's
`<think>...</think>` tokens. Three modes: suppress thinking (Fast),
show collapsed (Normal), show expanded (Deep).
**History:** Was built in v0.5.x. Regressed and not confirmed live in v0.7.4.
Needs rebuild against current ReAct loop.
**Files likely touched:** `lincoln_routes_chat.py`, `lincoln_chat.js`,
`lincoln_index.html`, `lincoln_main.css`
**Status:** Regressed — needs rebuild.

### T1-E: Execution Isolation
**What:** Python/Fortran execution currently runs via raw subprocess. Needs a proper
isolated environment (restricted imports, timeout enforcement, no filesystem write
outside designated sandbox path) before Lincoln can be trusted with autonomous
code execution.
**Constraint:** No Docker. Isolation via Python `multiprocessing` + restricted
builtins or a chroot-style WSL sandbox.

### T1-F: Memory Edit/Append UI
**What:** Manual CRUD interface for `lincoln_memory_entries` in the sidebar
memory panel. Inline edit on existing entries (click entry → editable → save)
and an "Add memory" button for manual append. Tag dropdown locked to the six
existing tags (`preference`, `decision`, `constraint`, `fact`, `code_style`, `persona`).
**Constraint:** Not a ReAct tool — no approval card. Pure UI CRUD, user-initiated
only. All writes go through `save_memory_entry()`, never raw SQL (per F4).
**Files likely touched:** `lincoln_routes_history.py` (backend), `lincoln_sidebar.js`
(frontend memory panel)
**Status:** ✅ Complete — deployed and verified 2026-07-24. Moved to
lincoln-shared-memory.md §1 and lincoln-master-handoff.md §6/§10.

---

## TIER 2 — AGENTIC CAPABILITIES

Build after Tier 1 is solid. These extend Lincoln's reach beyond the local machine.

### T2-A: Self-Introspection Agentic (Self-Building)
**What:** Lincoln reads its own source (via T1-B self-indexing), identifies a needed
change, generates a patch, and presents it to you via Aider for approval.
You approve → Aider applies → Lincoln re-indexes itself → loop continues.
**This is the self-building agent vision.**
**Constraint:** Aider always suggestion-only. Never auto-commits. User reviews every diff.
**Dependencies:** T1-B (self-indexing) must be live first.
**Files likely touched:** `lincoln_routes_chat.py` (new tool: `propose_patch`),
`lincoln_tool_schemas.py`, `lincoln_git_service.py`
**Status:** Not started.

### T2-B: Playwright / Selenium Agentic Web Browsing
**What:** Lincoln can navigate real websites, fill forms, extract structured data,
and return results to the ReAct loop. Runs via WSL2.
**Use cases:** Job application automation, data extraction from web portals,
testing financial data pages.
**Files likely touched:** New `lincoln_browser_service.py`, `lincoln_tool_schemas.py`,
`lincoln_routes_chat.py`
**Status:** Not started.

### T2-C: Bloomberg / Schwab Data Extraction Pipeline
**What:** OCR of Bloomberg terminal screenshots (Tesseract already wired) extended
into a structured extraction pipeline. Parses options chains, prices, Greeks,
tickers from screenshots and writes structured records to SQLite and/or RAG.
**Current state:** Tesseract OCR is live for general screenshots. The finance-specific
extraction pipeline (field recognition, structured output, DB write) was never built.
**Files likely touched:** `lincoln_ocr_service.py`, new `lincoln_finance_extract.py`,
`lincoln_database.py` (new tables)
**Status:** Not started.

### T2-D: Aider Propose-Patch Loop
**What:** Extension of T2-A. Lincoln can autonomously propose multi-file patches,
present diffs in the UI, and apply them on approval. Goes beyond T2-A by handling
cross-file changes and managing the apply → test → re-index cycle.
**Dependencies:** T2-A must be live first.
**Status:** Not started.

---

## TIER 3 — TRAINING AND DOMAIN SPECIALIZATION

The most complex phase. Requires Tier 1 and Tier 2 to be stable.

### T3-A: QLoRA Fine-Tuning Pipeline on RTX 5060 Ti 16GB
**What:** Fine-tune a base model (likely Qwen or deepseek-coder) on proprietary
OptionsPricing + BARCO Fortran/Python codebase using QLoRA (4-bit quantized
LoRA adapters). Target: a model that understands BARCO's mathematical conventions,
variable naming, and domain-specific patterns without hallucinating.
**Hardware:** RTX 5060 Ti 16GB (Blackwell, CUDA). 16GB VRAM is sufficient for
QLoRA on 7B-class models.
**Toolchain:** PyTorch, Hugging Face Transformers, PEFT (LoRA), bitsandbytes.
**Constraint:** Training data is proprietary — never leaves the machine.
**Status:** Not started. Listed on resume as v1.0.0 milestone.

### T3-B: Finance Domain Weight Training
**What:** Beyond LoRA adapters — full domain adaptation of model weights to
quantitative finance. Options pricing theory, Greeks, Fortran numerical methods,
BARCO conventions. Requires labeled training data, evaluation harness, and
iterative fine-tuning runs.
**Dependencies:** T3-A pipeline must be live and validated first.
**Status:** Not started.

### T3-C: True Air-Gap Mode
**What:** Lincoln confirmed working with all network access disabled. All models
local (Ollama), all data local (SQLite + ChromaDB), web search disabled, no
outbound calls of any kind. A network kill-switch or offline mode toggle in Settings.
**Current state:** DDG/Google search requires internet. Lincoln has no offline mode.
**Files likely touched:** `lincoln_web_search.py`, `lincoln_routes_settings.py`,
`lincoln_settings.js` (offline mode toggle), `lincoln_configuration.py`
**Status:** Not started.

### T3-D: Parallel Multi-Agent with Shared Memory Pool
**What:** Two or more Lincoln agents running in parallel, each with a specialist
role (research agent, code agent, synthesis agent), sharing the same SQLite
`lincoln_memory_entries` table. Coordinator agent decomposes tasks and delegates.
**Dependencies:** Tier 1 + Tier 2 must be stable. Execution isolation (T1-E) required.
**Status:** Conceptual only. Not designed.

---

## GUIDING PRINCIPLES (from Gregory's stated vision across all sessions)

1. **Air-gapped first.** Everything runs locally. Data never leaves the machine.
   Web search is a tool Lincoln uses — not a dependency Lincoln requires.

2. **Modeled after Claude.** The behavior, tool tiers, memory system, approval gates,
   streaming UX — Lincoln behaves like Claude but runs on local hardware and is
   trained on proprietary work.

3. **Self-building agent.** The end state is Lincoln proposing and applying its own
   improvements under human review. Not autonomous — supervised. But the loop
   exists and Lincoln participates in it.

4. **Strong suits routing.** No single model is best at everything. Lincoln routes
   to the right model for the right task. The user never has to think about which
   model to pick.

5. **Domain-trained weights.** General models are the starting point. The finish
   line is a model that understands BARCO's Fortran, OptionsPricing conventions,
   and quantitative finance at a level no general model achieves.

6. **Supports future research.** Lincoln is the research infrastructure. Options
   pricing, translation work, financial data pipelines, code development — Lincoln
   serves all of it. The architecture must not optimize for any single use case.

7. **No Docker. No cloud. No hardcoded config.** These three constraints are
   permanent and architectural.

---

## BUILD ORDER RECOMMENDATION

When ready to start building beyond v0.7.4, suggested sequence:
T1-D (Think Mode rebuild) ← quick win, regression fix
T1-A (Model routing) ← highest daily-use impact
T1-E (Execution isolation) ← safety prerequisite for autonomous code
T1-B (Self-indexing) ← prerequisite for T2-A
T1-C (Multi-iterative search) ← research quality improvement
T2-A (Self-introspection) ← first step toward self-building
T2-B (Playwright browsing) ← extends reach beyond local
T2-C (Bloomberg/Schwab pipeline)← domain data ingestion
T2-D (Aider propose-patch loop) ← full self-building loop
T3-A (QLoRA fine-tuning) ← begin domain training
T3-B (Finance domain weights) ← domain specialization complete
T3-C (True air-gap mode) ← full offline confirmation
T3-D (Multi-agent) ← final tier, parallel agents
---

*End of lincoln-roadmap.md*
*Update this file whenever a new goal is stated or a roadmap item completes.*
*Completed items: move to lincoln-shared-memory.md §1 and lincoln-master-handoff.md §10.*