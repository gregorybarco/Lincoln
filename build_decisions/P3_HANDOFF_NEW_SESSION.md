# LINCOLN P3 HANDOFF — Context Window Indicator
# For new Claude session — read this before doing anything.
# Date: 2026-07-23
# GitHub is source of truth — all P2 work is pushed and confirmed working.

---

## WHAT P3 IS

Add a token usage indicator to the topbar that shows:
  4,432 / 131,072 tok  3.4%
  [===                           ] (thin progress bar)

- Visible whenever a chat session is active
- Hidden on new session / no session
- Turns amber at 75%, red at 90%
- Updates after every response completes
- Uses same token estimation logic as lincoln_ollama_service.py (_estimate_tokens)

---

## CURRENT STATE

P2 (MiniCPM vision wiring) is fully complete and pushed to GitHub.
P3 has NOT been started. Zero changes made to any file for P3.
GitHub is the source of truth — fetch live files before writing any code.

---

## RAW FILE URLs (fetch before patching)

https://raw.githubusercontent.com/gregorybarco/Lincoln/main/lincoln/app/templates/lincoln_index.html
https://raw.githubusercontent.com/gregorybarco/Lincoln/main/lincoln/app/static/css/lincoln_main.css
https://raw.githubusercontent.com/gregorybarco/Lincoln/main/lincoln/app/routes/lincoln_routes_chat.py
https://raw.githubusercontent.com/gregorybarco/Lincoln/main/lincoln/app/static/js/lincoln_chat.js

---

## FOUR FILES TO CHANGE

### FILE 1 — lincoln_index.html
Insertion point (confirmed from live file):

FIND this exact block in the topbar:
      <div class="topbar-left">
        <span class="topbar-project-badge" id="topbarProjectBadge">No project</span>
        <span class="topbar-mode-badge">
          <i class="ti ti-lock" aria-hidden="true"></i>
          Suggestion mode
        </span>
      </div>

INSERT the ctx div INSIDE topbar-left, after the mode-badge span, before the closing </div>:
        <!-- Context window usage indicator -->
        <div id="ctxIndicator" class="ctx-indicator" style="display:none" title="Context window usage">
          <div class="ctx-indicator-labels">
            <span id="ctxTokensUsed">0</span>
            <span class="ctx-sep">/</span>
            <span id="ctxCeiling">–</span>
            <span class="ctx-unit">tok</span>
            <span id="ctxPercent" class="ctx-percent">0%</span>
          </div>
          <div class="ctx-bar-track">
            <div id="ctxBar" class="ctx-bar"></div>
          </div>
        </div>

No restart needed — hard reload only.

---

### FILE 2 — lincoln_main.css
Append to end of file:

/* ── Context window indicator (P3) ─────────────────────────────────────── */
.ctx-indicator {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-left: 12px;
  padding: 3px 8px;
  border-radius: var(--radius-sm, 4px);
  background: var(--bg-surface);
  border: 0.5px solid var(--border);
  min-width: 140px;
}

.ctx-indicator-labels {
  display: flex;
  align-items: baseline;
  gap: 3px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
}

.ctx-sep  { color: var(--text-muted); }
.ctx-unit { color: var(--text-muted); font-size: 10px; margin-left: 1px; }

