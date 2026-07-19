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
  let _activeProject   = null;
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
        // Don't auto-select — start with no project selected
        _showNoProjectHome();
      }
      if (projects.length === 0) {
        document.getElementById('projectList').innerHTML =
          '<div class="sidebar-empty-state">No projects yet — add one below.</div>';
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
    }
  }

  function _showNoProjectHome() {
    // Show general chat home when no project is selected
    if (typeof lincolnChat !== 'undefined') {
      lincolnChat.setActiveProject(null, null);
      lincolnChat.newSession();
    }
  }

  function _renderProjects(projects) {
    const list = document.getElementById('projectList');
    if (!list) return;

    // "General" — no project selected
    const generalActive = !_activeProjectId;
    let html = `
      <div class="sidebar-project-item ${generalActive ? 'active' : ''}"
           id="projectItemGeneral"
           onclick="lincolnSidebar.selectNoProject()">
        <div class="project-dot ${generalActive ? 'active' : ''}"></div>
        <div class="project-info">
          <div class="project-name">General</div>
          <div class="project-meta">No project — open chat</div>
        </div>
      </div>
    `;

    html += projects.map(p => `
      <div class="sidebar-project-item ${p.id === _activeProjectId ? 'active' : ''}"
           id="projectItem_${p.id}"
           onclick="lincolnSidebar.selectProject(${p.id}, ${JSON.stringify(p).replace(/"/g, '&quot;')})">
        <div class="project-dot ${p.id === _activeProjectId ? 'active' : ''}"></div>
        <div class="project-info">
          <div class="project-name">${_esc(p.display_name)}</div>
          <div class="project-meta">
            ${p.vector_count ? p.vector_count.toLocaleString() + ' vectors' : 'No index'}
            · ${_date(p.last_indexed || p.created_at)}
          </div>
        </div>
        <button class="project-settings-btn" title="Project settings"
                onclick="event.stopPropagation();lincolnSidebar.openProjectSettings(${p.id}, ${JSON.stringify(p).replace(/"/g, '&quot;')})">
          <i class="ti ti-settings" aria-hidden="true"></i>
        </button>
      </div>
    `).join('');

    list.innerHTML = html;
  }

  function selectNoProject() {
    _activeProjectId = null;
    _activeProject   = null;

    document.querySelectorAll('.sidebar-project-item').forEach(el => {
      el.classList.remove('active');
      el.querySelector('.project-dot')?.classList.remove('active');
    });
    document.getElementById('projectItemGeneral')?.classList.add('active');
    document.getElementById('projectItemGeneral')?.querySelector('.project-dot')?.classList.add('active');

    const badge = document.getElementById('topbarProjectBadge');
    if (badge) badge.textContent = 'No project';

    if (typeof lincolnChat !== 'undefined') {
      lincolnChat.setActiveProject(null, null);
      lincolnChat.newSession();
    }
    if (typeof lincolnCanvas !== 'undefined') lincolnCanvas.clear();
    loadHistory();
  }

  function selectProject(projectId, project) {
    _activeProjectId = projectId;
    _activeProject   = project;

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
    if (canvasLabel) canvasLabel.textContent = '';  // set per-session not per-project

    const aiderLabel = document.getElementById('aiderProjectLabel');
    if (aiderLabel) aiderLabel.textContent = project.display_name || project.name;

    if (typeof lincolnChat !== 'undefined') lincolnChat.setActiveProject(projectId, project);

    // Canvas is siloed per project — clear when switching
    if (typeof lincolnCanvas !== 'undefined') lincolnCanvas.clear();

    // Switch to chat mode and start a new session inside this project
    switchMode('chat');
    if (typeof lincolnChat !== 'undefined') lincolnChat.newSession();

    // Re-render history so this project's chats appear grouped
    loadHistory();
  }


  // ── New project panel ─────────────────────────────────────────────────────

  function openNewProjectPanel() {
    const overlay = document.getElementById('newProjectOverlay');
    if (overlay) overlay.style.display = 'flex';
    document.getElementById('newProjectError').style.display = 'none';
    document.getElementById('newProjectName').value = '';
    const desc = document.getElementById('newProjectDesc');
    if (desc) desc.value = '';
    document.getElementById('newProjectName').focus();
  }

  function closeNewProjectPanel() {
    const overlay = document.getElementById('newProjectOverlay');
    if (overlay) overlay.style.display = 'none';
  }

  // previewProject kept for compatibility but not used in simplified panel
  async function previewProject() {}

  async function createProject() {
    const name    = document.getElementById('newProjectName')?.value.trim();
    const desc    = document.getElementById('newProjectDesc')?.value.trim() || '';
    const errorEl = document.getElementById('newProjectError');

    if (!name) {
      _showError(errorEl, 'Project name is required.');
      return;
    }

    try {
      // Create project with no path — it's a conversation silo, path is optional
      const res     = await fetch('/api/projects', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ display_name: name, path: '.', description: desc }),
      });
      const project = await res.json();

      if (!res.ok) {
        _showError(errorEl, project.error || 'Could not create project.');
        return;
      }

      closeNewProjectPanel();
      await loadProjects();
      selectProject(project.id, project);

    } catch (err) {
      _showError(errorEl, `Error: ${err.message}`);
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


  // ── Project settings panel ────────────────────────────────────────────────

  let _settingsProjectId   = null;
  let _settingsWriteEnabled = false;

  function openProjectSettings(projectId, project) {
    _settingsProjectId    = projectId;
    _settingsWriteEnabled = !!(project.write_enabled);

    document.getElementById('projectSettingsTitle').textContent = project.display_name;
    document.getElementById('projSettingsPath').value     = (project.path && project.path !== '.') ? project.path : '';
    document.getElementById('projSettingsCodePath').value = project.code_path || '';
    document.getElementById('projectSettingsError').style.display = 'none';

    _updateWriteToggle(_settingsWriteEnabled);

    // Show index status
    const statusEl = document.getElementById('projectIndexStatus');
    if (project.vector_count) {
      statusEl.innerHTML = `
        <strong>${project.vector_count.toLocaleString()} vectors indexed</strong>
        · Last indexed ${_date(project.last_indexed)}
        <span style="color:var(--text-muted);font-size:11px;display:block;margin-top:2px">
          Click "Index now" to rebuild after code changes.
        </span>`;
    } else {
      statusEl.innerHTML = `
        <strong style="color:var(--text-muted)">Not indexed yet</strong>
        <span style="color:var(--text-muted);font-size:11px;display:block;margin-top:2px">
          Add a RAG source folder and click "Index now".
        </span>`;
    }

    document.getElementById('projectSettingsOverlay').style.display = 'flex';
  }

  function closeProjectSettings() {
    document.getElementById('projectSettingsOverlay').style.display = 'none';
    _settingsProjectId = null;
  }

  function toggleWriteAccess() {
    _settingsWriteEnabled = !_settingsWriteEnabled;
    _updateWriteToggle(_settingsWriteEnabled);
  }

  function _updateWriteToggle(enabled) {
    const btn = document.getElementById('writeToggleBtn');
    if (!btn) return;
    if (enabled) {
      btn.textContent  = 'On — write enabled';
      btn.style.background = 'var(--danger-bg)';
      btn.style.color      = 'var(--text-danger)';
      btn.style.borderColor = 'var(--text-danger)';
    } else {
      btn.textContent  = 'Off — read only';
      btn.style.background  = 'var(--bg-surface)';
      btn.style.color       = 'var(--text-secondary)';
      btn.style.borderColor = 'var(--border)';
    }
  }

  async function saveProjectSettings() {
    if (!_settingsProjectId) return;
    const path      = document.getElementById('projSettingsPath').value.trim();
    const codePath  = document.getElementById('projSettingsCodePath').value.trim();
    const errorEl   = document.getElementById('projectSettingsError');
    errorEl.style.display = 'none';

    try {
      const res = await fetch(`/api/projects/${_settingsProjectId}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          path:          path  || '.',
          code_path:     codePath || '',
          write_enabled: _settingsWriteEnabled,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        errorEl.textContent   = data.error || 'Could not save settings.';
        errorEl.style.display = 'block';
        return;
      }
      closeProjectSettings();
      await loadProjects();
    } catch (err) {
      errorEl.textContent   = `Error: ${err.message}`;
      errorEl.style.display = 'block';
    }
  }

  async function indexActiveProject() {
    if (!_settingsProjectId) return;

    // Save settings first so path is set before indexing
    await saveProjectSettings();

    _showToast('Indexing project…');
    try {
      const res  = await fetch(`/api/projects/${_settingsProjectId}/index`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ force_rebuild: false }),
      });
      const data = await res.json();
      if (!res.ok) {
        _hideToast();
        alert(`Index error: ${data.error}`);
        return;
      }
      _pollIndexStatus(_settingsProjectId);
    } catch (err) {
      _hideToast();
      console.error('Index error:', err);
    }
  }

  async function deleteActiveProject() {
    if (!_settingsProjectId) return;
    const name = document.getElementById('projectSettingsTitle').textContent;
    if (!confirm(`Delete project "${name}"? All chats in this project will also be deleted. This cannot be undone.`)) return;

    try {
      await fetch(`/api/projects/${_settingsProjectId}?wipe_index=false`, { method: 'DELETE' });
      closeProjectSettings();
      await loadProjects();
    } catch (err) {
      console.error('Delete project error:', err);
    }
  }


  // ── Native file/folder picker ─────────────────────────────────────────────
  // Uses the browser's built-in OS file dialog — no fake browser modal.
  // On Windows this opens the native Windows Explorer picker.

  let _fileBrowserMode   = 'folder';
  let _fileBrowserTarget = null;

  function openFileBrowser(mode, callback) {
    _fileBrowserMode   = mode || 'folder';
    _fileBrowserTarget = callback;

    const input = document.createElement('input');
    input.type  = 'file';

    if (mode === 'folder') {
      // Opens native folder picker on Windows/Chrome
      input.setAttribute('webkitdirectory', '');
      input.setAttribute('directory', '');
    } else {
      // Opens native file picker
      input.accept = '.py,.f90,.f95,.f03,.f,.for,.js,.ts,.css,.html,.sql,.md,.txt,.json,.yaml,.toml,.c,.cpp,.h,.sh,.bat';
    }

    input.style.display = 'none';
    document.body.appendChild(input);

    input.addEventListener('change', () => {
      let selectedPath = '';
      if (input.files && input.files.length > 0) {
        if (mode === 'folder') {
          // webkitRelativePath gives 'foldername/file.ext' — extract just the folder name
          // For a real absolute path, user types it manually in the path input
          // We surface the folder name as a hint
          const rel = input.files[0].webkitRelativePath;
          selectedPath = rel.split('/')[0];
        } else {
          selectedPath = input.files[0].name;
        }
      }
      document.body.removeChild(input);
      if (selectedPath && _fileBrowserTarget) {
        _fileBrowserTarget(selectedPath);
      }
    });

    input.click();
  }

  // Stubs for public API compatibility — no-ops since we use native picker now
  function closeFileBrowser() {}
  function _browsePath() {}
  function _selectBrowserEntry() {}
  function _confirmBrowser() {}


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

    if (!sessions.length) {
      list.innerHTML = '<div class="sidebar-empty-state">No history yet.</div>';
      return;
    }

    // Add bulk clear button to header if not already there
    const header = document.querySelector('.sidebar-history .sidebar-section-label');
    if (header && !document.getElementById('clearAllHistoryBtn')) {
      const clearBtn       = document.createElement('button');
      clearBtn.id          = 'clearAllHistoryBtn';
      clearBtn.className   = 'sidebar-section-action';
      clearBtn.title       = 'Clear all history';
      clearBtn.innerHTML   = '<i class="ti ti-trash" style="color:var(--text-danger)"></i>';
      clearBtn.onclick     = () => lincolnSidebar.clearAllHistory();
      header.appendChild(clearBtn);
    }

    // Group sessions: active project's chats first, then general, then others
    const projectSessions = sessions.filter(s => s.project_id === _activeProjectId && _activeProjectId);
    const generalSessions = sessions.filter(s => !s.project_id);
    const otherSessions   = sessions.filter(s => s.project_id && s.project_id !== _activeProjectId);

    function _sessionHTML(s) {
      return `
        <div class="sidebar-history-item" id="historyItem_${s.id}"
             onclick="lincolnSidebar._openHistorySession(${s.id})">
          <div class="history-title">${_esc(s.title)}</div>
          <div class="history-date">${_date(s.updated_at)}</div>
          <button class="history-delete-btn" title="Delete chat"
                  onclick="event.stopPropagation();lincolnSidebar.deleteSession(${s.id})">
            <i class="ti ti-trash"></i>
          </button>
        </div>`;
    }

    let html = '';

    // Active project chats — no label needed, they're the current context
    if (projectSessions.length && _activeProjectId) {
      html += projectSessions.map(_sessionHTML).join('');
    }

    // General chats
    if (generalSessions.length) {
      if (projectSessions.length) {
        html += `<div class="history-group-label">General</div>`;
      }
      html += generalSessions.map(_sessionHTML).join('');
    }

    // Other project chats — show which project they belong to
    const otherByProject = {};
    otherSessions.forEach(s => {
      const label = s.project_display_name || 'Other';
      if (!otherByProject[label]) otherByProject[label] = [];
      otherByProject[label].push(s);
    });
    Object.entries(otherByProject).forEach(([label, group]) => {
      html += `<div class="history-group-label">${_esc(label)}</div>`;
      html += group.map(_sessionHTML).join('');
    });

    list.innerHTML = html;
  }

  function _openHistorySession(sessionId) {
  switchMode('chat');
  setTimeout(() => lincolnChat.loadSession(sessionId), 0);
}

  async function clearAllHistory() {
    if (!confirm('Delete all chat history? This cannot be undone.')) return;
    try {
      await fetch('/api/history/all', { method: 'DELETE' });
      document.getElementById('historyList').innerHTML =
        '<div class="sidebar-empty-state">No history yet.</div>';
      document.getElementById('clearAllHistoryBtn')?.remove();
    } catch (err) {
      console.error('Clear all history error:', err);
    }
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
    selectNoProject,
    openProjectSettings,
    closeProjectSettings,
    toggleWriteAccess,
    saveProjectSettings,
    indexActiveProject,
    deleteActiveProject,
    openNewProjectPanel,
    closeNewProjectPanel,
    previewProject,
    createProject,
    deleteSession,
    clearAllHistory,
    switchMode,
    launchAider,
    openFileBrowser,
    closeFileBrowser,
    _browsePath,
    _selectBrowserEntry,
    _confirmBrowser,
    _openHistorySession,
    get activeProjectId() { return _activeProjectId; },
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSidebar.init());
