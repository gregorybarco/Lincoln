/**
 * Lincoln Chat  v0.7.3  Navigator
 * ==================================
 * Changes from v0.7.0:
 *   - Globe pill always-on mode: web_search_always_on DB setting keeps
 *     the globe pill active permanently. syncAlwaysOnSearch() loads the
 *     setting on init and whenever settings change.
 *
 * Changes from v0.7.0 (prior):
 *   - Multi-file upload: _openNativePicker() now sets input.multiple = true.
 *   - _clearPendingFile() renamed to _clearPendingFiles() internally.
 *   - Topbar project badge now updates correctly on setActiveProject().
 */

const lincolnChat = (() => {

  let _sessionId         = null;
  let _activeProjectId   = null;
  let _activeProject     = null;
  let _isStreaming       = false;
  let _pendingFiles      = [];
  let _pendingFileId     = null;
  let _pendingFileName   = null;
  let _thinkDropdownOpen = false;
  let _webSearchActive   = false;   // per-message globe toggle
  let _webSearchAlwaysOn = false;   // persistent always-on mode

  const _THINK_MODES  = ['fast', 'normal', 'deep'];
  const _THINK_LABELS = {
    fast:   { label: '⚡ Fast',   title: 'Fast — no reasoning, immediate response' },
    normal: { label: '◎ Normal', title: 'Normal — balanced, no reasoning overhead' },
    deep:   { label: '🧠 Deep',  title: 'Deep — full chain-of-thought reasoning (slower)' },
  };
  let _thinkMode = 'normal';

  // ── Think mode ─────────────────────────────────────────────────────────────

  function toggleThinkDropdown() {
    const dropdown = document.getElementById('thinkDropdown');
    if (!dropdown) return;
    _thinkDropdownOpen = !_thinkDropdownOpen;
    dropdown.classList.toggle('open', _thinkDropdownOpen);
  }

  function closeThinkDropdown() {
    _thinkDropdownOpen = false;
    document.getElementById('thinkDropdown')?.classList.remove('open');
  }

  function setThinkMode(mode) {
    _thinkMode = mode;
    _updateThinkButton();
    closeThinkDropdown();
  }

  function _updateThinkButton() {
    const label = document.getElementById('thinkModeLabel');
    const pill  = document.getElementById('thinkModePill');
    if (!label || !pill) return;
    const meta    = _THINK_LABELS[_thinkMode];
    label.textContent = meta.label;
    pill.title        = meta.title;
    pill.classList.toggle('think-mode-deep', _thinkMode === 'deep');
    document.querySelectorAll('#thinkDropdown .model-dropdown-item').forEach(el => {
      el.classList.toggle('selected', el.dataset.mode === _thinkMode);
    });
  }

  // ── Web search toggle (per-message globe pill) ────────────────────────────

  function toggleWebSearch() {
    if (_webSearchAlwaysOn) return;
    _webSearchActive = !_webSearchActive;
    const btn = document.getElementById('webSearchPill');
    if (btn) {
      btn.classList.toggle('active', _webSearchActive);
      btn.title = _webSearchActive
        ? 'Web search ON — will inject search results for this message (click to disable)'
        : 'Web search OFF — click to enable for next message';
    }
  }

  function _resetWebSearchPill() {
    // If always-on mode is active, leave the pill ON after send
    if (_webSearchAlwaysOn) return;
    _webSearchActive = false;
    const btn = document.getElementById('webSearchPill');
    if (btn) {
      btn.classList.remove('active');
      btn.title = 'Click to enable web search for next message';
    }
  }

  // Called on init and by settings when the always-on toggle changes
  async function syncAlwaysOnSearch(forcedValue) {
    try {
      let alwaysOn;
      if (forcedValue !== undefined) {
        alwaysOn = forcedValue === true || forcedValue === 'true';
      } else {
        const res  = await fetch('/api/settings');
        const data = await res.json();
        alwaysOn = ((data.ui_settings?.web_search_always_on ?? data.web_search_always_on) === 'true');
      }
      _webSearchAlwaysOn = alwaysOn;
      if (_webSearchAlwaysOn) {
        _webSearchActive = true;
        const btn = document.getElementById('webSearchPill');
        if (btn) {
          btn.classList.add('active');
          btn.title = 'Web search always ON (toggle off in Settings → Web Search)';
        }
      } else {
        _webSearchActive = false;
        const btn = document.getElementById('webSearchPill');
        if (btn) {
          btn.classList.remove('active');
          btn.title = 'Click to enable web search for next message';
        }
      }
    } catch (e) {
      console.error('[Lincoln] syncAlwaysOnSearch failed:', e);
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  async function init() {
    await _loadContextStrip();
    _updateThinkButton();
    _setupGlobalEscape();
    await syncAlwaysOnSearch();
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
      if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadHistory();
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  }

  async function newSession() {
    _sessionId       = null;
    _activeProjectId = null;
    _activeProject   = null;
    _clearMessages();
    _clearPendingFile();
    if (typeof lincolnCanvas !== 'undefined') lincolnCanvas.clear();
    _hideCtxIndicator();
    const badge = document.getElementById('topbarProjectBadge');
    if (badge) badge.textContent = 'No project';
    if (typeof lincolnSidebar !== 'undefined') {
      document.querySelectorAll('.sidebar-project-item').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.project-dot').forEach(dot => dot.classList.remove('active'));
      lincolnSidebar.loadHistory();
    }
  }

  async function loadSession(sessionId) {
    try {
      const res      = await fetch(`/api/history/${sessionId}`);
      const messages = await res.json();
      _sessionId     = sessionId;

      const container = document.getElementById('chatMessages');
      if (container) container.innerHTML = '';

      _clearPendingFile();
      if (typeof lincolnCanvas !== 'undefined') lincolnCanvas.clear();

      let lastUserText = '';
      messages.forEach(msg => {
        if (msg.role === 'user') {
          lastUserText = msg.content;
          _appendUserMessage(msg.content);
        } else if (msg.role === 'assistant') {
          _appendAssistantMessage(msg.content, []);
          if (typeof lincolnCanvas !== 'undefined') {
            const blocks = lincolnCanvas.extractCodeBlocks(msg.content);
            blocks.forEach((block, i) => {
              const base     = _deriveFilename(lastUserText, block.language);
              const suffix   = blocks.length > 1 ? `_part${i + 1}` : '';
              const baseName = base.replace(/(\.[^.]+)$/, suffix + '$1');
              lincolnCanvas.pinCodeBlock({
                language:    block.language,
                filename:    lincolnCanvas.resolveFilename(baseName, sessionId),
                content:     block.content,
                projectName: _activeProject?.display_name || '',
                sessionId:   sessionId,
              });
            });
          }
        }
      });
    } catch (err) {
      console.error('Failed to load session:', err);
    }
    _updateCtxIndicator();
  }

  function setActiveProject(projectId, project) {
    _activeProjectId = projectId;
    _activeProject   = project;
    const badge = document.getElementById('topbarProjectBadge');
    if (badge) badge.textContent = project?.display_name || 'No project';
  }

  function clearActiveProject() {
    _activeProjectId = null;
    _activeProject   = null;
    const badge = document.getElementById('topbarProjectBadge');
    if (badge) badge.textContent = 'No project';
  }

  // ── Send message ──────────────────────────────────────────────────────────

  async function sendMessage() {
    const input = document.getElementById('chatInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text || _isStreaming) return;

    await _ensureSession();

    const useWebSearch = _webSearchActive;
    _resetWebSearchPill();

    input.value = '';
    autoResizeTextarea(input);
    _hideWelcome();

    let displayText = text;
    let fileIds     = [];
    if (_pendingFiles.length === 1) {
      displayText = `📎 ${_pendingFiles[0].name}\n\n${text}`;
      fileIds     = [_pendingFiles[0].id];
    } else if (_pendingFiles.length > 1) {
      const names  = _pendingFiles.map(f => f.name).join(', ');
      displayText  = `📎 ${_pendingFiles.length} files: ${names}\n\n${text}`;
      fileIds      = _pendingFiles.map(f => f.id);
    }
    _appendUserMessage(displayText);

    _clearPendingFiles();
    _setStreaming(true);

    const assistantEl = _appendAssistantMessage('', []);
    const bubbleEl    = assistantEl.querySelector('.message-bubble');
    const cursor      = document.createElement('span');
    cursor.className  = 'streaming-cursor';
    bubbleEl.appendChild(cursor);

    let thinkEl      = null;
    let thinkBodyEl  = null;
    let inThinkBlock = false;
    let thinkText    = '';
    let fullText     = '';
    let sources      = [];

    function _ensureThinkBlock() {
      if (thinkEl) return;
      thinkEl = document.createElement('details');
      thinkEl.className = 'think-block';
      thinkEl.innerHTML =
        '<summary class="think-summary">Reasoning <span class="think-spinner"></span></summary>';
      thinkBodyEl = document.createElement('div');
      thinkBodyEl.className = 'think-body';
      thinkEl.appendChild(thinkBodyEl);
      bubbleEl.parentNode.insertBefore(thinkEl, bubbleEl);
    }

    try {
      const response = await fetch('/api/chat/send', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          session_id:     _sessionId,
          message:        text,
          model:          lincolnSettings?.activeModel || 'qwen3.5:9b',
          project_id:     _activeProjectId,
          use_rag:        !!_activeProjectId,
          use_web_search: useWebSearch,
          file_ids:       fileIds.length ? fileIds : null,
          file_id:        fileIds.length === 1 ? fileIds[0] : null,
          think_mode:     _thinkMode,
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

            if (event.type === 'token') {
              const content = event.content;
              if (content === 'THINK_START') {
                inThinkBlock = true;
                _ensureThinkBlock();
              } else if (content === 'THINK_END') {
                inThinkBlock = false;
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
                fullText += content;
                bubbleEl.innerHTML = (typeof marked !== 'undefined')
                  ? marked.parse(fullText)
                  : fullText.replace(/\n/g, '<br>');
                bubbleEl.appendChild(cursor);
                _scrollToBottom();
              }
            }
            if (event.type === 'sources') {
              sources = event.sources || [];
            }

            if (event.type === 'ctx_update') {
              _applyCtxUpdate(event);
            }

            if (event.type === 'web_search') {
              // Show transient indicator that web results were injected
              _showWebSearchIndicator(assistantEl, event.result_count || 0);
            }

            if (event.type === 'ban_check' && event.violations?.length) {
              _showBanCheckWarning(assistantEl, event.violations);
            }

            if (event.type === 'approval_required') {
              cursor.remove();
              _showApprovalCard(assistantEl, event);
            }

            if (event.type === 'tool_executing') {
              _showToolExecutingIndicator(assistantEl, event.tool_name);
            }

            if (event.type === 'done') {
              cursor.remove();
              _renderFinalMessage(bubbleEl, fullText, sources, assistantEl);
              _scrollToBottom();
              _updateCtxIndicator();

              if (typeof lincolnCanvas !== 'undefined') {
                const blocks = lincolnCanvas.extractCodeBlocks(fullText);
                blocks.forEach((block, i) => {
                  const base     = _deriveFilename(text, block.language);
                  const suffix   = blocks.length > 1 ? `_part${i + 1}` : '';
                  const baseName = base.replace(/(\.[^.]+)$/, suffix + '$1');
                  lincolnCanvas.pinCodeBlock({
                    language:    block.language,
                    filename:    lincolnCanvas.resolveFilename(baseName, _sessionId),
                    content:     block.content,
                    projectName: _activeProject?.display_name || '',
                    sessionId:   _sessionId,
                  });
                });
              }
              if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadHistory();
            }

            if (event.type === 'error') {
              cursor.remove();
              bubbleEl.textContent = `Error: ${event.message}`;
              bubbleEl.style.color = 'var(--text-danger)';
            }
          } catch (_) { /* malformed SSE line, skip */ }
        }
      }
    } catch (err) {
      cursor.remove();
      bubbleEl.textContent = `Connection error: ${err.message}`;
      bubbleEl.style.color = 'var(--text-danger)';
    }

    _setStreaming(false);
  }

  // ── Tool approval card ────────────────────────────────────────────────────

  function _showApprovalCard(messageEl, event) {
    const body = messageEl.querySelector('.message-body');
    if (!body) return;

    const argsStr = JSON.stringify(event.arguments || {}, null, 2);
    const card = document.createElement('div');
    card.className = 'tool-approval-card';
    card.dataset.toolCallId = event.tool_call_id;
    card.innerHTML = `
      <div class="tool-approval-header">
        <i class="ti ti-tool"></i>
        <strong>${_esc(event.tool_name)}</strong>
        <span class="tool-approval-badge">Approval required</span>
      </div>
      <pre class="tool-approval-args"><code>${_esc(argsStr)}</code></pre>
      <div class="tool-approval-actions">
        <button class="btn-approve" onclick="lincolnChat._approveToolCall('${_esc(event.tool_call_id)}', '${_esc(event.session_id)}')">
          <i class="ti ti-check"></i> Approve
        </button>
        <button class="btn-deny" onclick="lincolnChat._denyToolCall('${_esc(event.tool_call_id)}', '${_esc(event.session_id)}', this.closest('.tool-approval-card'))">
          <i class="ti ti-x"></i> Deny
        </button>
      </div>
    `;
    body.appendChild(card);
    _scrollToBottom();
  }

  async function _approveToolCall(toolCallId, sessionId) {
    const card = document.querySelector(`.tool-approval-card[data-tool-call-id="${toolCallId}"]`);
    if (card) {
      card.classList.add('approved');
      card.querySelector('.tool-approval-actions').innerHTML =
        '<span class="tool-status-approved"><i class="ti ti-check"></i> Approved — executing…</span>';
    }

    const container   = document.getElementById('chatMessages');
    const assistantEl = container?.lastElementChild;
    const bubbleEl    = assistantEl?.querySelector('.message-bubble');
    const cursor      = document.createElement('span');
    cursor.className  = 'streaming-cursor';
    if (bubbleEl) bubbleEl.appendChild(cursor);

    let fullText = '';
    let sources  = [];

    try {
      const response = await fetch('/api/chat/resolve_tool', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          tool_call_id: toolCallId,
          session_id:   sessionId,
          approved:     true,
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

            if (event.type === 'token' && bubbleEl) {
              fullText += event.content;
              bubbleEl.innerHTML = (typeof marked !== 'undefined')
                ? marked.parse(fullText)
                : fullText.replace(/\n/g, '<br>');
              bubbleEl.appendChild(cursor);
              _scrollToBottom();
            }

            if (event.type === 'tool_approval_required') {
              cursor.remove();
              _showApprovalCard(assistantEl, event);
            }

            if (event.type === 'tool_executing') {
              _showToolExecutingIndicator(assistantEl, event.tool_name);
            }

            if (event.type === 'sources') {
              sources = event.sources || [];
            }

            if (event.type === 'done') {
              cursor.remove();
              if (bubbleEl) _renderFinalMessage(bubbleEl, fullText, sources, assistantEl);
              _scrollToBottom();

              if (typeof lincolnCanvas !== 'undefined' && fullText) {
                const blocks = lincolnCanvas.extractCodeBlocks(fullText);
                const text   = document.getElementById('chatInput')?.value || '';
                blocks.forEach((block, i) => {
                  const base     = _deriveFilename(text, block.language);
                  const suffix   = blocks.length > 1 ? `_part${i + 1}` : '';
                  const baseName = base.replace(/(\.[^.]+)$/, suffix + '$1');
                  lincolnCanvas.pinCodeBlock({
                    language:    block.language,
                    filename:    lincolnCanvas.resolveFilename(baseName, _sessionId),
                    content:     block.content,
                    projectName: _activeProject?.display_name || '',
                    sessionId:   _sessionId,
                  });
                });
              }
              if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadHistory();
            }

            if (event.type === 'error') {
              cursor.remove();
              if (bubbleEl) {
                bubbleEl.textContent = `Error: ${event.message}`;
                bubbleEl.style.color = 'var(--text-danger)';
              }
            }
          } catch (_) { /* malformed SSE line */ }
        }
      }
    } catch (err) {
      cursor.remove();
      if (bubbleEl) {
        bubbleEl.textContent = `Connection error: ${err.message}`;
        bubbleEl.style.color = 'var(--text-danger)';
      }
    }

    _setStreaming(false);
  }

  async function _denyToolCall(toolCallId, sessionId, cardEl) {
    if (cardEl) {
      cardEl.classList.add('denied');
      cardEl.querySelector('.tool-approval-actions').innerHTML =
        '<span class="tool-status-denied"><i class="ti ti-x"></i> Denied</span>';
    }

    try {
      await fetch('/api/chat/resolve_tool', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          tool_call_id: toolCallId,
          session_id:   sessionId,
          approved:     false,
        }),
      });
    } catch (err) {
      console.error('[Lincoln] deny tool call error:', err);
    }
    _setStreaming(false);
  }

  function _showToolExecutingIndicator(messageEl, toolName) {
    const body = messageEl?.querySelector('.message-body');
    if (!body) return;
    const existing = body.querySelector('.tool-executing-indicator');
    if (existing) existing.remove();
    const el = document.createElement('div');
    el.className = 'tool-executing-indicator';
    el.innerHTML = `<span class="tool-spinner"></span> Running <strong>${_esc(toolName)}</strong>…`;
    body.appendChild(el);
    _scrollToBottom();
    setTimeout(() => el.remove(), 8000);
  }

  // ── Web search indicator ──────────────────────────────────────────────────

