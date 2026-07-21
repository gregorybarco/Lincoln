# ADR-008: Lincoln v0.6.0 Navigator — Architectural Decisions
# ASCII-127 compliant.

---

## Summary

This ADR documents every architectural decision made during the v0.6.0 Navigator
release. It covers multi-select UX, settings centralisation, admin mode, language
extensions, system prompt architecture, web search wiring, Aider WSL mode, RTL
language support, the ban list checker, the retrieval-only RAG fix, upload cleanup,
and Windows launcher.

---

## Decision 1: System Prompt Fully Editable from UI

Previously: Lincoln's persona was a hardcoded string inside lincoln_ollama_service.py,
invisible to the user and impossible to edit without touching source code.

New architecture: A lincoln_system_prompts table in SQLite stores ordered prompt
blocks, each with a label, content textarea, enabled toggle, and sort_order. The
table is pre-seeded with the default persona and formatting rules at first run.

get_active_system_prompt(project_id) assembles the final system prompt by
concatenating all enabled global blocks, then all enabled project blocks, in
sort_order. The assembled string is passed into build_messages_with_rag_context().

Nothing is hardcoded in lincoln_ollama_service.py. The function receives the
assembled prompt as a parameter.

UI: Settings -> Prompts & Persona shows each block as a labelled textarea (not
inline code display). Changes save on blur (textarea onblur). New blocks can be
added. Blocks can be reordered, disabled, or deleted. Project-level instructions
appear in the project settings panel.

Rationale: The user is the creator and must have complete control over how Lincoln
behaves. No value that affects Lincoln's response should be unreachable from the UI.

---

## Decision 2: Settings Centralisation -- Nothing Hidden Guarantee

All values that affect Lincoln's behaviour are now visible in the Settings panel.

User-editable settings (no restart): stored in lincoln_settings DB table.
New keys added in v0.6.0:
  history_limit, upload_max_text_kb, upload_max_doc_mb, upload_retention_days,
  ollama_timeout_sec, sidebar_show_project_chats, rag_snippet_chars,
  aider_launch_mode, web_search_enabled, nvfortran_path, f2py_fcompiler_flag,
  wsl_distro, maple_path, oneapi_path.

Infrastructure settings (restart required): stored in .env, displayed in the
Infrastructure section of Settings. They are greyed out until admin mode is enabled.

Admin mode: a toggle button at the bottom of the Infrastructure section. When enabled,
all .env fields become editable and Save buttons appear. Clicking Save calls
POST /api/settings/env which writes back to .env via write_env_key() in
lincoln_configuration.py. A confirmation note appears: "Restart Lincoln for this
change to take effect."

Admin mode does not require a password. The user is the sole operator of this local
system. The visual lock icon and warning text are sufficient to prevent accidental
edits during normal operation.

The embed model and chunk size fields show an additional warning: "Changing this
requires re-indexing all projects."

---

## Decision 3: Multi-Select Architecture

Applies to: sidebar history list, memory panel.

Checkboxes appear on hover of each item (always visible on mobile). The checkbox
label is a full-height click target to maximise tap accuracy.

Shift+click: selects the range between the last clicked item and the current item
(inclusive). Works on both history and memory lists independently. The last clicked
index is tracked per list.

Ctrl+A: selects all visible items in the list that currently has focus.

Escape: clears selection if the chat input does not have focus. If focus is in the
chat input, Escape only blurs the input. The global Escape handler in lincoln_chat.js
checks document.activeElement before acting. Priority: modal overlay -> settings
overlay -> think dropdown -> canvas selection -> sidebar selection.

Selection toolbar: slides in above the list when any item is selected. Shows count
badge, Delete selected (with confirm), Select all, Clear (X). Toolbar disappears
when count returns to 0.

Delete key: when sidebar list has focus and items are selected, triggers bulk delete
with confirm.

---

## Decision 4: Web Search Wiring

Previously: the "search " command prefix in the chat input fired a fetch() to
/api/chat/send but never read the SSE stream. The response was discarded. Bug B3.

New implementation:
  - The "search " prefix is removed. No hidden command shortcuts.
  - A globe icon pill appears in the input bar next to the think mode pill.
  - Clicking the globe toggles web search active for the NEXT message only (per-message,
    not per-session). After send, the pill resets to inactive.
  - When active, /api/chat/send receives use_web_search: true.
  - The route calls lincoln_web_search.search(user_text), formats the results, and
    prepends them to the system prompt as a labelled context block.
  - The SSE stream sends a 'web_search' event with result_count for the UI to display
    a transient indicator ("3 web results used").

No separate /api/search route is needed. The injection happens inside the existing
/api/chat/send stream so the user sees one unified response.

---

## Decision 5: Aider WSL Mode (Bug B8)

