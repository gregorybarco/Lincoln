/**
 * Lincoln Sidebar  v0.4.1
 * ========================
 * Changes from v0.4.0:
 *   - History: no ghost sessions — newSession() is LAZY (only called on first send)
 *   - History: "+ New chat" button added inside the history section header
 *   - History: clicking a history item always switches to Chat mode first
 *   - File browser modal for picking project folder paths
 *   - File browser also available from the attach button (text/code files)
 *   - selectProject() notifies canvas of active project name
 */

const lincolnSidebar = (() => {

  let _activeProjectId = null;
  let _activeMode      = 'chat';
  let _indexPollTimer  = null;


  // ── Init ──────────────────────────────────────────────────────────────────

  async function init() {
    await Promise.all([loadProjects(), loadHistory()]);
  }


  // ── Projects ──────────────────────────────────────────────────────────────

  async function loadProjects() {
    try {
      const res      = await fetch('/api/projects');
      const projects = await res.json();
      _renderProjects(projects);

      if (!_activeProjectId && projects.length > 0) {
        selectProject(projects[0].id, projects[0]);
      }
      if (projects.length === 0) {
        document.getElementById('projectList').innerHTML =
          '<div class="sidebar-empty-state">No projects yet — add one below.</div>';
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
    }
  }

  function _renderProjects(projects) {
    const list = document.getElementById('projectList');
    if (!list) return;
    list.innerHTML = projects.map(p => `
      <div class="sidebar-project-item ${p.id === _activeProjectId ? 'active' : ''}"
           id="projectItem_${p.id}"
           onclick="lincolnSidebar.selectProject(${p.id}, ${JSON.stringify(p).replace(/"/g, '&quot;')})">
        <div class="project-dot ${p.id === _activeProjectId ? 'active' : ''}"></div>
        <div class="project-info">
          <div class="project-name">${_esc(p.display_name)}</div>
          <div class="project-meta">
            ${p.vector_count ? p.vector_count.toLocaleString() + ' vectors' : 'Not indexed'}
            · ${_date(p.last_indexed || p.created_at)}
          </div>
        </div>
      </div>
    `).join('');
  }

  function selectProject(projectId, project) {
    _activeProjectId = projectId;

    document.querySelectorAll('.sidebar-project-item').forEach(el => {
      el.classList.remove('active');
      el.querySelector('.project-dot')?.classList.remove('active');
    });
    const item = document.getElementById(`projectItem_${projectId}`);
    if (item) {
      item.classList.add('active');
      item.querySelector('.project-dot')?.classList.add('active');
    }

    const badge = document.getElementById('topbarProjectBadge');
    if (badge) badge.textContent = project.display_name || project.name;

    const canvasLabel = document.getElementById('canvasProjectLabel');
    if (canvasLabel) canvasLabel.textContent = project.display_name || project.name;

    const aiderLabel = document.getElementById('aiderProjectLabel');
    if (aiderLabel) aiderLabel.textContent = project.display_name || project.name;

    if (typeof lincolnChat !== 'undefined') lincolnChat.setActiveProject(projectId, project);
  }


  // ── New project panel ─────────────────────────────────────────────────────

  function openNewProjectPanel() {
    const overlay = document.getElementById('newProjectOverlay');
    if (overlay) overlay.style.display = 'flex';
    document.getElementById('newProjectPreview').style.display  = 'none';
    document.getElementById('newProjectError').style.display    = 'none';
    document.getElementById('createProjectBtn').style.display   = 'none';
    document.getElementById('newProjectName').value = '';
    document.getElementById('newProjectPath').value = '';
    document.getElementById('newProjectName').focus();
  }

  function closeNewProjectPanel() {
    const overlay = document.getElementById('newProjectOverlay');
    if (overlay) overlay.style.display = 'none';
  }

  async function previewProject() {
    const name    = document.getElementById('newProjectName').value.trim();
    const path    = document.getElementById('newProjectPath').value.trim();
    const errorEl = document.getElementById('newProjectError');
    const prevEl  = document.getElementById('newProjectPreview');

    if (!name || !path) {
      _showError(errorEl, 'Project name and folder path are both required.');
      return;
    }

    errorEl.style.display = 'none';
    prevEl.innerHTML = '<div style="color:var(--text-muted);font-size:12px">Scanning files…</div>';
    prevEl.style.display = 'block';

    try {
      const createRes = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: name, path }),
      });
      const project = await createRes.json();

      if (!createRes.ok) {
        _showError(errorEl, project.error || 'Could not create project.');
        prevEl.style.display = 'none';
        return;
      }

      const previewRes = await fetch(`/api/projects/${project.id}/preview`, { method: 'POST' });
      const preview    = await previewRes.json();

      if (preview.error) {
        _showError(errorEl, preview.error);
        await fetch(`/api/projects/${project.id}`, { method: 'DELETE' });
        prevEl.style.display = 'none';
        return;
      }

      const byLang = Object.entries(preview.by_language || {})
        .map(([lang, count]) => `${count} ${lang}`).join(', ');

      prevEl.innerHTML = `
        <strong>${preview.total} files found</strong> — ${byLang || 'no files'}<br>
        <span style="color:var(--text-muted);font-size:11px">
          Ready to index. Click 'Create and index' to embed.
        </span>
      `;
      document.getElementById('createProjectBtn').dataset.projectId = project.id;
      document.getElementById('createProjectBtn').style.display     = 'inline-flex';

    } catch (err) {
      _showError(errorEl, `Error: ${err.message}`);
      prevEl.style.display = 'none';
    }
  }

  async function createProject() {
    const projectId = document.getElementById('createProjectBtn').dataset.projectId;
    if (!projectId) return;

    closeNewProjectPanel();
    _showToast('Indexing project…');

    try {
      const res  = await fetch(`/api/projects/${projectId}/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_rebuild: false }),
      });
      const data = await res.json();
      if (!res.ok) {
        _hideToast();
        alert(`Index error: ${data.error}`);
        return;
      }
      _pollIndexStatus(parseInt(projectId));
    } catch (err) {
      _hideToast();
      console.error('Index error:', err);
    }
  }

  function _pollIndexStatus(projectId) {
    clearInterval(_indexPollTimer);
    _indexPollTimer = setInterval(async () => {
      try {
        const res    = await fetch(`/api/projects/${projectId}/status`);
        const status = await res.json();
        document.getElementById('indexToastMessage').textContent = status.message;
        if (status.status === 'complete') {
          clearInterval(_indexPollTimer);
          setTimeout(() => { _hideToast(); loadProjects(); }, 1500);
        } else if (status.status === 'error') {
          clearInterval(_indexPollTimer);
          _hideToast();
          alert(`Index failed: ${status.message}`);
          loadProjects();
        }
      } catch (err) {
        clearInterval(_indexPollTimer);
        _hideToast();
      }
    }, 1500);
  }


  // ── File browser modal ────────────────────────────────────────────────────
  // Used by both "Pick folder" in New Project and "Attach file" in chat input.

  let _fileBrowserMode   = 'folder';   // 'folder' | 'file'
  let _fileBrowserTarget = null;       // callback(selectedPath)

  function openFileBrowser(mode, callback) {
    _fileBrowserMode   = mode || 'folder';
    _fileBrowserTarget = callback;

    let modal = document.getElementById('fileBrowserModal');
    if (!modal) {
      modal = _createFileBrowserModal();
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    _browsePath('');
  }

  function _createFileBrowserModal() {
    const modal = document.createElement('div');
    modal.id        = 'fileBrowserModal';
    modal.className = 'lincoln-overlay';
    modal.innerHTML = `
      <div class="lincoln-panel" style="width:520px;max-height:70vh">
        <div class="panel-header">
          <div class="panel-title" id="fbTitle">Browse files</div>
          <button class="panel-close" onclick="lincolnSidebar.closeFileBrowser()">
            <i class="ti ti-x"></i>
          </button>
        </div>
        <div style="padding:8px 14px;border-bottom:0.5px solid var(--border);display:flex;gap:6px;align-items:center">
          <input id="fbPathInput" class="form-input" style="flex:1;font-size:12px;font-family:var(--font-mono)"
                 placeholder="Type a path…"
                 onkeydown="if(event.key==='Enter') lincolnSidebar._browsePath(this.value)">
          <button class="panel-btn-primary" onclick="lincolnSidebar._browsePath(document.getElementById('fbPathInput').value)">
            Go
          </button>
        </div>
        <div id="fbList" style="flex:1;overflow-y:auto;padding:8px 6px;min-height:200px">
          <div style="padding:20px;text-align:center;color:var(--text-muted);font-size:12px">Loading…</div>
        </div>
        <div class="panel-footer" style="justify-content:space-between;align-items:center">
          <span id="fbSelected" style="font-size:11px;color:var(--text-muted);font-family:var(--font-mono);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
          <div style="display:flex;gap:8px">
            <button class="panel-btn-secondary" onclick="lincolnSidebar.closeFileBrowser()">Cancel</button>
            <button class="panel-btn-confirm" id="fbConfirm" onclick="lincolnSidebar._confirmBrowser()" disabled>
              Select
            </button>
          </div>
        </div>
      </div>
    `;
    return modal;
  }

  let _fbCurrentPath = '';

  async function _browsePath(path) {
    _fbCurrentPath = path;
    const input = document.getElementById('fbPathInput');
    if (input) input.value = path;

    const list = document.getElementById('fbList');
    if (!list) return;
    list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:12px">Loading…</div>';

    try {
      const res  = await fetch(`/api/files/browse?path=${encodeURIComponent(path)}`);
      const data = await res.json();

      if (data.error) {
        list.innerHTML = `<div style="padding:12px;color:var(--text-danger);font-size:12px">${_esc(data.error)}</div>`;
        return;
      }

      let html = '';

      // Up button
      if (data.parent !== null) {
        html += `
          <div class="fb-entry fb-dir" onclick="lincolnSidebar._browsePath(${JSON.stringify(data.parent)})">
            <i class="ti ti-arrow-up"></i>
            <span>..</span>
          </div>
        `;
      }

      // Entries
      data.entries.forEach(entry => {
        const isDir  = entry.type === 'dir';
        const isFile = entry.type === 'file';
        const selectable = (_fileBrowserMode === 'folder' && isDir) ||
                           (_fileBrowserMode === 'file'   && isFile);

        if (isDir) {
          html += `
            <div class="fb-entry fb-dir" onclick="lincolnSidebar._browsePath(${JSON.stringify(entry.path)})">
              <i class="ti ti-folder-filled" style="color:#f59e0b"></i>
              <span>${_esc(entry.name)}</span>
              ${selectable ? `<button class="fb-select-btn" onclick="event.stopPropagation();lincolnSidebar._selectBrowserEntry(${JSON.stringify(entry.path)})">Select</button>` : ''}
            </div>
          `;
        } else if (isFile && _fileBrowserMode === 'file') {
          html += `
            <div class="fb-entry fb-file" onclick="lincolnSidebar._selectBrowserEntry(${JSON.stringify(entry.path)})">
              <i class="ti ti-file-code" style="color:var(--text-muted)"></i>
              <span>${_esc(entry.name)}</span>
            </div>
          `;
        } else {
          html += `
            <div class="fb-entry fb-file fb-disabled">
              <i class="ti ti-file" style="color:var(--border-strong)"></i>
              <span style="color:var(--text-muted)">${_esc(entry.name)}</span>
            </div>
          `;
        }
      });

      if (!data.entries.length && data.parent === null) {
        html = '<div style="padding:12px;color:var(--text-muted);font-size:12px">No items found.</div>';
      }

      list.innerHTML = html;

    } catch (err) {
      list.innerHTML = `<div style="padding:12px;color:var(--text-danger);font-size:12px">Error: ${_esc(err.message)}</div>`;
    }
  }

  function _selectBrowserEntry(path) {
    const selected = document.getElementById('fbSelected');
    const confirm  = document.getElementById('fbConfirm');
    if (selected) selected.textContent = path;
    if (confirm)  confirm.disabled = false;
    _fbCurrentPath = path;
  }

  function _confirmBrowser() {
    const path = document.getElementById('fbSelected')?.textContent;
    if (path && _fileBrowserTarget) {
      _fileBrowserTarget(path);
    }
    closeFileBrowser();
  }

  function closeFileBrowser() {
    const modal = document.getElementById('fileBrowserModal');
    if (modal) modal.style.display = 'none';
  }


  // ── Chat history ──────────────────────────────────────────────────────────

  async function loadHistory() {
    try {
      const res      = await fetch('/api/history');
      const sessions = await res.json();
      _renderHistory(sessions);
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  }

  function _renderHistory(sessions) {
    const list = document.getElementById('historyList');
    if (!list) return;

    // Filter out brand-new "New chat" sessions with no messages yet
    const realSessions = sessions.filter(s => s.title !== 'New chat' || s.updated_at !== s.created_at);

    if (!realSessions.length) {
      list.innerHTML = '<div class="sidebar-empty-state">No history yet.</div>';
      return;
    }

    list.innerHTML = realSessions.map(s => `
      <div class="sidebar-history-item" id="historyItem_${s.id}"
           onclick="lincolnSidebar._openHistorySession(${s.id})">
        <div class="history-title">${_esc(s.title)}</div>
        <div class="history-date">${_date(s.updated_at)}</div>
        <button class="history-delete-btn" title="Delete chat"
                onclick="event.stopPropagation();lincolnSidebar.deleteSession(${s.id})">
          <i class="ti ti-trash"></i>
        </button>
      </div>
    `).join('');
  }

  function _openHistorySession(sessionId) {
    // Always switch to Chat mode first, then load session
    switchMode('chat');
    if (typeof lincolnChat !== 'undefined') lincolnChat.loadSession(sessionId);
  }

  async function deleteSession(sessionId) {
    if (!confirm('Delete this chat? This cannot be undone.')) return;
    try {
      await fetch(`/api/history/${sessionId}`, { method: 'DELETE' });
      document.getElementById(`historyItem_${sessionId}`)?.remove();
    } catch (err) {
      console.error('Delete session error:', err);
    }
  }


  // ── Mode switching ────────────────────────────────────────────────────────

  function switchMode(mode) {
    _activeMode = mode;

    ['navChat', 'navAider', 'navMemory'].forEach(id =>
      document.getElementById(id)?.classList.remove('active')
    );
    const navMap = { chat: 'navChat', aider: 'navAider', memory: 'navMemory' };
    document.getElementById(navMap[mode])?.classList.add('active');

    const views = { chat: 'chatView', aider: 'aiderView', memory: 'memoryView' };
    Object.entries(views).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el) el.style.display = key === mode ? 'flex' : 'none';
    });
  }

  function launchAider() {
    alert(
      'Open a new terminal window and run:\n\n' +
      '  cd B:\\Homebrewed_AI\\Lincoln\n' +
      '  venv\\Scripts\\activate\n' +
      '  aider\n\n' +
      'Return to Lincoln in your browser when done.'
    );
  }


  // ── Toast helpers ─────────────────────────────────────────────────────────

  function _showToast(message) {
    const toast = document.getElementById('indexToast');
    const msg   = document.getElementById('indexToastMessage');
    if (msg)   msg.textContent    = message;
    if (toast) toast.style.display = 'block';
  }

  function _hideToast() {
    const toast = document.getElementById('indexToast');
    if (toast) toast.style.display = 'none';
  }


  // ── Utilities ─────────────────────────────────────────────────────────────

  function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function _showError(el, message) {
    el.textContent   = message;
    el.style.display = 'block';
  }

  function _date(isoStr) {
    if (!isoStr) return '';
    const date = new Date(isoStr);
    const now  = new Date();
    if (now - date < 86400000) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }


  // ── Public API ────────────────────────────────────────────────────────────

  return {
    init,
    loadProjects,
    loadHistory,
    selectProject,
    openNewProjectPanel,
    closeNewProjectPanel,
    previewProject,
    createProject,
    deleteSession,
    switchMode,
    launchAider,
    openFileBrowser,
    closeFileBrowser,
    _browsePath,
    _selectBrowserEntry,
    _confirmBrowser,
    get activeProjectId() { return _activeProjectId; },
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSidebar.init());
