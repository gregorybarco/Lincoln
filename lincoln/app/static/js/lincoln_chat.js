/**
 * Lincoln Chat  v0.7.0  Navigator
 * ==================================
 * Changes from v0.6.0:
 *   - Multi-file upload: _openNativePicker() now sets input.multiple = true.
 *     Each file is uploaded in sequence; all pending files are tracked in
 *     _pendingFiles[] (array). The pending chip shows a count badge when
 *     multiple files are attached ("3 files attached"). All file IDs are
 *     sent in the payload as file_ids[] array (backend updated to match).
 *   - _clearPendingFile() renamed to _clearPendingFiles() internally;
 *     public clearPendingFile() still works for backwards compat.
 *   - Topbar project badge now updates correctly on setActiveProject().
 *
 * ReAct patch (v0.7.0):
 *   - approval_required SSE event: pauses stream, shows approval card
 *   - tool_executing SSE event: shows spinner indicator per tool
 *   - tool_result SSE event: marks tool indicator as complete
 *   - search_query SSE event: shows toast with exact query string
 *   - _resolveApproval(): POSTs to /api/chat/resolve_tool, resumes stream
 *   - _showApprovalCard(): renders Approve/Deny UI inline in chat
 */

const lincolnChat = (() => {

  let _sessionId         = null;
  let _activeProjectId   = null;
  let _activeProject     = null;
  let _isStreaming       = false;
  // v0.7.0: multi-file — track array of {id, name, size, isImage}
  let _pendingFiles      = [];
  // Kept for backward compat (older code may read these)
  let _pendingFileId     = null;
  let _pendingFileName   = null;
  let _thinkDropdownOpen = false;
  let _webSearchActive   = false;   // per-message globe toggle

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
    _webSearchActive = false;
    const btn = document.getElementById('webSearchPill');
    if (btn) {
      btn.classList.remove('active');
      btn.title = 'Click to enable web search for next message';
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  async function init() {
    await _loadContextStrip();
    _updateThinkButton();
    _setupGlobalEscape();
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
    // Reset topbar badge
    const badge = document.getElementById('topbarProjectBadge');
    if (badge) badge.textContent = 'No project';
    // Deselect project in sidebar
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
  }

  function setActiveProject(projectId, project) {
    _activeProjectId = projectId;
    _activeProject   = project;
    // Update topbar badge
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

    // Capture and reset per-message state before clearing input
    const useWebSearch = _webSearchActive;
    _resetWebSearchPill();

    input.value = '';
    autoResizeTextarea(input);
    _hideWelcome();

    // Multi-file: build display text and capture file IDs before clearing
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
                bubbleEl.textContent = fullText;
                bubbleEl.appendChild(cursor);
                _scrollToBottom();
              }
            }

            if (event.type === 'sources') {
              sources = event.sources || [];
            }

            if (event.type === 'web_search') {
              _showWebSearchIndicator(assistantEl, event.result_count || 0);
            }

            // ── ReAct tool events ─────────────────────────────────────────

            if (event.type === 'tool_executing') {
              _showToolExecutingIndicator(assistantEl, event.tool_name, event.arguments);
            }

            if (event.type === 'tool_result') {
              _updateToolExecutingIndicator(assistantEl, event.tool_name, event.result_preview);
            }

            if (event.type === 'search_query') {
              _showToast(`🔍 Searching: "${event.query}"`, 'info');
            }

            if (event.type === 'approval_required') {
              cursor.remove();
              _setStreaming(false);
              _showApprovalCard(
                assistantEl, event, _sessionId,
                lincolnSettings?.activeModel || 'qwen3.5:9b',
                _activeProjectId, _thinkMode
              );
              return;
            }

            // ── End ReAct tool events ─────────────────────────────────────

            if (event.type === 'ban_check' && event.violations?.length) {
              _showBanCheckWarning(assistantEl, event.violations);
            }

            if (event.type === 'done') {
              cursor.remove();
              _renderFinalMessage(bubbleEl, fullText, sources, assistantEl);
              _scrollToBottom();

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

  // ── Web search indicator ──────────────────────────────────────────────────

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

  // ── ReAct: Tool executing indicator ──────────────────────────────────────

  function _showToolExecutingIndicator(messageEl, toolName, args) {
    const body = messageEl.querySelector('.message-body');
    if (!body) return;

    body.querySelector('.tool-executing-indicator')?.remove();

    const icons = {
      rag_query:       'ti-database-search',
      read_file:       'ti-file-code',
      web_search:      'ti-world-search',
      execute_python:  'ti-brand-python',
      execute_fortran: 'ti-cpu',
      write_file:      'ti-file-pencil',
      run_aider:       'ti-terminal-2',
    };

    const el = document.createElement('div');
    el.className    = 'tool-executing-indicator';
    el.dataset.tool = toolName;
    el.innerHTML    = `
      <div class="tool-indicator-inner">
        <i class="ti ${icons[toolName] || 'ti-tool'} tool-indicator-icon"></i>
        <span class="tool-indicator-name">${_esc(toolName.replace(/_/g, ' '))}</span>
        <span class="tool-indicator-spinner"></span>
      </div>
    `;
    body.insertBefore(el, body.querySelector('.message-bubble'));
  }

  function _updateToolExecutingIndicator(messageEl, toolName, resultPreview) {
    const el = messageEl.querySelector(`.tool-executing-indicator[data-tool="${toolName}"]`);
    if (!el) return;
    el.querySelector('.tool-indicator-spinner')?.remove();
    el.querySelector('.tool-indicator-inner')?.insertAdjacentHTML(
      'beforeend',
      `<i class="ti ti-check tool-indicator-done"></i>`
    );
    setTimeout(() => el.classList.add('tool-indicator-collapsed'), 2000);
  }

  // ── ReAct: Approval card ──────────────────────────────────────────────────

  function _showApprovalCard(messageEl, event, sessionId, model, projectId, thinkMode) {
    const body = messageEl.querySelector('.message-body');
    if (!body) return;

    const toolName = event.tool_name;
    const args     = event.arguments;
    const tier     = event.tier || 'write';
    const reason   = event.reason || 'This action requires your approval.';

    let argsDisplay = JSON.stringify(args, null, 2);
    if (argsDisplay.length > 800) argsDisplay = argsDisplay.slice(0, 800) + '\n... (truncated)';

    const headerContent = toolName === 'web_search'
      ? `<div class="approval-search-query">
           <i class="ti ti-world-search"></i>
           <span>${_esc(args.query || '')}</span>
         </div>`
      : `<pre class="approval-args-pre">${_esc(argsDisplay)}</pre>`;

    const tierLabel = tier === 'search' ? '🔍 Web Search Request' : '⚠️ Action Required';
    const tierClass = tier === 'search' ? 'approval-card-search' : 'approval-card-write';

    const safeModel    = _esc(model || 'qwen3.5:9b');
    const safeThink    = _esc(thinkMode || 'normal');
    const safeProject  = projectId != null ? projectId : 'null';

    const card = document.createElement('div');
    card.className = `approval-card ${tierClass}`;
    card.innerHTML = `
      <div class="approval-card-header">
        <strong>${tierLabel}</strong>
        <span class="approval-tool-name">${_esc(toolName.replace(/_/g, ' '))}</span>
      </div>
      <div class="approval-card-reason">${_esc(reason)}</div>
      ${headerContent}
      <div class="approval-card-actions">
        <button class="approval-btn-approve"
          onclick="lincolnChat._resolveApproval(true, ${sessionId}, '${safeModel}', ${safeProject}, '${safeThink}', this.closest('.approval-card'))">
          <i class="ti ti-check"></i> Approve
        </button>
        <button class="approval-btn-deny"
          onclick="lincolnChat._resolveApproval(false, ${sessionId}, '${safeModel}', ${safeProject}, '${safeThink}', this.closest('.approval-card'))">
          <i class="ti ti-x"></i> Deny
        </button>
      </div>
    `;

    const bubble = body.querySelector('.message-bubble');
    if (bubble) body.insertBefore(card, bubble);
    else body.appendChild(card);
  }

  // ── ReAct: Resolve approval ───────────────────────────────────────────────

  async function _resolveApproval(approved, sessionId, model, projectId, thinkMode, cardEl) {
    cardEl?.querySelectorAll('button').forEach(b => b.disabled = true);

    const statusEl = document.createElement('div');
    statusEl.className   = 'approval-resolving';
    statusEl.textContent = approved ? 'Executing…' : 'Denied.';
    cardEl?.appendChild(statusEl);

    if (!approved) {
      setTimeout(() => cardEl?.classList.add('approval-card-dismissed'), 500);
    }

    const container      = document.getElementById('chatMessages');
    const lastAssistant  = container?.querySelector('.lincoln-message:last-child');
    const targetEl       = lastAssistant || _appendAssistantMessage('', []);
    const bubbleEl       = targetEl.querySelector('.message-bubble');

    _setStreaming(true);
    const cursor = document.createElement('span');
    cursor.className = 'streaming-cursor';
    if (bubbleEl) bubbleEl.appendChild(cursor);

    let fullText = '';

    try {
      const response = await fetch('/api/chat/resolve_tool', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          session_id: sessionId,
          approved:   approved,
          model:      model,
          project_id: projectId,
          think_mode: thinkMode,
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
              bubbleEl.textContent = fullText;
              bubbleEl.appendChild(cursor);
              _scrollToBottom();
            }

            if (event.type === 'tool_executing') {
              _showToolExecutingIndicator(targetEl, event.tool_name, event.arguments);
            }

            if (event.type === 'tool_result') {
              _updateToolExecutingIndicator(targetEl, event.tool_name, event.result_preview);
            }

            if (event.type === 'tool_denied') {
              _showToast(`Tool denied: ${event.tool_name}`, 'info');
            }

            if (event.type === 'approval_required') {
              // Nested approval — another gated tool in the same ReAct chain
              cursor.remove();
              _setStreaming(false);
              _showApprovalCard(targetEl, event, sessionId, model, projectId, thinkMode);
              return;
            }

            if (event.type === 'done') {
              cursor.remove();
              if (bubbleEl && fullText) {
                _renderFinalMessage(bubbleEl, fullText, [], targetEl);
                // Pin to canvas
                if (typeof lincolnCanvas !== 'undefined') {
                  const blocks = lincolnCanvas.extractCodeBlocks(fullText);
                  blocks.forEach((block, i) => {
                    const suffix   = blocks.length > 1 ? `_part${i + 1}` : '';
                    const baseName = ('executed_code' + suffix + (lincolnChat._langExt?.[block.language] || '.py'));
                    lincolnCanvas.pinCodeBlock({
                      language:    block.language,
                      filename:    lincolnCanvas.resolveFilename(baseName, sessionId),
                      content:     block.content,
                      projectName: '',
                      sessionId:   sessionId,
                    });
                  });
                }
              }
              cardEl?.classList.add('approval-card-dismissed');
              _scrollToBottom();
              if (typeof lincolnSidebar !== 'undefined') lincolnSidebar.loadHistory();
            }

            if (event.type === 'error') {
              cursor.remove();
              if (bubbleEl) {
                bubbleEl.textContent = `Error: ${event.message}`;
                bubbleEl.style.color = 'var(--text-danger)';
              }
            }
          } catch (_) {}
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

  // ── File upload ───────────────────────────────────────────────────────────

  function openFileAttach() {
    if (typeof lincolnSidebar !== 'undefined' && lincolnSidebar.openFileBrowser) {
      lincolnSidebar.openFileBrowser('file', async (fileOrPath) => {
        if (fileOrPath instanceof File) {
          await _uploadFileBlob(fileOrPath);
        } else if (typeof fileOrPath === 'string' && fileOrPath) {
          _openNativePicker();
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

  async function saveMemory() {
    _openMemoryModal();
  }

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
          <p class="modal-hint">
            This summary will appear as context at the top of your next Lincoln session.
            Keep it concise — what are the key facts to carry forward?
          </p>
          <textarea id="memoryModalText" class="modal-textarea"
            placeholder="e.g. BASIN-RERUN-M1 blocked until Aug. rfree2=0.011. Tickers: AMZN AAPL META MSFT."
            rows="5"></textarea>
          <div class="modal-actions">
            <button class="btn-secondary" onclick="document.getElementById('memoryInputModal').remove()">
              Cancel
            </button>
            <button class="btn-primary" onclick="lincolnChat._submitMemory()">
              Save to memory
            </button>
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
        body:    JSON.stringify({
          content:    text,
          project_id: _activeProjectId,
          tag:        'session_summary',
        }),
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
    renderer.code  = function (code, lang) {
      const language = (typeof lang === 'object' ? lang.lang : lang) || '';
      const escaped  = language && hljs.getLanguage(language)
        ? hljs.highlight(code, { language }).value
        : hljs.highlightAuto(code).value;
      const cls = language ? ` class="language-${language} hljs"` : ' class="hljs"';
      return `<pre><code${cls}>${escaped}</code></pre>`;
    };
    marked.use({ renderer, breaks: true, gfm: true });
  })();

  function _md(text) {
    if (typeof marked !== 'undefined') return marked.parse(text || '');
    return _esc(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  function _applyFormatting(element) {
    if (!element) return;
    if (typeof hljs !== 'undefined') {
      element.querySelectorAll('pre code:not(.hljs)').forEach(block => {
        hljs.highlightElement(block);
      });
    }
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(element, {
        delimiters: [
          { left: '$$', right: '$$',   display: true  },
          { left: '\\[', right: '\\]', display: true  },
          { left: '$',  right: '$',    display: false },
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
    } catch (_) {
      recentsEl.innerHTML = '';
    }
  }

  function startNewChat() {
    const home = document.getElementById('projectHome');
    if (home) home.remove();
    _sessionId = null;
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

      if (typeof lincolnCanvas !== 'undefined' && lincolnCanvas.hasSelection?.()) {
        lincolnCanvas.clearSelection(); return;
      }

      if (typeof lincolnSidebar !== 'undefined' && lincolnSidebar.hasSelection?.()) {
        lincolnSidebar.clearSelection(); return;
      }
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
    setTimeout(() => {
      toast.classList.remove('toast-visible');
      setTimeout(() => toast.remove(), 300);
    }, 3500);
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

  function _escEl(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function _fmtDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr), now = new Date();
    if (now - d < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  const _LANG_EXT = {
    python: '.py',      fortran: '.f90',    javascript: '.js',
    typescript: '.ts',  html: '.html',      css: '.css',
    sql: '.sql',        bash: '.sh',        sh: '.sh',
    json: '.json',      markdown: '.md',    r: '.r',
    cpp: '.cpp',        c: '.c',            java: '.java',
    rust: '.rs',        go: '.go',          ruby: '.rb',
    text: '.txt',
    julia: '.jl',       matlab: '.m',       mathematica: '.nb',
    wolfram: '.wl',     rmarkdown: '.Rmd',  sas: '.sas',
    stata: '.do',       gams: '.gms',       ampl: '.ampl',
    lp: '.lp',          maple: '.mpl',      latex: '.tex',
    bibtex: '.bib',     powershell: '.ps1', batch: '.bat',
  };

  function _deriveFilename(userText, language) {
    const ext = _LANG_EXT[language] || '.txt';

    const lincolnMatch = userText.match(/\b(lincoln_[A-Za-z0-9_]+(?:\.[A-Za-z0-9]+)?)\b/i);
    if (lincolnMatch) {
      const name = lincolnMatch[1];
      return name.includes('.') ? name : name + ext;
    }

    const FILLER = /\b(the|a|an|please|can|you|write|make|create|build|give|me|i|want|need|fix|update|rewrite|add|new|version|of|for|with|that|this|and|or|in|to|my|code|file|script|function|class|module|using|show|get|set|just|also|now|here|it|its|is|are|was|were|be|been|being)\b/gi;
    const slug = userText
      .replace(FILLER, ' ')
      .replace(/[^A-Za-z0-9\s]/g, ' ')
      .trim()
      .split(/\s+/)
      .filter(w => w.length > 1)
      .slice(0, 5)
      .join('_')
      .toLowerCase() || 'code';

    return slug + ext;
  }

  function showWelcome() {
    _sessionId = null;
    _clearMessages();
  }

  function showProjectHome(project) {
    _sessionId     = null;
    _activeProject = project;
    _clearMessages();
  }

  // Close think dropdown when clicking outside
  document.addEventListener('click', (e) => {
    const pill = document.getElementById('thinkModePill');
    const dd   = document.getElementById('thinkDropdown');
    if (pill && dd && !pill.contains(e.target) && !dd.contains(e.target)) {
      closeThinkDropdown();
    }
  });

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
    showWelcome,
    showProjectHome,
    showToast:                    _showToast,
    // ReAct approval — called by inline onclick handlers in approval cards
    _resolveApproval,
    _showApprovalCard,
    _showToolExecutingIndicator,
    _updateToolExecutingIndicator,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnChat.init());