The current launch opened a Windows cmd window with "aider". For OptionsPricing
and other WSL-native projects, this is wrong: nvfortran, f2py, and the Python venv
all live in WSL, not in Windows PATH.

New behaviour: a per-setting "aider_launch_mode" (cmd | wsl) stored in DB settings.

When wsl: subprocess.Popen launches wsl.exe -d {wsl_distro} -- bash -c
"cd {wsl_path} && aider; exec bash". The Windows path is auto-translated using
drive-letter-to-/mnt/ mapping.

B:\OptionsPricing -> /mnt/b/OptionsPricing

This opens a real WSL terminal with the correct environment. Aider can then call
nvfortran, f2py, and the project venv correctly.

wsl_distro defaults to "Ubuntu" (confirmed: Ubuntu 26.04 LTS "resolute").

---

## Decision 6: Retrieval-Only RAG (No Hidden Second LLM Call)

Previously: query_project_index() called query_engine.query(question) which made
a full hidden LLM call inside LlamaIndex before the user saw any tokens. The
synthesised answer was then injected into the main streaming call. Two LLM calls
per RAG query, the first hidden and non-streaming.

New behaviour: query_project_index() uses retriever.retrieve(question) which performs
only vector similarity search and returns raw node chunks. The chunks are formatted
as labelled code blocks and returned as the 'answer' field. This is injected directly
into the system prompt.

Effect: one LLM call per user message (the streaming one). Latency reduction
proportional to the first LLM call (typically 5-15 seconds on qwen3.5:9b). No
silent failure point from the hidden call timing out.

---

## Decision 7: RAG Path Fix (Bug B2)

build_project_index() and dry_run_project() previously used:
  raw_path = project.get("code_path") or project.get("path") or ""

This is wrong. code_path is the Aider editing target, not the RAG source.
If code_path is set to a subfolder (e.g. lincoln/ package only), the index
silently excluded all other project files.

Correct logic (_resolve_rag_source_path):
  If path is set and != '.': use path as RAG source.
  If path == '.' (conversation-only project): use code_path as fallback if set.
  Otherwise: return None (no folder configured).

---

## Decision 8: Language Extensions

Added in v0.6.0 for file attach and RAG indexing:
  Julia (.jl), MATLAB/Octave (.m), Mathematica (.nb), Wolfram Language (.wl),
  R Markdown (.Rmd), SAS (.sas), Stata (.do, .ado),
  GAMS (.gms), AMPL (.ampl), LP format (.lp), MPS format (.mps),
  Maple worksheets (.mw -- XML extraction), Maple procedures (.mpl, .maple, .mm).

Human language support (RTL detection):
  Russian, Urdu, Hindi, Punjabi (Gurmukhi LTR + Shahmukhi RTL), Bhojpuri, Bangla,
  Arabic, French, German, Japanese, Chinese (Simplified + Traditional).

RTL implementation: dir="auto" on all .message-bubble elements. The browser's
Unicode bidirectional algorithm handles script detection automatically. No per-message
language detection needed.

---

## Decision 9: Ban List Checker

lincoln_ban_list_checker.py scans AI-generated code for patterns banned in the
OptionsPricing project per ProjectA_CODE_PRACTICES.md Section 2.

Patterns checked:
  - ctypes import (f2py bridge only)
  - subprocess cross-OS Popen
  - JSON pointer files
  - gfortran reference
  - Hardcoded Windows drive letter paths
  - Python math injected into .sh pipeline
  - numpy/scipy numerical math (should stay in Fortran)
  - Sequential optimizer dispatch
  - CMake usage
  - Non-ASCII characters (ASCII-127 law)

The checker runs on every response that contains a code block and a project_id.
It does not block or modify the response. It emits a 'ban_check' SSE event after
the 'done' event. The UI renders a collapsible warning banner listing violations
with pattern name, reason, and line number.

The check is lightweight (regex) and adds < 1ms latency.

---

## Decision 10: Upload Cleanup

lincoln_cleanup_service.py runs at startup and deletes files in data/uploads/
whose mtime is older than upload_retention_days (default 30, configurable in UI).

Runs once synchronously before Flask starts serving requests. No background thread.
For 30 days of typical use the scan completes in milliseconds.

---

## Decision 11: Windows Launcher

lincoln_start.bat uses a PowerShell TcpClient loop to poll port 5000 before
opening the browser. No fixed timeout. The terminal window starts minimized
(/min) so it appears in the taskbar for live log monitoring without stealing focus.

lincoln_create_shortcut.bat creates Start Menu and Desktop shortcuts via
WScript.Shell.CreateShortcut(). Run once after deployment.

The icon (lincoln.ico) is generated by lincoln_icon_generator.py using Pillow.
The design: capital L in gold (#c9a84c) on a dark charcoal (#1e1e2e) rounded
rectangle background. Multi-resolution: 16x16 through 256x256.

---

End of ADR-008.
