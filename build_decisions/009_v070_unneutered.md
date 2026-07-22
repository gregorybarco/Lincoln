# 009 — v0.7.0 "Unneutered" — Token Limits, Tool Awareness, Multi-File, Protected Functions

**Date:** 2026-07-21
**Status:** Accepted

---

## Context

Lincoln v0.6.1 was functionally complete but had several compounding problems
that made it less capable than the underlying model actually is:

1. **Response truncation** — Lincoln's code responses were being cut off
   mid-function. The model was "neutered": full capability but constrained
   output. Root cause was two independent issues (see below).

2. **Tool blindness** — The LLM had no knowledge of what tools were available.
   When asked to read a Bloomberg screenshot, Qwen said "I don't have access
   to OCR." It does. The tool manifest was simply never injected.

3. **Single-file upload** — The file picker only allowed one file at a time.
   Attaching multiple files for cross-file analysis required separate messages.

4. **Prompt block + button** — The "+ Add instruction block" button in Settings
   was firing 400 errors. The JS code was correct; investigation confirmed the
   route is also correct. The issue was an on-blur race condition in some
   browsers where the first PATCH fired before the POST completed.

5. **No project context window** — There was no per-project free-text
   instructions field. Project-specific behaviour required editing global prompts.

6. **No file management** — No way to view or delete files inside a project's
   RAG source path from the UI.

7. **Canvas files in Git** — Old canvas files were already tracked before
   .gitignore was updated. A separate cleanup guide was written.

---

## Decisions

### D1 — num_predict = -1 (permanent, both chat() and stream_chat())

`num_predict` was not set in any Ollama payload. Ollama defaults vary by
version: some default to -1 (unlimited), others to 128. On this machine with
the current Ollama build, the default was causing responses to hard-stop at
~128 tokens. Setting `num_predict: -1` explicitly ensures unlimited output
on every request.

This is not a workaround -- this is the correct setting for an assistant that
generates code. A code function can easily exceed 128 tokens.

### D2 — Context window response headroom (20%)

`resolve_num_ctx_for_request()` was sizing the window to fit the input tokens
exactly. This left the model fighting for output space. The window now pads
by 20% (`tokens_with_headroom = estimated_input / 0.80`) so the model always
has room to write a complete code response before reaching the context limit.

### D3 — Tool manifest injected into every system prompt

`build_messages_with_rag_context()` now appends a `TOOL_MANIFEST` block to
the system prompt if the string "LINCOLN TOOL MANIFEST" is not already present.
The manifest is assembled from DB settings at call time so it reflects the
actual installed tools on this machine.

The manifest covers: Python/Jupyter, Fortran/nvfortran, C/C++/WSL, Julia/R/Bash,
Maple/cmaple, OCR/Tesseract, vision model, document parsing, multi-file upload,
web search, RAG, memory, Aider, Git, and self-inspection (own source code path).

**Non-negotiable:** The LLM must never say "I don't have access to that tool"
for a tool that Lincoln has. This fix is permanent.

### D4 — Multi-file upload (JS + backend)

`_openNativePicker()` sets `input.multiple = true`. Files are uploaded in
sequence, each added to `_pendingFiles[]` array. The pending chip shows a
count badge for multiple files. The payload sends `file_ids[]` array. The
backend (`lincoln_routes_chat.py`) concatenates all file blobs in order with
labelled headers. Legacy `file_id` (single) is still accepted.

### D5 — Protected function ban list

`PROTECTED_FUNCTIONS.md` added to `build_decisions/`. Lists all Lincoln JS
namespaces, critical methods, protected HTML IDs, and Python functions that
must not be overwritten by generated code.

`lincoln_ban_list_checker.py` extended with `_PROTECTED_PATTERNS` loaded at
module level. These fire WARNING banners (not blocks) so the user retains
the final decision. The banner text explains exactly what would break and why.

### D6 — Per-project context window

`lincoln_projects` table gains a `context TEXT DEFAULT ''` column via additive
migration. `get_project_context()` and `set_project_context()` added to
`lincoln_database.py`. New routes `GET/POST /api/projects/<id>/context` in
`lincoln_routes_projects.py`. Injection happens in `lincoln_routes_chat.py`
after global prompt blocks and before RAG context.

### D7 — Project file management routes

`GET /api/projects/<id>/files` returns a file listing of the RAG source path
with metadata (name, relative path, size_kb, extension, is_indexable).

`DELETE /api/projects/<id>/files` deletes a file (with path traversal guard)
and triggers a background re-index automatically.

---

## Files Changed

| File | Change |
|---|---|
| `lincoln/lincoln_ollama_service.py` | D1: num_predict=-1, D2: headroom, D3: tool manifest |
| `lincoln/lincoln_ban_list_checker.py` | D5: protected function patterns |
| `lincoln/lincoln_database.py` | D6: context column migration + helpers |
| `lincoln/lincoln_routes_chat.py` | D4: file_ids[], D6: context injection |
| `lincoln/lincoln_routes_projects.py` | D6: context routes, D7: file management routes |
| `lincoln/app/static/js/lincoln_chat.js` | D4: multi-file upload, _pendingFiles[] array |
| `build_decisions/PROTECTED_FUNCTIONS.md` | D5: protected symbol registry |
| `build_decisions/009_v070_unneutered.md` | this ADR |
| `build_decisions/GIT_CANVAS_CLEANUP.md` | canvas file git cleanup guide |

---

## What Was NOT Changed

- `lincoln_settings.js` — addPromptBlock() is correct. The 400 error was
  intermittent and browser-specific. If it recurs, the fix is to add a 50ms
  debounce between the POST and any subsequent PATCH. Not changed until
  confirmed reproducible.
- `lincoln_index.html` — Project context textarea and file list UI are deferred
  to the next session (v0.7.1). The routes exist; the UI panel needs updating.
- Model selector — confirmed working in v0.6.1 patch. Not changed.
- Ollama model download — confirmed: Ollama app downloads to the correct location
  and models appear in the pill automatically via `/api/models`. No change needed.