function _applyCtxUpdate(data) {
    const indicator = document.getElementById('ctxIndicator');
    const tokUsed   = document.getElementById('ctxTokensUsed');
    const ceiling   = document.getElementById('ctxCeiling');
    const pct       = document.getElementById('ctxPercent');
    const bar       = document.getElementById('ctxBar');
    if (!indicator) return;

    if (tokUsed) tokUsed.textContent = (data.tokens_used || 0).toLocaleString();
    if (ceiling) ceiling.textContent = (data.ceiling || 0).toLocaleString();

    const p = data.percent || 0;
    if (pct) {
      pct.textContent = p.toFixed(1) + '%';
      pct.className   = 'ctx-percent' + (p >= 90 ? ' ctx-danger' : p >= 75 ? ' ctx-warn' : '');
    }
    if (bar) {
      bar.style.width = Math.min(p, 100) + '%';
      bar.className   = 'ctx-bar' + (p >= 90 ? ' ctx-bar-danger' : p >= 75 ? ' ctx-bar-warn' : '');
    }
    indicator.style.display  = 'flex';
    indicator.style.background = '#e8e7e3';
    indicator.style.border     = '0.5px solid rgba(0,0,0,0.14)';
  }

  function _showWebSearchIndicator(messageEl, resultCount) {
    const body = messageEl.querySelector('.message-body');
    if (!body) return;
    const chip = document.createElement('div');
    chip.className   = 'web-search-indicator';
    chip.textContent = `🌐 ${resultCount} web result${resultCount !== 1 ? 's' : ''} used`;
    body.prepend(chip);
  }

  // ── Ban list warning ──────────────────────────────────────────────────────

  function _showBanCheckWarning(messageEl, violations) {
    const body = messageEl.querySelector('.message-body');
    if (!body) return;
    const banner = document.createElement('div');
    banner.className = 'ban-check-banner';
    banner.innerHTML = `
      <div class="ban-check-header">
        <i class="ti ti-alert-triangle"></i>
        <strong>OptionsPricing Ban List — ${violations.length} violation${violations.length !== 1 ? 's' : ''} detected</strong>
        <button class="ban-check-dismiss" onclick="this.closest('.ban-check-banner').remove()">
          <i class="ti ti-x"></i>
        </button>
      </div>
      <ul class="ban-check-list">
        ${violations.map(v => `
          <li>
            <span class="ban-pattern-name">${_esc(v.pattern_name)}</span>
            <span class="ban-line">Line ${v.line_number}</span>
            <div class="ban-reason">${_esc(v.reason)}</div>
          </li>
        `).join('')}
      </ul>
    `;
    body.appendChild(banner);
  }

  // ── File upload ───────────────────────────────────────────────────────────

  function openFileAttach() {
    if (typeof lincolnSidebar !== 'undefined' && lincolnSidebar.openFileBrowser) {
      lincolnSidebar.openFileBrowser('file', async (fileOrPath) => {
        if (fileOrPath instanceof File) {
          await _uploadFileBlob(fileOrPath);
        } else {
          _openNativePicker();
        }
      });
    } else {
      _openNativePicker();
    }
  }

  function _openNativePicker() {
    const input    = document.createElement('input');
    input.type     = 'file';
    input.multiple = true;
    input.accept   = _buildAcceptString();
    input.onchange = async () => {
      if (!input.files || !input.files.length) return;
      for (const file of Array.from(input.files)) {
        await _uploadFileBlob(file);
      }
    };
    input.click();
  }

  function _buildAcceptString() {
    return [
      '.py', '.f90', '.f95', '.f03', '.f08', '.f', '.for',
      '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.scss',
      '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs',
      '.sql', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini',
      '.sh', '.bat', '.ps1',
      '.jl', '.m', '.nb', '.wl', '.r', '.Rmd',
      '.sas', '.do', '.ado', '.gms', '.ampl', '.lp', '.mps',
      '.mw', '.mpl', '.maple',
      '.tex', '.latex', '.bib',
      '.csv', '.ipynb',
      '.pdf', '.docx', '.xlsx',
      '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp',
    ].join(',');
  }

  async function _uploadFileBlob(file) {
    const formData = new FormData();
    formData.append('file', file);
    if (_sessionId) formData.append('session_id', String(_sessionId));

    const ext     = '.' + file.name.split('.').pop().toLowerCase();
    const isImage = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp'].includes(ext);

    let uploadUrl = '/api/files/upload';
    if (isImage) uploadUrl += '?mode=ocr&lang=eng';

    try {
      const res  = await fetch(uploadUrl, { method: 'POST', body: formData });
      const data = await res.json();

      if (!res.ok || data.error) {
        _showToast(data.error || `Upload failed: ${file.name}`, 'error');
        return;
      }

      _pendingFiles.push({
        id:      data.file_id,
        name:    data.filename,
        size:    data.size,
        isImage: isImage,
      });
      _pendingFileId   = _pendingFiles[_pendingFiles.length - 1].id;
      _pendingFileName = _pendingFiles[_pendingFiles.length - 1].name;
      _updatePendingChip();

    } catch (err) {
      _showToast(`Upload error: ${err.message}`, 'error');
    }
  }

  function _updatePendingChip() {
    let chip = document.getElementById('pendingFileChip');
    if (!chip) {
      chip = document.createElement('div');
      chip.id        = 'pendingFileChip';
      chip.className = 'pending-file-chip';
      const inputArea = document.querySelector('.input-box-bottom');
      if (inputArea) inputArea.prepend(chip);
    }

    if (_pendingFiles.length === 0) { chip.remove(); return; }

    if (_pendingFiles.length === 1) {
      const f  = _pendingFiles[0];
      const kb = Math.round((f.size || 0) / 1024 * 10) / 10;
      chip.innerHTML = `
        <i class="ti ti-${f.isImage ? 'photo' : 'file-code'}"></i>
        <span>${_esc(f.name)}</span>
        <span style="color:var(--text-muted)">${kb} KB</span>
        ${f.isImage ? `<button class="chip-action" onclick="lincolnChat._switchImageMode()" title="Switch OCR/Vision mode">
          <i class="ti ti-eye"></i>
        </button>` : ''}
        <button onclick="lincolnChat.clearPendingFile()" title="Remove file">
          <i class="ti ti-x"></i>
        </button>
      `;
    } else {
      const totalKb = Math.round(_pendingFiles.reduce((s, f) => s + (f.size || 0), 0) / 1024 * 10) / 10;
      const names   = _pendingFiles.map(f => _esc(f.name)).join(', ');
      chip.innerHTML = `
        <i class="ti ti-files"></i>
        <span title="${names}">${_pendingFiles.length} files attached</span>
        <span style="color:var(--text-muted)">${totalKb} KB total</span>
        <button onclick="lincolnChat.clearPendingFile()" title="Remove all files">
          <i class="ti ti-x"></i>
        </button>
      `;
    }
  }

  function _switchImageMode() {
    _showToast('Vision mode: re-attach the image and use ?mode=vision in the URL field', 'info');
  }

  function clearPendingFile() { _clearPendingFiles(); }

  function _clearPendingFiles() {
    _pendingFiles    = [];
    _pendingFileId   = null;
    _pendingFileName = null;
    document.getElementById('pendingFileChip')?.remove();
  }

  function _clearPendingFile() { _clearPendingFiles(); }

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
    } catch (_) { }
  }

  function dismissContextStrip() {
    document.getElementById('contextStrip')?.style.setProperty('display', 'none');
  }

  // ── Save memory ───────────────────────────────────────────────────────────

  async function saveMemory() { _openMemoryModal(); }

  function _openMemoryModal() {
    let modal = document.getElementById('memoryInputModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id        = 'memoryInputModal';
      modal.className = 'modal-overlay';
      modal.innerHTML = `
        <div class="modal-box">
          <div class="modal-header">
            <h3>Save session to memory</h3>
            <button onclick="document.getElementById('memoryInputModal').remove()">
              <i class="ti ti-x"></i>
            </button>
          </div>
          <p class="modal-hint">Keep it concise — what are the key facts to carry forward?</p>
          <textarea id="memoryModalText" class="modal-textarea"
            placeholder="e.g. BASIN-RERUN-M1 blocked until Aug. rfree2=0.011."
            rows="5"></textarea>
          <div class="modal-actions">
            <button class="btn-secondary" onclick="document.getElementById('memoryInputModal').remove()">Cancel</button>
            <button class="btn-primary" onclick="lincolnChat._submitMemory()">Save to memory</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    document.getElementById('memoryModalText')?.focus();
  }

  async function _submitMemory() {
    const text = document.getElementById('memoryModalText')?.value.trim();
    if (!text) return;
    try {
      const res = await fetch('/api/history/context', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ content: text, project_id: _activeProjectId, tag: 'session_summary' }),
      });
      if (res.ok) {
        document.getElementById('memoryInputModal')?.remove();
        _showToast('Session saved to memory', 'success');
        if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadMemory?.();
      } else {
        _showToast('Failed to save memory', 'error');
      }
    } catch (err) {
      _showToast(`Error: ${err.message}`, 'error');
    }
  }

  // ── Markdown + syntax highlighting ────────────────────────────────────────

  (function _initMarked() {
    if (typeof marked === 'undefined' || typeof hljs === 'undefined') return;
    const renderer = new marked.Renderer();
    renderer.code  = function (token) {
      // marked v9+: single token object {type, raw, lang, text, escaped}
      const rawCode = (typeof token === 'object' && token !== null) ? (token.text || token.raw || '') : token;
      const rawLang = (typeof token === 'object' && token !== null) ? (token.lang || '') : (arguments[1] || '');
      const language = rawLang || '';
      let escaped;
      try {
        escaped = language && hljs.getLanguage(language)
          ? hljs.highlight(rawCode, { language }).value
          : hljs.highlightAuto(rawCode).value;
      } catch (_) {
        escaped = _esc(rawCode);
      }
      const cls = language ? ` class="language-${language} hljs"` : ' class="hljs"';
      return `<pre><code${cls}>${escaped}</code></pre>`;
    };
    marked.use({ renderer, breaks: true, gfm: true });
  })();

  function _md(text) {
    if (typeof marked !== 'undefined') return marked.parse(text || '');
    return _esc(text).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
  }

  function _applyFormatting(element) {
    if (!element) return;
    if (typeof hljs !== 'undefined') {
      element.querySelectorAll('pre code:not(.hljs)').forEach(block => hljs.highlightElement(block));
    }
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(element, {
        delimiters: [
          { left: '$$',  right: '$$',   display: true  },
          { left: '\\[', right: '\\]', display: true  },
          { left: '\\(', right: '\\)', display: false },
        ],
        throwOnError:   false,
        output:         'html',
        ignoredTags:    ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
        ignoredClasses: ['hljs', 'language-python', 'language-fortran', 'language-r',
                         'language-matlab', 'language-julia', 'language-maple'],
      });
    }
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
        <div class="message-bubble user-bubble" dir="auto">${_esc(text)}</div>
      </div>
    `;
    container.appendChild(el);
    _applyFormatting(el.querySelector('.message-bubble'));
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
        <div class="message-bubble lincoln-bubble markdown-body" dir="auto">${text ? _md(text) : ''}</div>
        <div class="message-sources"></div>
      </div>
    `;
    container.appendChild(el);
    _applyFormatting(el.querySelector('.message-bubble'));
    _scrollToBottom();
    if (sources?.length) _renderSources(el.querySelector('.message-sources'), sources);
    return el;
  }

  function _renderFinalMessage(bubbleEl, text, sources, messageEl) {
    bubbleEl.innerHTML = _md(text);
    bubbleEl.setAttribute('dir', 'auto');
    _applyFormatting(bubbleEl);
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

  // ── Project home ──────────────────────────────────────────────────────────

  function _clearMessages() {
    const container = document.getElementById('chatMessages');
    if (!container) return;

    if (_activeProject) {
      container.innerHTML = `
        <div class="lincoln-project-home" id="projectHome">
          <div class="project-home-header">
            <div class="project-home-logo">L</div>
            <div class="project-home-title">${_escEl(_activeProject.display_name)}</div>
            <div class="project-home-subtitle">What are we working on today?</div>
          </div>
          <button class="project-home-new-chat" onclick="lincolnChat.startNewChat()">
            <i class="ti ti-plus" aria-hidden="true"></i> New chat
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
      const res      = await fetch(`/api/history?project_id=${_activeProjectId}`);
      const sessions = await res.json();
      const mine     = sessions.slice(0, 8);
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
    } catch (_) { recentsEl.innerHTML = ''; }
  }

  function startNewChat() {
    const home = document.getElementById('projectHome');
    if (home) home.remove();
    _sessionId = null;
    _hideCtxIndicator();
  }

  // ── Global Escape handler ─────────────────────────────────────────────────

  function _setupGlobalEscape() {
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const input = document.getElementById('chatInput');
      if (document.activeElement === input) { input.blur(); return; }
      const modal = document.querySelector('.modal-overlay[style*="flex"]');
      if (modal) { modal.style.display = 'none'; return; }
      const overlay = document.querySelector('.overlay[style*="flex"]');
      if (overlay) { overlay.style.display = 'none'; return; }
      if (_thinkDropdownOpen) { closeThinkDropdown(); return; }
      if (typeof lincolnCanvas !== 'undefined' && lincolnCanvas.hasSelection?.()) { lincolnCanvas.clearSelection(); return; }
      if (typeof lincolnSidebar !== 'undefined' && lincolnSidebar.hasSelection?.()) { lincolnSidebar.clearSelection(); return; }
    });
  }

  // ── Toast notifications ───────────────────────────────────────────────────

  function _showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.classList.add('toast-visible'), 10);
    setTimeout(() => { toast.classList.remove('toast-visible'); setTimeout(() => toast.remove(), 300); }, 3500);
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

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

  function _hideWelcome() { document.getElementById('lincolnWelcome')?.remove(); }
  function _scrollToBottom() { const c = document.getElementById('chatMessages'); if (c) c.scrollTop = c.scrollHeight; }
  function _setStreaming(active) { _isStreaming = active; const btn = document.getElementById('sendBtn'); if (btn) btn.disabled = active; }
  function _esc(str) { const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }
  function _escEl(str) { const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML; }
  function _fmtDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr), now = new Date();
    if (now - d < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  const _LANG_EXT = {
    python: '.py', fortran: '.f90', javascript: '.js', typescript: '.ts',
    html: '.html', css: '.css', sql: '.sql', bash: '.sh', sh: '.sh',
    json: '.json', markdown: '.md', r: '.r', cpp: '.cpp', c: '.c',
    java: '.java', rust: '.rs', go: '.go', ruby: '.rb', text: '.txt',
    julia: '.jl', matlab: '.m', mathematica: '.nb', wolfram: '.wl',
    rmarkdown: '.Rmd', sas: '.sas', stata: '.do', gams: '.gms',
    ampl: '.ampl', lp: '.lp', maple: '.mpl', latex: '.tex',
    bibtex: '.bib', powershell: '.ps1', batch: '.bat',
  };

  function _deriveFilename(userText, language) {
    const ext = _LANG_EXT[language] || '.txt';
    const lincolnMatch = userText.match(/\b(lincoln_[A-Za-z0-9_]+(?:\.[A-Za-z0-9]+)?)\b/i);
    if (lincolnMatch) {
      const name = lincolnMatch[1];
      return name.includes('.') ? name : name + ext;
    }
    const FILLER = /\b(the|a|an|please|can|you|write|make|create|build|give|me|i|want|need|fix|update|rewrite|add|new|version|of|for|with|that|this|and|or|in|to|my|code|file|script|function|class|module|using|show|get|set|just|also|now|here|it|its|is|are|was|were|be|been|being)\b/gi;
    const slug = userText.replace(FILLER, ' ').replace(/[^A-Za-z0-9\s]/g, ' ').trim()
      .split(/\s+/).filter(w => w.length > 1).slice(0, 5).join('_').toLowerCase() || 'code';
    return slug + ext;
  }

  function showWelcome() { _sessionId = null; _clearMessages(); _hideCtxIndicator(); }
  function showProjectHome(project) { _sessionId = null; _activeProject = project; _clearMessages(); _hideCtxIndicator(); }

  document.addEventListener('click', (e) => {
    const pill = document.getElementById('thinkModePill');
    const dd   = document.getElementById('thinkDropdown');
    if (pill && dd && !pill.contains(e.target) && !dd.contains(e.target)) closeThinkDropdown();
  });

  async function _updateCtxIndicator() {
    if (!_sessionId) return;
    const model = (typeof lincolnSettings !== 'undefined' && lincolnSettings.activeModel)
                  ? lincolnSettings.activeModel
                  : '';
    try {
      const params = new URLSearchParams({ session_id: _sessionId });
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
      indicator.style.background = '#e8e7e3';
      indicator.style.border = '0.5px solid rgba(0,0,0,0.14)';
    } catch (_) { /* silently ignore — indicator is non-critical */ }
  }
 
  function _hideCtxIndicator() {
    const el = document.getElementById('ctxIndicator');
    if (el) el.style.display = 'none';
  }

  return {
    init,
    newSession,
    startNewChat,
    loadSession,
    setActiveProject,
    clearActiveProject,
    sendMessage,
    handleInputKeydown,
    autoResizeTextarea,
    insertCommand,
    openFileAttach,
    clearPendingFile,
    dismissContextStrip,
    saveMemory,
    _submitMemory,
    _switchImageMode,
    toggleThinkDropdown,
    closeThinkDropdown,
    setThinkMode,
    toggleWebSearch,
    syncAlwaysOnSearch,
    showWelcome,
    showProjectHome,
    showToast: _showToast,
    _approveToolCall,
    _denyToolCall,
    showCtxIndicator: _updateCtxIndicator,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnChat.init());
