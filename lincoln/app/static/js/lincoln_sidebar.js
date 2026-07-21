/**
 * Lincoln Sidebar  v0.6.0  Navigator
 * ======================================
 * Changes from v0.5.x:
 *   - Multi-select on history: checkboxes, shift+click range, ctrl+A, Escape clears
 *   - Selection toolbar: count badge, Delete selected, Select all, Clear
 *   - DELETE /api/history/selected bulk delete (new route)
 *   - DELETE /api/history/all now correctly hits the new route
 *   - Memory panel: full list view with timestamps, tags, checkboxes, delete buttons
 *   - Memory multi-select: same pattern as history
 *   - Persist sidebar_show_project_chats to DB on toggle
 *   - hasSelection() and clearSelection() exposed for global Escape handler
 */

const lincolnSidebar = (() => {

  let _activeProjectId = null;
  let _activeProject   = null;
  let _activeMode      = 'chat';
  let _showProjectChats = false;

  // Multi-select state
  let _historySelected  = new Set();  // selected session ids
  let _lastClickedIdx   = null;       // for shift+click range
  let _memorySelected   = new Set();  // selected memory entry ids

  // ── Init ──────────────────────────────────────────────────────────────────

  async function init() {
    await _loadShowProjectChats();
    await loadHistory();
    await loadProjects();
    _setupKeyboardShortcuts();
  }

  async function _loadShowProjectChats() {
    try {
      const res  = await fetch('/api/settings');
      const data = await res.json();
      _showProjectChats = (data.ui_settings?.sidebar_show_project_chats === 'true');
      _updateProjectChatsToggle();
    } catch (_) { }
  }

  function _updateProjectChatsToggle() {
    const btn = document.getElementById('projectChatsToggle');
    if (btn) btn.textContent = `project chats: ${_showProjectChats ? 'on' : 'off'}`;
  }

  // ── History ───────────────────────────────────────────────────────────────

  async function loadHistory() {
    try {
      const res      = await fetch('/api/history');
      const sessions = await res.json();
      _renderHistory(sessions);
    } catch (err) {
      console.error('Load history error:', err);
    }
  }

  function _renderHistory(sessions) {
    const list = document.getElementById('historyList');
    if (!list) return;

    if (!sessions.length) {
      list.innerHTML = '<div class="sidebar-empty-state">No history yet.</div>';
      _renderHistoryToolbar(0, 0);
      return;
    }

    const projectSessions = sessions.filter(s => s.project_id === _activeProjectId && _activeProjectId);
    const generalSessions = sessions.filter(s => !s.project_id);
    const otherSessions   = sessions.filter(s => s.project_id && s.project_id !== _activeProjectId);

    let html      = '';
    let allIds    = [];
    let itemIndex = 0;

    function _sessionHTML(s, idx) {
      allIds.push(s.id);
      const checked = _historySelected.has(s.id) ? 'checked' : '';
      return `
        <div class="sidebar-history-item ${_historySelected.has(s.id) ? 'selected' : ''}"
             id="historyItem_${s.id}"
             data-session-id="${s.id}"
             data-item-index="${idx}"
             onclick="lincolnSidebar._onHistoryItemClick(event, ${s.id}, ${idx})">
          <label class="history-checkbox-wrap" onclick="event.stopPropagation()">
            <input type="checkbox" class="history-checkbox"
              ${checked}
              onchange="lincolnSidebar._onHistoryCheckbox(event, ${s.id}, ${idx})">
          </label>
          <div class="history-content" onclick="lincolnSidebar._openHistorySession(${s.id})">
            <div class="history-title">${_esc(s.title)}</div>
            <div class="history-date">${_date(s.updated_at)}</div>
          </div>
          <button class="history-delete-btn" title="Delete chat"
                  onclick="event.stopPropagation(); lincolnSidebar.deleteSession(${s.id})">
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

    if (_showProjectChats && projectSessions.length && _activeProjectId) {
      html += _groupLabel(_activeProject?.display_name || 'Project', projectSessions.length);
      projectSessions.forEach(s => { html += _sessionHTML(s, itemIndex++); });
    }

    if (generalSessions.length) {
      if (html) html += _groupLabel('General', generalSessions.length);
      generalSessions.forEach(s => { html += _sessionHTML(s, itemIndex++); });
    }

    if (_showProjectChats) {
      const otherByProject = {};
      otherSessions.forEach(s => {
        const label = s.project_display_name || 'Other';
        if (!otherByProject[label]) otherByProject[label] = [];
        otherByProject[label].push(s);
      });
      Object.entries(otherByProject).forEach(([label, group]) => {
        html += _groupLabel(label, group.length);
        group.forEach(s => { html += _sessionHTML(s, itemIndex++); });
      });
    }

    if (!html) html = '<div class="sidebar-empty-state">No general chats yet.</div>';

    list.innerHTML = html;
    list.dataset.allIds = JSON.stringify(allIds);
    _renderHistoryToolbar(sessions.length, _historySelected.size);
  }

  // ── History selection toolbar ─────────────────────────────────────────────

  function _renderHistoryToolbar(total, selectedCount) {
    let toolbar = document.getElementById('historySelectionToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id        = 'historySelectionToolbar';
      toolbar.className = 'selection-toolbar';
      const historySection = document.querySelector('.sidebar-history');
      if (historySection) historySection.prepend(toolbar);
    }

    if (selectedCount === 0) {
      toolbar.style.display = 'none';
      return;
    }

    toolbar.style.display = 'flex';
    toolbar.innerHTML = `
      <span class="selection-count">${selectedCount} selected</span>
      <button class="selection-btn" onclick="lincolnSidebar._selectAllHistory()">
        Select all
      </button>
      <button class="selection-btn selection-btn-danger"
        onclick="lincolnSidebar._deleteSelectedHistory()">
        <i class="ti ti-trash"></i> Delete
      </button>
      <button class="selection-btn" onclick="lincolnSidebar.clearSelection()">
        <i class="ti ti-x"></i>
      </button>
    `;
  }

  // ── History item click / checkbox handlers ────────────────────────────────

  function _onHistoryItemClick(event, sessionId, itemIndex) {
    // If clicking the checkbox or delete button, handled elsewhere
    if (event.target.closest('.history-checkbox-wrap') ||
        event.target.closest('.history-delete-btn')) return;

    if (event.shiftKey && _lastClickedIdx !== null) {
      // Shift+click: select range
      _selectHistoryRange(_lastClickedIdx, itemIndex);
    } else if (!event.ctrlKey && !event.metaKey) {
      // Plain click with no selection active: open session
      if (_historySelected.size === 0) {
        _openHistorySession(sessionId);
        return;
      }
      // If in selection mode, treat as toggle
      _toggleHistoryItem(sessionId);
    } else {
      // Ctrl+click: toggle
      _toggleHistoryItem(sessionId);
    }
    _lastClickedIdx = itemIndex;
    _syncHistoryCheckboxes();
    _renderHistoryToolbar(0, _historySelected.size);
  }

  function _onHistoryCheckbox(event, sessionId, itemIndex) {
    event.stopPropagation();
    if (event.shiftKey && _lastClickedIdx !== null) {
      _selectHistoryRange(_lastClickedIdx, itemIndex);
    } else {
      _toggleHistoryItem(sessionId);
    }
    _lastClickedIdx = itemIndex;
    _syncHistoryCheckboxes();
    _renderHistoryToolbar(0, _historySelected.size);
  }

  function _toggleHistoryItem(sessionId) {
    if (_historySelected.has(sessionId)) {
      _historySelected.delete(sessionId);
    } else {
      _historySelected.add(sessionId);
    }
  }

  function _selectHistoryRange(fromIdx, toIdx) {
    const list = document.getElementById('historyList');
    if (!list) return;
    const items = [...list.querySelectorAll('[data-item-index]')];
    const min   = Math.min(fromIdx, toIdx);
    const max   = Math.max(fromIdx, toIdx);
    items.forEach(item => {
      const idx = parseInt(item.dataset.itemIndex, 10);
      if (idx >= min && idx <= max) {
        const sid = parseInt(item.dataset.sessionId, 10);
        _historySelected.add(sid);
      }
    });
  }

  function _selectAllHistory() {
    const list = document.getElementById('historyList');
    if (!list) return;
    const allIds = JSON.parse(list.dataset.allIds || '[]');
    allIds.forEach(id => _historySelected.add(id));
    _syncHistoryCheckboxes();
    _renderHistoryToolbar(0, _historySelected.size);
  }

  function _syncHistoryCheckboxes() {
    document.querySelectorAll('.sidebar-history-item').forEach(item => {
      const sid      = parseInt(item.dataset.sessionId, 10);
      const cb       = item.querySelector('.history-checkbox');
      const selected = _historySelected.has(sid);
      if (cb) cb.checked = selected;
      item.classList.toggle('selected', selected);
    });
  }

  function hasSelection() {
    return _historySelected.size > 0 || _memorySelected.size > 0;
  }

  function clearSelection() {
    _historySelected.clear();
    _memorySelected.clear();
    _lastClickedIdx = null;
    _syncHistoryCheckboxes();
    _renderHistoryToolbar(0, 0);
    _syncMemoryCheckboxes();
    _renderMemoryToolbar(0, 0);
  }

  async function _deleteSelectedHistory() {
    const ids = [..._historySelected];
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} selected chat${ids.length !== 1 ? 's' : ''}? This cannot be undone.`)) return;
    try {
      await fetch('/api/history/selected', {
        method:  'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ ids }),
      });
      ids.forEach(id => document.getElementById(`historyItem_${id}`)?.remove());
      _historySelected.clear();
      _renderHistoryToolbar(0, 0);
    } catch (err) {
      console.error('Bulk delete error:', err);
    }
  }

  async function clearAllHistory() {
    if (!confirm('Delete all chat history? This cannot be undone.')) return;
    try {
      await fetch('/api/history/all', { method: 'DELETE' });
      _historySelected.clear();
      await loadHistory();
    } catch (err) {
      console.error('Clear all history error:', err);
    }
  }

  async function deleteSession(sessionId) {
    if (!confirm('Delete this chat? This cannot be undone.')) return;
    try {
      await fetch(`/api/history/${sessionId}`, { method: 'DELETE' });
      document.getElementById(`historyItem_${sessionId}`)?.remove();
      _historySelected.delete(sessionId);
      _renderHistoryToolbar(0, _historySelected.size);
    } catch (err) {
      console.error('Delete session error:', err);
    }
  }

  function _openHistorySession(sessionId) {
    switchMode('chat');
    document.getElementById('projectHome')?.remove();
    document.getElementById('lincolnWelcome')?.remove();
    if (typeof lincolnCanvasUI !== 'undefined') lincolnCanvasUI.show();
    setTimeout(() => lincolnChat.loadSession(sessionId), 0);
  }

  // ── Keyboard shortcuts ────────────────────────────────────────────────────

  function _setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl+A to select all history when sidebar has focus
      if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        const historyList = document.getElementById('historyList');
        if (historyList && document.activeElement?.closest('#historyList')) {
          e.preventDefault();
          _selectAllHistory();
        }
      }

      // Delete key to delete selected items
      if (e.key === 'Delete' && !e.ctrlKey) {
        if (_historySelected.size > 0 &&
            document.activeElement?.closest('#historyList')) {
          _deleteSelectedHistory();
        }
        if (_memorySelected.size > 0 &&
            document.activeElement?.closest('#memoryList')) {
          _deleteSelectedMemory();
        }
      }
    });
  }

  // ── Memory panel ──────────────────────────────────────────────────────────

  async function loadMemory() {
    const list = document.getElementById('memoryList');
    if (!list) return;
    try {
      const res     = await fetch('/api/history/memory');
      const entries = await res.json();
      _renderMemory(entries);
    } catch (err) {
      list.innerHTML = '<div class="sidebar-empty-state">Could not load memory entries.</div>';
    }
  }

  function _renderMemory(entries) {
    const list = document.getElementById('memoryList');
    if (!list) return;

    if (!entries.length) {
      list.innerHTML = `
        <div class="sidebar-empty-state">
          No saved memories yet.<br>
          Use the <strong>Save session</strong> button after a chat to create one.
        </div>`;
      _renderMemoryToolbar(0, 0);
      return;
    }

    list.innerHTML = entries.map((entry, idx) => {
      const checked = _memorySelected.has(entry.id) ? 'checked' : '';
      const tag     = entry.tag ? `<span class="memory-tag">${_esc(entry.tag)}</span>` : '';
      const project = entry.project_display_name
        ? `<span class="memory-project">${_esc(entry.project_display_name)}</span>` : '';
      return `
        <div class="memory-entry ${_memorySelected.has(entry.id) ? 'selected' : ''}"
             id="memoryEntry_${entry.id}"
             data-memory-id="${entry.id}"
             data-item-index="${idx}">
          <label class="history-checkbox-wrap" onclick="event.stopPropagation()">
            <input type="checkbox" class="history-checkbox"
              ${checked}
              onchange="lincolnSidebar._onMemoryCheckbox(event, ${entry.id}, ${idx})">
          </label>
          <div class="memory-content">
            <div class="memory-meta">
              <span class="memory-date">${_date(entry.created_at)}</span>
              ${tag}${project}
            </div>
            <div class="memory-text">${_esc(entry.content)}</div>
          </div>
          <button class="history-delete-btn" title="Delete memory"
                  onclick="event.stopPropagation(); lincolnSidebar.deleteMemoryEntry(${entry.id})">
            <i class="ti ti-trash"></i>
          </button>
        </div>
      `;
    }).join('');

    _renderMemoryToolbar(entries.length, _memorySelected.size);
  }

  function _renderMemoryToolbar(total, selectedCount) {
    let toolbar = document.getElementById('memorySelectionToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id        = 'memorySelectionToolbar';
      toolbar.className = 'selection-toolbar';
      const memSection = document.getElementById('memoryView');
      if (memSection) memSection.prepend(toolbar);
    }

    if (selectedCount === 0) {
      toolbar.style.display = 'none';
      return;
    }

    toolbar.style.display = 'flex';
    toolbar.innerHTML = `
      <span class="selection-count">${selectedCount} selected</span>
      <button class="selection-btn selection-btn-danger"
        onclick="lincolnSidebar._deleteSelectedMemory()">
        <i class="ti ti-trash"></i> Delete
      </button>
      <button class="selection-btn" onclick="lincolnSidebar.clearSelection()">
        <i class="ti ti-x"></i>
      </button>
    `;
  }

  function _onMemoryCheckbox(event, entryId, idx) {
    if (_memorySelected.has(entryId)) {
      _memorySelected.delete(entryId);
    } else {
      _memorySelected.add(entryId);
    }
    _syncMemoryCheckboxes();
    _renderMemoryToolbar(0, _memorySelected.size);
  }

  function _syncMemoryCheckboxes() {
    document.querySelectorAll('.memory-entry').forEach(item => {
      const eid      = parseInt(item.dataset.memoryId, 10);
      const cb       = item.querySelector('.history-checkbox');
      const selected = _memorySelected.has(eid);
      if (cb) cb.checked = selected;
      item.classList.toggle('selected', selected);
    });
  }

  async function deleteMemoryEntry(entryId) {
    if (!confirm('Delete this memory entry?')) return;
    try {
      await fetch(`/api/history/memory/${entryId}`, { method: 'DELETE' });
      document.getElementById(`memoryEntry_${entryId}`)?.remove();
      _memorySelected.delete(entryId);
      _renderMemoryToolbar(0, _memorySelected.size);
    } catch (err) {
      console.error('Delete memory error:', err);
    }
  }

  async function _deleteSelectedMemory() {
    const ids = [..._memorySelected];
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} memory entr${ids.length !== 1 ? 'ies' : 'y'}?`)) return;
    try {
      await fetch('/api/history/memory/selected', {
        method:  'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ ids }),
      });
      ids.forEach(id => document.getElementById(`memoryEntry_${id}`)?.remove());
      _memorySelected.clear();
      _renderMemoryToolbar(0, 0);
    } catch (err) {
      console.error('Bulk memory delete error:', err);
    }
  }

  async function clearAllMemory() {
    if (!confirm('Delete all saved memories? This cannot be undone.')) return;
    try {
      await fetch('/api/history/memory/all', { method: 'DELETE' });
      _memorySelected.clear();
      await loadMemory();
    } catch (err) {
      console.error('Clear all memory error:', err);
    }
  }

  // ── Projects ──────────────────────────────────────────────────────────────

  async function loadProjects() {
    try {
      const res      = await fetch('/api/projects');
      const projects = await res.json();
      _renderProjects(projects);
    } catch (err) {
      console.error('Load projects error:', err);
    }
  }

  function _renderProjects(projects) {
    const list = document.getElementById('projectList');
    if (!list) return;
    if (!projects.length) {
      list.innerHTML = '<div class="sidebar-empty-state">No projects yet.</div>';
      return;
    }
    list.innerHTML = projects.map(p => `
      <div class="sidebar-project-item ${p.id === _activeProjectId ? 'active' : ''}"
           id="projectItem_${p.id}"
           onclick="lincolnSidebar.selectProject(${p.id})">
        <div class="project-dot ${p.id === _activeProjectId ? 'active' : ''}"></div>
        <div class="project-info">
          <div class="project-name">${_esc(p.display_name)}</div>
          <div class="project-meta">${p.vector_count?.toLocaleString() || 0} vectors</div>
        </div>
        <button class="project-settings-btn" title="Project settings"
                onclick="event.stopPropagation(); lincolnSidebar.openProjectSettings(${p.id})">
          <i class="ti ti-settings"></i>
        </button>
      </div>
    `).join('');
  }

  async function selectProject(projectId) {
    try {
      const res     = await fetch(`/api/projects`);
      const projects = await res.json();
      const project  = projects.find(p => p.id === projectId);
      if (!project) return;

      _activeProjectId = projectId;
      _activeProject   = project;

      document.querySelectorAll('.sidebar-project-item').forEach(el => {
        el.classList.toggle('active', el.id === `projectItem_${projectId}`);
      });
      document.querySelectorAll('.project-dot').forEach((dot, i) => {
        dot.classList.toggle('active', i === projects.findIndex(p => p.id === projectId));
      });

      if (typeof lincolnChat !== 'undefined') {
        lincolnChat.setActiveProject(projectId, project);
        lincolnChat.showProjectHome(project);
      }

      await loadHistory();
    } catch (err) {
      console.error('Select project error:', err);
    }
  }

  // ── Project chat toggle ───────────────────────────────────────────────────

  async function toggleProjectChats() {
    _showProjectChats = !_showProjectChats;
    _updateProjectChatsToggle();

    // Persist to DB
    try {
      await fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ sidebar_show_project_chats: _showProjectChats ? 'true' : 'false' }),
      });
    } catch (_) { }

    await loadHistory();
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

    // Load memory entries when switching to memory view
    if (mode === 'memory') loadMemory();
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
    document.getElementById('newProjectOverlay')?.style.setProperty('display', 'none');
  }

  async function createProject() {
    const name    = document.getElementById('newProjectName')?.value.trim();
    const desc    = document.getElementById('newProjectDesc')?.value.trim() || '';
    const errorEl = document.getElementById('newProjectError');

    if (!name) { _showError(errorEl, 'Project name is required.'); return; }

    try {
      const res     = await fetch('/api/projects', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ display_name: name, path: '.', description: desc }),
      });
      const project = await res.json();
      if (!res.ok) { _showError(errorEl, project.error || 'Could not create project.'); return; }
      closeNewProjectPanel();
      await loadProjects();
    } catch (err) {
      _showError(errorEl, err.message);
    }
  }

  // ── Project settings panel ────────────────────────────────────────────────

  function openProjectSettings(projectId) {
    // Implemented in lincoln_index.html event handlers
    if (typeof window._openProjectSettingsPanel === 'function') {
      window._openProjectSettingsPanel(projectId);
    }
  }

  // ── File browser (for file attach) ───────────────────────────────────────

  function openFileBrowser(mode, callback) {
    // Delegate to native file picker for now
    // The sidebar file browser panel can be expanded in a future iteration
    // BUG FIX (B4): callback receives File object from native picker
    const input    = document.createElement('input');
    input.type     = 'file';
    input.onchange = () => {
      if (input.files[0]) callback(input.files[0]);
    };
    input.click();
  }

  // ── Index polling (B1 fix: stops on complete or error) ───────────────────

  let _indexPollTimer = null;

  function startIndexPoll(projectId) {
    if (_indexPollTimer) clearInterval(_indexPollTimer);
    _indexPollTimer = setInterval(async () => {
      try {
        const res  = await fetch(`/api/projects/${projectId}/status`);
        const data = await res.json();

        // BUG FIX (B1): stop on complete OR error, not only on idle
        if (['complete', 'error', 'idle'].includes(data.status)) {
          clearInterval(_indexPollTimer);
          _indexPollTimer = null;

          if (data.status === 'complete') {
            if (typeof lincolnChat !== 'undefined') lincolnChat.showToast?.('Index complete', 'success');
            await loadProjects();
          } else if (data.status === 'error') {
            if (typeof lincolnChat !== 'undefined') lincolnChat.showToast?.(`Index error: ${data.error}`, 'error');
          }
        }
      } catch (_) {
        clearInterval(_indexPollTimer);
        _indexPollTimer = null;
      }
    }, 1500);
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function _date(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr), now = new Date();
    if (now - d < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function _showError(el, msg) {
    if (!el) return;
    el.textContent    = msg;
    el.style.display  = 'block';
  }

  // ── Public API ────────────────────────────────────────────────────────────

  return {
    init,
    loadHistory,
    loadProjects,
    loadMemory,
    clearAllHistory,
    clearAllMemory,
    deleteSession,
    deleteMemoryEntry,
    selectProject,
    toggleProjectChats,
    switchMode,
    openNewProjectPanel,
    closeNewProjectPanel,
    createProject,
    openProjectSettings,
    openFileBrowser,
    startIndexPoll,
    hasSelection,
    clearSelection,
    _openHistorySession,
    _onHistoryItemClick,
    _onHistoryCheckbox,
    _onMemoryCheckbox,
    _deleteSelectedHistory,
    _deleteSelectedMemory,
    _selectAllHistory,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSidebar.init());
