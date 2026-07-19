/**
 * Lincoln Chat  v0.5.1
 * =====================
 * Changes from v0.4.1:
 *   - Thinking mode toggle: Fast / Normal / Deep (like Claude's Low/Medium/Max/Thinking)
 *     Fast   → think=false, immediate first token
 *     Normal → think=false, default (same speed, labelled clearly)
 *     Deep   → think=true, streams reasoning into collapsible block before answer
 *   - Fix: <think> tokens no longer corrupt the response bubble.
 *     THINK_START / THINK_END markers from backend route thinking tokens to a
 *     separate collapsible <details> block — response text is always clean.
 *   - think_mode sent with every /api/chat/send request
 */

const lincolnChat = (() => {

  let _sessionId       = null;
  let _activeProjectId = null;
  let _activeProject   = null;
  let _isStreaming     = false;
  let _pendingFileId   = null;   // file_id from /api/files/upload
  let _pendingFileName = null;

  // ── Thinking mode ─────────────────────────────────────────────────────────
  // Cycles: fast → normal → deep → fast
  // fast/normal both suppress thinking (think=false); deep enables it (think=true).
  const _THINK_MODES = ['fast', 'normal', 'deep'];
  const _THINK_LABELS = {
    fast:   { label: '⚡ Fast',   title: 'Fast — no reasoning, immediate response' },
    normal: { label: '◎ Normal', title: 'Normal — balanced, no reasoning overhead' },
    deep:   { label: '🧠 Deep',  title: 'Deep — full chain-of-thought reasoning (slower)' },
  };
  let _thinkMode = 'normal';   // default

  function cycleThinkMode() {
    const idx   = _THINK_MODES.indexOf(_thinkMode);
    _thinkMode  = _THINK_MODES[(idx + 1) % _THINK_MODES.length];
    _updateThinkButton();
  }

  function _updateThinkButton() {
    const btn = document.getElementById('thinkModeBtn');
    if (!btn) return;
    const meta     = _THINK_LABELS[_thinkMode];
    btn.textContent = meta.label;
    btn.title       = meta.title;
    btn.dataset.mode = _thinkMode;
    // Visual accent for deep mode
    btn.classList.toggle('think-mode-deep', _thinkMode === 'deep');
  }


  // ── Init ──────────────────────────────────────────────────────────────────
  // DO NOT create a session here — only load context strip.
  // Session is created lazily on first message send.

  async function init() {
    await _loadContextStrip();
    _updateThinkButton();   // set initial label on the think toggle button
  }


  // ── Session management ────────────────────────────────────────────────────

  async function _ensureSession() {
    if (_sessionId) return;
    try {
      const res     = await fetch('/api/chat/session', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ project_id: _activeProjectId }),
      });
      const session = await res.json();
      _sessionId    = session.id;
      // Refresh history immediately so the new chat appears in the sidebar
      if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadHistory();
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  }

  async function newSession() {
    // Show home screen — session created lazily on first message
    _sessionId = null;
    _clearMessages();
    _clearPendingFile();
    if (typeof lincolnCanvas !== 'undefined') lincolnCanvas.clear();
  }

  async function loadSession(sessionId) {
    try {
      const res      = await fetch(`/api/history/${sessionId}`);
      const messages = await res.json();
      _sessionId     = sessionId;
      _clearMessages();
      _hideWelcome();
      _clearPendingFile();
      // Clear canvas then restore only THIS session's code blocks
      if (typeof lincolnCanvas !== 'undefined') lincolnCanvas.clear();

      messages.forEach(msg => {
        if (msg.role === 'user') {
          _appendUserMessage(msg.content);
        } else if (msg.role === 'assistant') {
          _appendAssistantMessage(msg.content, []);
          // Re-pin code blocks to canvas on restore
          if (typeof lincolnCanvas !== 'undefined') {
            const blocks = lincolnCanvas.extractCodeBlocks(msg.content);
            blocks.forEach(block => lincolnCanvas.pinCodeBlock({
              language:    block.language,
              filename:    _guessFilename(block.content, block.language),
              content:     block.content,
              projectName: _activeProject?.display_name || '',
              sessionId:   sessionId,
            }));
          }
        }
      });
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  }

  function setActiveProject(projectId, project) {
    _activeProjectId = projectId;
    _activeProject   = project;
  }


  // ── Send message ──────────────────────────────────────────────────────────

  async function sendMessage() {
    const input = document.getElementById('chatInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text || _isStreaming) return;

    // Lazily create session on first message
    await _ensureSession();

    if (text.startsWith('search ')) return _handleWebSearch(text.slice(7).trim(), input);
    if (text.startsWith('fetch '))  return _handleFetch(text.slice(6).trim(), input);

    input.value = '';
    autoResizeTextarea(input);
    _hideWelcome();

    // Show user message — include file chip if pending
    const displayText = _pendingFileName
      ? `📎 ${_pendingFileName}\n\n${text}`
      : text;
    _appendUserMessage(displayText);

    const fileId       = _pendingFileId;
    const pendingName  = _pendingFileName;
    _clearPendingFile();

    _setStreaming(true);

    const assistantEl  = _appendAssistantMessage('', []);
    const bubbleEl     = assistantEl.querySelector('.message-bubble');
    const cursor       = document.createElement('span');
    cursor.className   = 'streaming-cursor';
    bubbleEl.appendChild(cursor);

    // Thinking block — created on demand when THINK_START arrives
    let thinkEl        = null;   // <details> element
    let thinkBodyEl    = null;   // <div> inside it receiving reasoning tokens
    let inThinkBlock   = false;
    let thinkText      = '';

    let fullText = '';
    let sources  = [];

    function _ensureThinkBlock() {
      if (thinkEl) return;
      thinkEl = document.createElement('details');
      thinkEl.className = 'think-block';
      thinkEl.innerHTML = '<summary class="think-summary">Reasoning <span class="think-spinner"></span></summary>';
      thinkBodyEl = document.createElement('div');
      thinkBodyEl.className = 'think-body';
      thinkEl.appendChild(thinkBodyEl);
      // Insert before the bubble so it appears above the answer
      bubbleEl.parentNode.insertBefore(thinkEl, bubbleEl);
    }

    try {
      const response = await fetch('/api/chat/send', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          session_id:  _sessionId,
          message:     text,
          model:       lincolnSettings?.activeModel || 'qwen3.5:9b',
          project_id:  _activeProjectId,
          use_rag:     !!_activeProjectId,
          file_id:     fileId || null,
          think_mode:  _thinkMode,
        }),
      });

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));

            // ── think_mode handshake ──────────────────────────────────────
            if (event.type === 'think_mode') {
              // acknowledged — no UI action needed
            }

            // ── token ─────────────────────────────────────────────────────
            if (event.type === 'token') {
              const content = event.content;

              if (content === 'THINK_START') {
                inThinkBlock = true;
                _ensureThinkBlock();
              } else if (content === 'THINK_END') {
                inThinkBlock = false;
                // Replace spinner with token count
                if (thinkEl) {
                  const words = thinkText.trim().split(/\s+/).length;
                  thinkEl.querySelector('summary').innerHTML =
                    `Reasoning <span class="think-token-count">${words} words</span>`;
                }
              } else if (inThinkBlock) {
                thinkText += content;
                if (thinkBodyEl) {
                  thinkBodyEl.textContent = thinkText;
                  _scrollToBottom();
                }
              } else {
                // Normal response token — this is the text that shows in the bubble
                fullText += content;
                bubbleEl.textContent = fullText;
                bubbleEl.appendChild(cursor);
                _scrollToBottom();
              }
            }

            // ── sources ───────────────────────────────────────────────────
            if (event.type === 'sources') {
              sources = event.sources || [];
            }

            // ── done ──────────────────────────────────────────────────────
            if (event.type === 'done') {
              cursor.remove();
              _renderFinalMessage(bubbleEl, fullText, sources, assistantEl);
              _scrollToBottom();

              if (typeof lincolnCanvas !== 'undefined') {
                const blocks = lincolnCanvas.extractCodeBlocks(fullText);
                blocks.forEach(block => lincolnCanvas.pinCodeBlock({
                  language:    block.language,
                  filename:    _guessFilename(block.content, block.language),
                  content:     block.content,
                  projectName: _activeProject?.display_name || '',
                  sessionId:   _sessionId,
                }));
              }

              if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadHistory();
            }

            // ── error ─────────────────────────────────────────────────────
            if (event.type === 'error') {
              cursor.remove();
              bubbleEl.textContent = `Error: ${event.message}`;
              bubbleEl.style.color = 'var(--text-danger)';
            }

          } catch (_) { /* partial JSON — buffer fills on next iteration */ }
        }
      }

    } catch (err) {
      cursor.remove();
      bubbleEl.textContent = `Connection error: ${err.message}`;
      bubbleEl.style.color = 'var(--text-danger)';
    }

    _setStreaming(false);
  }


  // ── Web search / fetch commands ───────────────────────────────────────────

  async function _handleWebSearch(query, input) {
    input.value = '';
    _hideWelcome();
    _appendUserMessage(`search ${query}`);
    _setStreaming(true);
    await _ensureSession();

    const el       = _appendAssistantMessage('Searching…', []);
    const bubbleEl = el.querySelector('.message-bubble');
    try {
      await fetch('/api/chat/send', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          session_id: _sessionId,
          message:    `Search the web for: ${query}. Summarize what you find.`,
          model:      lincolnSettings?.activeModel || 'qwen3.5:9b',
          project_id: null,
          use_rag:    false,
        }),
      });
      bubbleEl.textContent = 'Search complete.';
    } catch (err) {
      bubbleEl.textContent = `Search error: ${err.message}`;
    }
    _setStreaming(false);
  }

  async function _handleFetch(url, input) {
    input.value = '';
    _hideWelcome();
    _appendUserMessage(`fetch ${url}`);
    _appendAssistantMessage(
      `Fetching ${url}… (use the terminal: lincoln_websearch fetch ${url})`, []
    );
  }


  // ── File attachment ───────────────────────────────────────────────────────

  function openFileAttach() {
    // Open file browser in file mode
    if (typeof lincolnSidebar !== 'undefined') {
      lincolnSidebar.openFileBrowser('file', async (selectedPath) => {
        await _uploadFileByPath(selectedPath);
      });
    } else {
      // Fallback: native file input
      const input = document.createElement('input');
      input.type   = 'file';
      input.accept = '.py,.f90,.f95,.f03,.f08,.js,.ts,.css,.html,.sql,.md,.txt,.csv,.json,.yaml,.yml,.toml,.ini,.cfg,.c,.cpp,.h,.hpp,.sh,.bat';
      input.onchange = async () => {
        if (input.files[0]) await _uploadFileBlob(input.files[0]);
      };
      input.click();
    }
  }

  async function _uploadFileByPath(filePath) {
    // Server-side: read file from path (file browser selected a local path)
    // We fetch the file content from /api/files/browse?path=... won't work for binary
    // Instead use a dedicated endpoint or fall back to native input
    // For now: open native input pre-seeded with the path hint
    const input = document.createElement('input');
    input.type  = 'file';
    input.onchange = async () => {
      if (input.files[0]) await _uploadFileBlob(input.files[0]);
    };
    input.click();
  }

  async function _uploadFileBlob(file) {
    const formData = new FormData();
    formData.append('file', file);
    if (_sessionId) formData.append('session_id', String(_sessionId));

    try {
      const res  = await fetch('/api/files/upload', { method: 'POST', body: formData });
      const data = await res.json();

      if (!res.ok || data.status !== 'ok') {
        alert(`Upload failed: ${data.message || 'Unknown error'}`);
        return;
      }

      _pendingFileId   = data.file_id;
      _pendingFileName = data.filename;
      _showPendingFile(data.filename, data.size_bytes);

    } catch (err) {
      alert(`Upload error: ${err.message}`);
    }
  }

  function _showPendingFile(name, sizeBytes) {
    let chip = document.getElementById('pendingFileChip');
    if (!chip) {
      chip = document.createElement('div');
      chip.id        = 'pendingFileChip';
      chip.className = 'pending-file-chip';
      const inputArea = document.querySelector('.input-box-bottom');
      if (inputArea) inputArea.prepend(chip);
    }
    const kb = Math.round(sizeBytes / 1024 * 10) / 10;
    chip.innerHTML = `
      <i class="ti ti-file-code"></i>
      <span>${_esc(name)}</span>
      <span style="color:var(--text-muted)">${kb} KB</span>
      <button onclick="lincolnChat.clearPendingFile()" title="Remove file">
        <i class="ti ti-x"></i>
      </button>
    `;
  }

  function clearPendingFile() {
    _clearPendingFile();
  }

  function _clearPendingFile() {
    _pendingFileId   = null;
    _pendingFileName = null;
    document.getElementById('pendingFileChip')?.remove();
  }


  // ── Context strip ─────────────────────────────────────────────────────────

  async function _loadContextStrip() {
    try {
      const res     = await fetch('/api/history/context');
      const entries = await res.json();
      if (!entries.length) return;

      const latest  = entries[0];
      const strip   = document.getElementById('contextStrip');
      const content = document.getElementById('contextStripContent');
      if (!strip || !content) return;

      content.innerHTML = `<strong>Last session</strong> — ${_esc(latest.content)}`;
      strip.style.display = 'flex';
    } catch (_) { /* no memory yet */ }
  }

  function dismissContextStrip() {
    const strip = document.getElementById('contextStrip');
    if (strip) strip.style.display = 'none';
  }

  async function saveMemory() {
    const content = prompt('Save a summary of this session to memory:\n(It will appear as context next time you open Lincoln)');
    if (!content?.trim()) return;
    try {
      const res = await fetch('/api/history/context', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          content:    content.trim(),
          project_id: _activeProjectId,
          tag:        'session_summary',
        }),
      });
      if (res.ok) {
        alert('✓ Session saved to memory. It will appear as context next time.');
      } else {
        alert('Failed to save memory.');
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  }


  // ── Markdown rendering ────────────────────────────────────────────────────
  // Uses marked.js (loaded via CDN) for full markdown support.
  // Falls back to plain text if marked is not available.

  function _md(text) {
    if (typeof marked !== 'undefined') {
      return marked.parse(text || '', { breaks: true, gfm: true });
    }
    // Fallback — basic inline formatting only
    return _esc(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }


  // ── Message rendering ─────────────────────────────────────────────────────

  function _appendUserMessage(text) {
    const container = document.getElementById('chatMessages');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'lincoln-message user-message';
    el.innerHTML = `
      <div class="message-avatar user-avatar">U</div>
      <div class="message-body">
        <div class="message-bubble user-bubble">${_esc(text)}</div>
      </div>
    `;
    container.appendChild(el);
    _scrollToBottom();
    return el;
  }

  function _appendAssistantMessage(text, sources) {
    const container = document.getElementById('chatMessages');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'lincoln-message';
    el.innerHTML = `
      <div class="message-avatar lincoln-avatar">L</div>
      <div class="message-body">
        <div class="message-bubble lincoln-bubble markdown-body">${text ? _md(text) : ''}</div>
        <div class="message-sources"></div>
      </div>
    `;
    container.appendChild(el);
    _scrollToBottom();
    if (sources?.length) _renderSources(el.querySelector('.message-sources'), sources);
    return el;
  }

  function _renderFinalMessage(bubbleEl, text, sources, messageEl) {
    // Apply full markdown rendering when streaming completes
    bubbleEl.innerHTML = _md(text);
    const sourcesEl = messageEl.querySelector('.message-sources');
    if (sourcesEl && sources?.length) _renderSources(sourcesEl, sources);
  }

  function _renderSources(container, sources) {
    if (!container || !sources?.length) return;
    container.innerHTML = sources.slice(0, 5).map(s => `
      <div class="source-chip">
        <i class="ti ti-file-code" style="font-size:10px"></i>
        ${_esc(s.file_name || s.file_path)}${s.score ? ' · ' + s.score : ''}
      </div>
    `).join('');
  }


  // ── Input helpers ─────────────────────────────────────────────────────────

  function handleInputKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

  function autoResizeTextarea(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }

  function insertCommand(text) {
    const input = document.getElementById('chatInput');
    if (!input) return;
    input.value = text;
    input.focus();
  }


  // ── Utilities ─────────────────────────────────────────────────────────────

  function _clearMessages() {
    const container = document.getElementById('chatMessages');
    if (!container) return;

    if (_activeProject) {
      // Claude-style project home screen
      container.innerHTML = `
        <div class="lincoln-project-home" id="projectHome">
          <div class="project-home-header">
            <div class="project-home-logo">L</div>
            <div class="project-home-title">${_escEl(_activeProject.display_name)}</div>
            <div class="project-home-subtitle">What are we working on today?</div>
          </div>
          <button class="project-home-new-chat" onclick="lincolnChat.startNewChat()">
            <i class="ti ti-plus" aria-hidden="true"></i>
            New chat
          </button>
          <div class="project-home-recents" id="projectHomeRecents">
            <div style="font-size:11px;color:var(--text-muted);padding:8px 0">Loading recent chats…</div>
          </div>
        </div>
      `;
      _loadProjectHomeRecents();
    } else {
      container.innerHTML = `
        <div class="lincoln-welcome" id="lincolnWelcome">
          <div class="welcome-logo">L</div>
          <div class="welcome-text">
            <div class="welcome-title">Lincoln is ready</div>
            <div class="welcome-subtitle">Select a project or start a general chat.</div>
          </div>
        </div>
      `;
    }
  }

  async function _loadProjectHomeRecents() {
    const recentsEl = document.getElementById('projectHomeRecents');
    if (!recentsEl || !_activeProjectId) return;
    try {
      const res      = await fetch('/api/history');
      const sessions = await res.json();
      const mine     = sessions.filter(s => s.project_id === _activeProjectId).slice(0, 8);
      if (!mine.length) {
        recentsEl.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">No chats yet — start one above.</div>';
        return;
      }
      recentsEl.innerHTML = mine.map(s => `
        <div class="project-home-chat-item" onclick="lincolnChat.loadSession(${s.id})">
          <i class="ti ti-message-circle" style="font-size:14px;color:var(--text-muted);flex-shrink:0"></i>
          <div class="project-home-chat-title">${_escEl(s.title)}</div>
          <div class="project-home-chat-date">${_fmtDate(s.updated_at)}</div>
        </div>
      `).join('');
    } catch (_) {
      recentsEl.innerHTML = '';
    }
  }

  function startNewChat() {
    // Hide home screen, show empty chat, create session on first send
    const home = document.getElementById('projectHome');
    if (home) home.remove();
    _sessionId = null;
  }

  function _fmtDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr), now = new Date();
    if (now - d < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function _escEl(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function _hideWelcome() {
    document.getElementById('lincolnWelcome')?.remove();
  }

  function _scrollToBottom() {
    const c = document.getElementById('chatMessages');
    if (c) c.scrollTop = c.scrollHeight;
  }

  function _setStreaming(active) {
    _isStreaming = active;
    const btn = document.getElementById('sendBtn');
    if (btn) btn.disabled = active;
  }

  function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function _guessFilename(content, language) {
    const firstLine = content.split('\n')[0];
    const match     = firstLine.match(/(?:filename|file):\s*(\S+)/i);
    if (match) return match[1];
    const ext = { python:'.py', fortran:'.f90', javascript:'.js', html:'.html', css:'.css', sql:'.sql', bash:'.sh' };
    return `code${ext[language] || '.txt'}`;
  }


  // ── Public screen-state methods (called by lincolnSidebar) ───────────────
  // These MUST stay in sync with what lincoln_sidebar.js calls on lincolnChat.

  function showWelcome() {
    // Called by sidebar when user selects "General" (no project)
    _sessionId = null;
    _clearMessages();   // renders lincolnWelcome screen
  }

  function showProjectHome(project) {
    // Called by sidebar when user selects a project
    _sessionId      = null;
    _activeProject  = project;
    _clearMessages();   // renders project home screen
  }


  // ── Public API ────────────────────────────────────────────────────────────

  return {
    init,
    newSession,
    startNewChat,
    loadSession,
    setActiveProject,
    sendMessage,
    handleInputKeydown,
    autoResizeTextarea,
    insertCommand,
    openFileAttach,
    clearPendingFile,
    dismissContextStrip,
    saveMemory,
    cycleThinkMode,
    showWelcome,
    showProjectHome,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnChat.init());
