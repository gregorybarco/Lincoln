/**
 * Lincoln Sidebar  v0.5.0
 * ========================
 * Changes from v0.4.1:
 *   - BUG FIX: clicking history item no longer shows project home + chat simultaneously
 *   - History: per-project chat toggle (hidden by default, matching Claude behaviour)
 *   - History: numbered group count badges
 *   - History: clearer group dividers with border-top
 *   - Project settings: folder browser writes full absolute path to input field
 *   - Project settings: path-resolved feedback under input
 *   - Project settings: Aider code folder has clear explainer
 *   - Project settings: write access warning shows/hides dynamically
 *   - openFolderPicker() uses webkitdirectory — on Windows/Chrome this is the native
 *     Explorer picker; the full path is NOT available via web API so we surface the
 *     folder name as a hint and ask user to paste the full path if needed
 *   - onPathInput() shows a green resolved badge when path looks absolute
 */

const lincolnSidebar = (() => {

  let _activeProjectId = null;
  let _activeProject   = null;
  let _activeMode      = 'chat';
  let _indexPollTimer  = null;
  let _showProjectChats = false;   // v0.5.0: project chats hidden by default

  // ── Project settings state ────────────────────────────────────────────────
  let _settingsProjectId   = null;
  let _settingsWriteEnabled = false;


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
    if (typeof lincolnChat !== 'undefined') {
      lincolnChat.setActiveProject(null, null);
    }
  }

  function _renderProjects(projects) {
    const list = document.getElementById('projectList');
    if (!list) return;

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
            ${p.vector_count
              ? `<span style="color:var(--text-success)">${p.vector_count} vectors</span>`
              : 'No index'}
          </div>
        </div>
        <button class="project-settings-btn"
                onclick="event.stopPropagation();lincolnSidebar.openProjectSettings(${p.id}, ${JSON.stringify(p).replace(/"/g, '&quot;')})"
                title="Project settings">
          <i class="ti ti-settings"></i>
        </button>
      </div>
    `).join('');

    list.innerHTML = html;
  }

  function selectNoProject() {
    _activeProjectId = null;
    _activeProject   = null;

    document.querySelectorAll('.sidebar-project-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.project-dot').forEach(el => el.classList.remove('active'));
    document.getElementById('projectItemGeneral')?.classList.add('active');
    document.getElementById('projectItemGeneral')?.querySelector('.project-dot')?.classList.add('active');

    document.getElementById('topbarProjectBadge').textContent = 'No project';

    // Show general welcome (NOT project home)
    if (typeof lincolnChat !== 'undefined') {
      lincolnChat.setActiveProject(null, null);
      lincolnChat.showWelcome();
    }
    if (typeof lincolnCanvasUI !== 'undefined') lincolnCanvasUI.show();
    loadHistory();
  }

  function selectProject(projectId, project) {
    _activeProjectId = projectId;
    _activeProject   = project;

    document.querySelectorAll('.sidebar-project-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.project-dot').forEach(el => el.classList.remove('active'));
    const item = document.getElementById(`projectItem_${projectId}`);
    item?.classList.add('active');
    item?.querySelector('.project-dot')?.classList.add('active');

    document.getElementById('topbarProjectBadge').textContent = project.display_name;

    // Show project home — canvas hides on project home
    if (typeof lincolnChat !== 'undefined') {
      lincolnChat.setActiveProject(projectId, project);
      lincolnChat.showProjectHome(project);
    }
    if (typeof lincolnCanvasUI !== 'undefined') lincolnCanvasUI.hide();
    loadHistory();
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

  function toggleProjectHistory() {
    _showProjectChats = !_showProjectChats;
    const btn = document.getElementById('historyProjectToggle');
    if (btn) btn.textContent = `project chats: ${_showProjectChats ? 'on' : 'off'}`;
    loadHistory();
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
      // Insert before the toggle+plus group
      header.insertBefore(clearBtn, header.lastElementChild);
    }

    // Group sessions
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

    function _groupLabel(label, count) {
      return `<div class="history-group-label">
        <span>${_esc(label)}</span>
        <span class="history-group-count">${count}</span>
      </div>`;
    }

    let html = '';

    // Active project chats — only if toggle is on
    if (_showProjectChats && projectSessions.length && _activeProjectId) {
      html += _groupLabel(_activeProject?.display_name || 'Project', projectSessions.length);
      html += projectSessions.map(_sessionHTML).join('');
    }

    // General chats
    if (generalSessions.length) {
      if (html) html += _groupLabel('General', generalSessions.length);
      html += generalSessions.map(_sessionHTML).join('');
    }

    // Other project chats — only if toggle is on
    if (_showProjectChats) {
      const otherByProject = {};
      otherSessions.forEach(s => {
        const label = s.project_display_name || 'Other';
        if (!otherByProject[label]) otherByProject[label] = [];
        otherByProject[label].push(s);
      });
      Object.entries(otherByProject).forEach(([label, group]) => {
        html += _groupLabel(label, group.length);
        html += group.map(_sessionHTML).join('');
      });
    }

    if (!html) {
      html = '<div class="sidebar-empty-state">No general chats yet.</div>';
    }

    list.innerHTML = html;
  }

  /**
   * v0.5.0 BUG FIX: clicking a history item must:
   *   1. Switch to chat mode
   *   2. Hide the project home / welcome screen
   *   3. Show the messages container
   *   4. Load the session
   * Previously the project home was left visible underneath.
   */
  function _openHistorySession(sessionId) {
    switchMode('chat');
    // Hide project home / welcome — show messages
    const welcome  = document.getElementById('lincolnWelcome');
    const messages = document.getElementById('chatMessages');
    if (welcome)  welcome.style.display  = 'none';
    if (messages) messages.style.display = 'flex';
    // Show canvas if it was hidden for project home
    if (typeof lincolnCanvasUI !== 'undefined') lincolnCanvasUI.show();
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

  async function createProject() {
    const name    = document.getElementById('newProjectName')?.value.trim();
    const desc    = document.getElementById('newProjectDesc')?.value.trim() || '';
    const errorEl = document.getElementById('newProjectError');

    if (!name) {
      _showError(errorEl, 'Project name is required.');
      return;
    }

    try {
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


  // ── Project settings panel ────────────────────────────────────────────────

  function openProjectSettings(projectId, project) {
    _settingsProjectId    = projectId;
    _settingsWriteEnabled = project.write_enabled || false;

    document.getElementById('projectSettingsTitle').textContent = project.display_name;
    document.getElementById('projSettingsPath').value     = project.path && project.path !== '.' ? project.path : '';
    document.getElementById('projSettingsCodePath').value = project.code_path || '';
    document.getElementById('projectSettingsError').style.display = 'none';

    // Show/reset path resolved badges
    _updatePathResolved('projSettingsPath', 'ragPathResolved');
    _updatePathResolved('projSettingsCodePath', 'aiderPathResolved');

    _updateWriteToggle(_settingsWriteEnabled);

    // Write access warning visibility
    document.getElementById('writeAccessWarning').style.display = 'none';

    // Index status
    const statusEl = document.getElementById('projectIndexStatus');
    if (project.vector_count) {
      statusEl.innerHTML = `
        <strong style="color:var(--text-success)">Indexed</strong>
        <span style="color:var(--text-muted);font-size:11px;display:block;margin-top:2px">
          ${project.vector_count} vectors · Last indexed ${_date(project.last_indexed)}
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
    document.getElementById('writeAccessWarning').style.display =
      _settingsWriteEnabled ? 'flex' : 'none';
  }

  function _updateWriteToggle(enabled) {
    const btn = document.getElementById('writeToggleBtn');
    if (!btn) return;
    if (enabled) {
      btn.textContent       = 'On — write enabled';
      btn.style.background  = 'var(--danger-bg)';
      btn.style.color       = 'var(--text-danger)';
      btn.style.borderColor = 'var(--text-danger)';
    } else {
      btn.textContent       = 'Off — read only';
      btn.style.background  = 'var(--bg-surface)';
      btn.style.color       = 'var(--text-secondary)';
      btn.style.borderColor = 'var(--border)';
    }
  }

  /**
   * v0.5.0: Path input handler — shows green resolved badge when path
   * looks like an absolute Windows or Unix path.
   */
  function onPathInput(inputId, resolvedId) {
    _updatePathResolved(inputId, resolvedId);
  }

  function _updatePathResolved(inputId, resolvedId) {
    const input    = document.getElementById(inputId);
    const resolved = document.getElementById(resolvedId);
    if (!input || !resolved) return;
    const val  = input.value.trim();
    const isAbs = /^[A-Za-z]:[\\\/]/.test(val) || val.startsWith('/');
    if (val && isAbs) {
      resolved.textContent = `✓ ${val}`;
      resolved.classList.add('visible');
    } else {
      resolved.classList.remove('visible');
    }
  }

  /**
   * v0.5.0: Folder picker.
   * webkitdirectory on Chrome opens the Windows native folder picker.
   * Due to browser security, we cannot read the full absolute path —
   * only the relative folder name is available via the File API.
   * We show the folder name as a hint in the placeholder and tell
   * the user to paste the full path manually if the hint is insufficient.
   */
  function openFolderPicker(targetInputId, resolvedId) {
    const picker = document.createElement('input');
    picker.type  = 'file';
    picker.setAttribute('webkitdirectory', '');
    picker.setAttribute('directory', '');
    picker.style.display = 'none';
    document.body.appendChild(picker);

    picker.addEventListener('change', () => {
      document.body.removeChild(picker);
      if (!picker.files || picker.files.length === 0) return;

      // webkitRelativePath = 'FolderName/file.ext' — extract folder name
      const rel        = picker.files[0].webkitRelativePath || '';
      const folderName = rel.split('/')[0] || '';

      const input = document.getElementById(targetInputId);
      if (!input) return;

      // If input is already filled with an absolute path that ends in this
      // folder name, don't overwrite it. Otherwise set folder name as hint.
      const existing = input.value.trim();
      if (existing && existing.toLowerCase().endsWith(folderName.toLowerCase())) {
        // Already correct — just validate
        _updatePathResolved(targetInputId, resolvedId);
        return;
      }

      if (folderName) {
        // Populate placeholder so user sees which folder was selected
        input.placeholder = folderName + ' (paste full path, e.g. B:\\projects\\' + folderName + ')';
        // If input is empty, fill with folder name as a starting point
        if (!existing) {
          input.value = folderName;
        }
      }
      _updatePathResolved(targetInputId, resolvedId);
    });

    picker.click();
  }

  // Keep compatibility with old inline usage
  function closeFileBrowser() {}
  function _browsePath() {}
  function _selectBrowserEntry() {}
  function _confirmBrowser() {}

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
      _activeProjectId = null;
      _activeProject   = null;
      await loadProjects();
      selectNoProject();
    } catch (err) {
      console.error('Delete project error:', err);
    }
  }


  // ── Index polling ─────────────────────────────────────────────────────────

  function _pollIndexStatus(projectId) {
    if (_indexPollTimer) clearInterval(_indexPollTimer);
    _indexPollTimer = setInterval(async () => {
      try {
        const res  = await fetch(`/api/projects/${projectId}/status`);
        const data = await res.json();
        if (data.status === 'idle') {
          clearInterval(_indexPollTimer);
          _indexPollTimer = null;
          _hideToast();
          await loadProjects();
        } else {
          _showToast(data.message || 'Indexing…');
        }
      } catch (_) {
        clearInterval(_indexPollTimer);
        _indexPollTimer = null;
        _hideToast();
      }
    }, 1500);
  }

  function _showToast(msg) {
    const toast = document.getElementById('indexToast');
    const label = document.getElementById('indexToastMessage');
    if (toast) toast.style.display = 'block';
    if (label) label.textContent = msg;
  }

  function _hideToast() {
    const toast = document.getElementById('indexToast');
    if (toast) toast.style.display = 'none';
  }


  // ── File browser (stubs — replaced by openFolderPicker) ──────────────────

  function openFileBrowser(mode, callback) {
    // Delegate to native picker for folder mode
    if (mode === 'folder') {
      const tempId = '_tmpFolderInput_' + Date.now();
      const picker = document.createElement('input');
      picker.type  = 'file';
      picker.setAttribute('webkitdirectory', '');
      picker.style.display = 'none';
      document.body.appendChild(picker);
      picker.addEventListener('change', () => {
        document.body.removeChild(picker);
        if (picker.files && picker.files.length > 0) {
          const rel    = picker.files[0].webkitRelativePath || '';
          const folder = rel.split('/')[0] || '';
          if (folder && callback) callback(folder);
        }
      });
      picker.click();
    } else {
      // File mode — use native file input
      const input = document.createElement('input');
      input.type   = 'file';
      input.accept = '.py,.f90,.f95,.f03,.f,.for,.js,.ts,.css,.html,.sql,.md,.txt,.csv,.json,.yaml,.toml,.c,.cpp,.h,.sh,.bat,.tex,.maple,.mw,.mpl,.ipynb,.bib,.pdf,.docx,.xlsx';
      input.style.display = 'none';
      document.body.appendChild(input);
      input.addEventListener('change', () => {
        document.body.removeChild(input);
        if (input.files && input.files.length > 0 && callback) {
          callback(input.files[0].name, input.files[0]);
        }
      });
      input.click();
    }
  }


  // ── Utilities ─────────────────────────────────────────────────────────────

  function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function _date(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000)     return 'just now';
    if (diff < 3600000)   return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000)  return Math.floor(diff / 3600000) + 'h ago';
    if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';
    return d.toLocaleDateString();
  }

  function _showError(el, msg) {
    if (!el) return;
    el.textContent   = msg;
    el.style.display = 'block';
  }


  // ── Public API ────────────────────────────────────────────────────────────

  return {
    init,
    loadProjects,
    loadHistory,
    selectProject,
    selectNoProject,
    switchMode,
    openNewProjectPanel,
    closeNewProjectPanel,
    createProject,
    openProjectSettings,
    closeProjectSettings,
    saveProjectSettings,
    indexActiveProject,
    deleteActiveProject,
    toggleWriteAccess,
    toggleProjectHistory,
    openFileBrowser,
    openFolderPicker,
    onPathInput,
    clearAllHistory,
    deleteSession,
    _openHistorySession,
    get activeProjectId() { return _activeProjectId; },
    get activeProject()   { return _activeProject; },
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSidebar.init());