.ctx-percent {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.ctx-percent.ctx-warn   { color: var(--text-warning, #f59e0b); }
.ctx-percent.ctx-danger { color: var(--text-danger,  #ef4444); }

.ctx-bar-track {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}

.ctx-bar {
  height: 100%;
  width: 0%;
  background: var(--accent, #6366f1);
  border-radius: 2px;
  transition: width 0.4s ease, background 0.3s ease;
}

.ctx-bar.ctx-bar-warn   { background: var(--text-warning, #f59e0b); }
.ctx-bar.ctx-bar-danger { background: var(--text-danger,  #ef4444); }

No restart needed — hard reload only.

---

### FILE 3 — lincoln_routes_chat.py
Append to end of file. RESTART REQUIRED after saving.

Key bug to avoid: model fallback must use LLM_MODEL from configuration,
NOT get_setting("LINCOLN_LLM_MODEL") — that key does not exist in the DB.
LLM_MODEL is already imported at the top of lincoln_routes_chat.py from
lincoln.lincoln_configuration.

Fetch the live file first to confirm LLM_MODEL is already imported.
If it is, just append this route:

@chat_blueprint.route("/api/chat/context_usage", methods=["GET"])
def context_usage():
    """
    Token usage estimate for current session vs model ceiling.
    Query params: session_id (int, required), model (str, optional)
    Returns: { tokens_used, ceiling, percent, model, warning }
    """
    from lincoln.lincoln_database import get_session_messages
    from lincoln.lincoln_ollama_service import resolve_hardware_ceiling

    session_id = request.args.get("session_id", type=int)
    model      = request.args.get("model", "").strip() or LLM_MODEL

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    try:
        messages    = get_session_messages(session_id)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        tokens_used = int((total_chars / 4) * 1.10)
        ceiling     = resolve_hardware_ceiling(model)
        percent     = round((tokens_used / ceiling) * 100, 1) if ceiling > 0 else 0.0

        return jsonify({
            "tokens_used": tokens_used,
            "ceiling":     ceiling,
            "percent":     percent,
            "model":       model,
            "warning":     percent >= 80.0,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

RESTART REQUIRED.

---

### FILE 4 — lincoln_chat.js
FETCH THE LIVE FILE FIRST.
Find:
  1. Where _isStreaming (or equivalent) is set to false after stream ends,
     OR where the final message render function is called after SSE completes.
     This is the call site for _updateCtxIndicator().
  2. The newSession() function — add _hideCtxIndicator() inside it.
  3. The return {} block at the bottom of the lincolnChat IIFE —
     add _updateCtxIndicator and _hideCtxIndicator to public exports if needed.

Add these two functions inside the lincolnChat IIFE before the return block:

  async function _updateCtxIndicator() {
    if (!_currentSessionId) return;
    const model = lincolnSettings.activeModel || '';
    try {
      const params = new URLSearchParams({ session_id: _currentSessionId });
      if (model) params.set('model', model);
      const res  = await fetch('/api/chat/context_usage?' + params.toString());
      if (!res.ok) return;
      const data = await res.json();

      const indicator = document.getElementById('ctxIndicator');
      const tokUsed   = document.getElementById('ctxTokensUsed');
      const ceiling   = document.getElementById('ctxCeiling');
      const pct       = document.getElementById('ctxPercent');
      const bar       = document.getElementById('ctxBar');
      if (!indicator) return;

      if (tokUsed) tokUsed.textContent = data.tokens_used.toLocaleString();
      if (ceiling) ceiling.textContent = data.ceiling.toLocaleString();

      const p = data.percent;
      if (pct) {
        pct.textContent = p.toFixed(1) + '%';
        pct.className   = 'ctx-percent' + (p >= 90 ? ' ctx-danger' : p >= 75 ? ' ctx-warn' : '');
      }
      if (bar) {
        bar.style.width = Math.min(p, 100) + '%';
        bar.className   = 'ctx-bar' + (p >= 90 ? ' ctx-bar-danger' : p >= 75 ? ' ctx-bar-warn' : '');
      }
      indicator.style.display = 'flex';
    } catch (_) {}
  }

  function _hideCtxIndicator() {
    const el = document.getElementById('ctxIndicator');
    if (el) el.style.display = 'none';
  }

No restart needed — hard reload only after Flask restart for File 3.

---

## DEPLOYMENT ORDER

1. Apply HTML change (File 1) — VS Code manual edit
2. Append CSS (File 2) — VS Code manual edit
3. Append Python route (File 3) — VS Code manual edit, then restart Flask
4. Add JS functions + call sites (File 4) — fetch live file first to find exact
   insertion points, then VS Code manual edit, then hard reload

---

## VERIFICATION

After deploy, open Lincoln, start a chat, send one message.
After the response completes, the topbar should show:
  [some number] / [ceiling] tok  [percent]%
  [progress bar]

Test the warning colours by checking what 75% and 90% look like —
or temporarily lower the thresholds in _updateCtxIndicator to 5% and 10%
to force amber/red without filling the context window.

After new session (New Chat button), indicator should disappear.

---

## WHAT COMES AFTER P3

Nothing in the confirmed queue. P3 was the last item.
New session should: read LINCOLN_MASTER_HANDOFF.md, check recent_chats,
audit memory, then ask the user what to build next.
