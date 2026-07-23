/**
 * Lincoln Sidebar  v0.7.0  Navigator
 * ======================================
 * Changes from v0.6.0:
 *   - Project settings panel fully implemented (was a stub calling window._openProjectSettingsPanel).
 *     Full tabbed controller: Settings / Context / Files — all in this module.
 *   - Settings tab: path editing, write toggle, index status — was partially wired, now complete.
 *   - Context tab: per-project instructions textarea. Loads from GET /api/projects/<id>/context,
 *     saves to POST /api/projects/<id>/context. Dirty-state guard on close.
 *   - Files tab: lists all files in the RAG source folder with size, RAG badge, and delete button.
 *     DELETE /api/projects/<id>/files removes file from disk and auto-triggers re-index.
 *   - launchAider() added (was called from HTML but never existed in this module).
 *   - All new functions exposed in public API return object.
 *
 * Changes from v0.5.x:
 *   - Multi-select on history: checkboxes, shift+click range, ctrl+A, Escape clears
 *   - Selection toolbar: count badge, Delete selected, Select all, Clear
 *   - Memory panel: full list view with timestamps, tags, checkboxes, delete buttons
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
    _setupSidebarResize();
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
      // When a project is active, only fetch chats assigned to that project.
      // This fixes the leak where general-history chats appeared inside projects.
      const url = _activeProjectId
        ? `/api/history?project_id=${_activeProjectId}`
        : '/api/history';
      const res      = await fetch(url);
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
      list.innerHTML = _activeProjectId
        ? `<div class="sidebar-empty-state">No chats in this project yet.</div>`
        : '<div class="sidebar-empty-state">No history yet.</div>';
      _renderHistoryToolbar(0, 0);
      return;
    }

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
              onclick="lincolnSidebar._onHistoryCheckbox(event, ${s.id}, ${idx})">
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

    if (_activeProjectId) {
      // Filtered mode — only this project's sessions are returned by the API.
      // Render them all directly without any further grouping.
      sessions.forEach(s => { html += _sessionHTML(s, itemIndex++); });
    } else {
      // No project active — general history view with optional project grouping.
      const projectSessions = sessions.filter(s => s.project_id === _activeProjectId && _activeProjectId);
      const generalSessions = sessions.filter(s => !s.project_id);
      const otherSessions   = sessions.filter(s => s.project_id && s.project_id !== _activeProjectId);

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
    }

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
    if (event.target.closest('.history-checkbox-wrap') ||
        event.target.closest('.history-delete-btn')) return;

    if (event.shiftKey && _lastClickedIdx !== null) {
      _selectHistoryRange(_lastClickedIdx, itemIndex);
    } else if (!event.ctrlKey && !event.metaKey) {
      if (_historySelected.size === 0) {
        _lastClickedIdx = itemIndex; // <-- ADD THIS so it remembers the click index
        _openHistorySession(sessionId);
        return;
      }
      _toggleHistoryItem(sessionId);
    } else {
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

    let html = '';

    // "No Project" deselect row — only shown when a project is active
    if (_activeProjectId) {
      html += `
        <div class="sidebar-project-item no-project-item" id="exitProjectBtn"
             onclick="lincolnSidebar.exitProject()" title="Exit project — return to general chat">
          <div class="project-dot"></div>
          <div class="project-info">
            <div class="project-name" style="color:var(--text-muted)">No project</div>
          </div>
          <i class="ti ti-x" style="font-size:12px;color:var(--text-muted)"></i>
        </div>
      `;
    }

    if (!projects.length) {
      html += '<div class="sidebar-empty-state">No projects yet.</div>';
    } else {
      html += projects.map(p => `
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

    list.innerHTML = html;
  }

  async function selectProject(projectId) {
    try {
      const res     = await fetch(`/api/projects`);
      const projects = await res.json();
      const project  = projects.find(p => p.id === projectId);
      if (!project) return;

      _activeProjectId = projectId;
      _activeProject   = project;

      // Re-render project list to show/update the "No Project" exit button
      _renderProjects(projects);

      if (typeof lincolnChat !== 'undefined') {
        lincolnChat.setActiveProject(projectId, project);
        lincolnChat.showProjectHome(project);
      }

      await loadHistory();
    } catch (err) {
      console.error('Select project error:', err);
    }
  }

  // ── Exit / deselect project ───────────────────────────────────────────────

  async function exitProject() {
    _activeProjectId = null;
    _activeProject   = null;

    // Deactivate all project items in sidebar
    document.querySelectorAll('.sidebar-project-item').forEach(el => {
      el.classList.remove('active');
    });
    document.querySelectorAll('.project-dot').forEach(dot => {
      dot.classList.remove('active');
    });
    // Hide the exit button itself
    document.getElementById('exitProjectBtn')?.style.setProperty('display', 'none');

    if (typeof lincolnChat !== 'undefined') {
      lincolnChat.clearActiveProject();
      lincolnChat.newSession();
    }

    await loadHistory();
  }

  // ── Sidebar fold toggle ───────────────────────────────────────────────────

  let _sidebarCollapsed = false;

  function toggleSidebarFold() {
    _sidebarCollapsed = !_sidebarCollapsed;
    const sidebar = document.getElementById('lincolnSidebar');
    const btn     = document.getElementById('sidebarFoldBtn');
    const main    = document.getElementById('lincolnMain');

    if (!sidebar) return;

    if (_sidebarCollapsed) {
      sidebar.style.width    = '36px';
      sidebar.style.minWidth = '36px';
      sidebar.style.overflow = 'hidden';
      // Hide all children except the fold button itself
      sidebar.querySelectorAll(':scope > *:not(#sidebarFoldBtnRow)').forEach(el => {
        el.style.display = 'none';
      });
      if (btn) btn.textContent = '▶';
      if (btn) btn.title = 'Expand sidebar';
    } else {
      sidebar.style.width    = '';
      sidebar.style.minWidth = '';
      sidebar.style.overflow = '';
      sidebar.querySelectorAll(':scope > *').forEach(el => {
        el.style.display = '';
      });
      if (btn) btn.textContent = '◀';
      if (btn) btn.title = 'Collapse sidebar';
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

  // ── Project settings panel (v0.7.0 — tabbed: Settings / Context / Files) ──

  let _editingProjectId  = null;
  let _editingWriteEnabled = false;
  let _activeProjTab     = 'settings';
  let _contextDirty      = false;

  function openProjectSettings(projectId) {
    _editingProjectId  = projectId;
    _activeProjTab     = 'settings';
    _contextDirty      = false;

    const overlay = document.getElementById('projectSettingsOverlay');
    if (overlay) overlay.style.display = 'flex';

    _switchProjTab('settings');
    _loadProjectSettingsData(projectId);
  }

  function closeProjectSettings() {
    if (_contextDirty) {
      if (!confirm('You have unsaved context changes. Discard them?')) return;
    }
    const overlay = document.getElementById('projectSettingsOverlay');
    if (overlay) overlay.style.display = 'none';
    _editingProjectId = null;
    _contextDirty     = false;
  }

  function _switchProjTab(tab) {
    _activeProjTab = tab;

    // Tab buttons
    ['settings', 'context', 'files'].forEach(t => {
      const btn = document.getElementById('projTab' + t.charAt(0).toUpperCase() + t.slice(1));
      if (!btn) return;
      const isActive = t === tab;
      btn.style.color        = isActive ? 'var(--text-primary)' : 'var(--text-muted)';
      btn.style.borderBottom = isActive ? '2px solid var(--accent)' : '2px solid transparent';
      btn.style.fontWeight   = isActive ? '600' : '500';
    });

    // Panes
    const panes = { settings: 'projPaneSettings', context: 'projPaneContext', files: 'projPaneFiles' };
    Object.entries(panes).forEach(([t, id]) => {
      const el = document.getElementById(id);
      if (el) el.style.display = t === tab ? 'flex' : 'none';
      if (el && t === tab) el.style.flexDirection = 'column';
    });

    // Footer right buttons — swap per tab
    const footerRight = document.getElementById('projSettingsFooterRight');
    if (footerRight) {
      if (tab === 'settings') {
        footerRight.innerHTML = `
          <button class="panel-btn-secondary" onclick="lincolnSidebar.closeProjectSettings()">Cancel</button>
          <button class="panel-btn-primary"   onclick="lincolnSidebar.saveProjectSettings()">Save</button>
          <button class="panel-btn-confirm" id="projectIndexBtn" onclick="lincolnSidebar.indexActiveProject()">
            <i class="ti ti-refresh"></i> Index now
          </button>`;
      } else if (tab === 'context') {
        footerRight.innerHTML = `
          <button class="panel-btn-secondary" onclick="lincolnSidebar.closeProjectSettings()">Close</button>
          <button class="panel-btn-confirm"   onclick="lincolnSidebar._saveProjectContext()">
            <i class="ti ti-device-floppy"></i> Save context
          </button>`;
      } else if (tab === 'files') {
        footerRight.innerHTML = `
          <button class="panel-btn-secondary" onclick="lincolnSidebar.closeProjectSettings()">Close</button>`;
      }
    }

    // Lazy-load per tab
    if (tab === 'context' && _editingProjectId) _loadProjectContext(_editingProjectId);
    if (tab === 'files'   && _editingProjectId) _loadProjectFiles(_editingProjectId);
  }

  async function _loadProjectSettingsData(projectId) {
    try {
      const [projRes, statusRes] = await Promise.all([
        fetch(`/api/projects`),
        fetch(`/api/projects/${projectId}/status`),
      ]);
      const projects = await projRes.json();
      const project  = projects.find(p => p.id === projectId);
      const status   = await statusRes.json();

      if (!project) return;

      // Populate title
      const title = document.getElementById('projectSettingsTitle');
      if (title) title.textContent = project.display_name + ' — settings';

      // Populate paths
      const pathEl = document.getElementById('projSettingsPath');
      if (pathEl) pathEl.value = project.path || '';

      const codePathEl = document.getElementById('projSettingsCodePath');
      if (codePathEl) codePathEl.value = project.code_path || '';

      // Write toggle
      _editingWriteEnabled = !!project.write_enabled;
      _updateWriteToggle();

      // Index status
      const statusEl = document.getElementById('projectIndexStatus');
      if (statusEl) {
        const vectors = project.vector_count || 0;
        const indexed = project.last_indexed
          ? new Date(project.last_indexed).toLocaleString()
          : 'Never';
        const statusColor = status.status === 'running'
          ? 'var(--text-accent)'
          : vectors > 0 ? 'var(--text-success)' : 'var(--text-muted)';
        statusEl.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="color:${statusColor};font-weight:500">
              ${status.status === 'running' ? '⟳ Indexing…' : vectors > 0 ? '✓ Indexed' : 'Not indexed'}
            </span>
            <span style="color:var(--text-muted)">${vectors.toLocaleString()} vectors</span>
          </div>
          <div style="color:var(--text-muted);margin-top:3px">Last indexed: ${indexed}</div>
          ${status.message ? `<div style="margin-top:3px">${_esc(status.message)}</div>` : ''}
        `;
      }
    } catch (err) {
      console.error('Load project settings error:', err);
    }
  }

  function _updateWriteToggle() {
    const btn = document.getElementById('writeToggleBtn');
    const warn = document.getElementById('writeAccessWarning');
    if (btn) {
      btn.textContent  = _editingWriteEnabled ? 'On — write enabled' : 'Off — read only';
      btn.style.color  = _editingWriteEnabled ? 'var(--text-danger)' : 'var(--text-secondary)';
      btn.style.borderColor = _editingWriteEnabled ? 'var(--text-danger)' : 'var(--border)';
    }
    if (warn) warn.style.display = _editingWriteEnabled ? 'flex' : 'none';
  }

  function toggleWriteAccess() {
    _editingWriteEnabled = !_editingWriteEnabled;
    _updateWriteToggle();
  }

  async function saveProjectSettings() {
    if (!_editingProjectId) return;
    const path      = document.getElementById('projSettingsPath')?.value.trim()     || '.';
    const code_path = document.getElementById('projSettingsCodePath')?.value.trim() || null;
    const errEl     = document.getElementById('projectSettingsError');
    if (errEl) errEl.style.display = 'none';

    try {
      const res = await fetch(`/api/projects/${_editingProjectId}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ path, code_path, write_enabled: _editingWriteEnabled }),
      });
      if (!res.ok) {
        const data = await res.json();
        if (errEl) { errEl.textContent = data.error || 'Save failed'; errEl.style.display = 'block'; }
        return;
      }
      lincolnChat?.showToast?.('Project settings saved', 'success');
      await loadProjects();
    } catch (err) {
      if (errEl) { errEl.textContent = err.message; errEl.style.display = 'block'; }
    }
  }

  async function deleteActiveProject() {
    if (!_editingProjectId) return;
    if (!confirm('Delete this project? Chats will be unlinked. The index will be wiped.')) return;
    try {
      await fetch(`/api/projects/${_editingProjectId}?wipe_index=true`, { method: 'DELETE' });
      closeProjectSettings();
      await loadProjects();
      lincolnChat?.showToast?.('Project deleted', 'info');
    } catch (err) {
      console.error('Delete project error:', err);
    }
  }

  async function indexActiveProject() {
    if (!_editingProjectId) return;
    const btn = document.getElementById('projectIndexBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ti ti-refresh"></i> Indexing…'; }
    try {
      await fetch(`/api/projects/${_editingProjectId}/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_rebuild: true }),
      });
      startIndexPoll(_editingProjectId);
      lincolnChat?.showToast?.('Index started', 'info');
    } catch (err) {
      lincolnChat?.showToast?.(`Index error: ${err.message}`, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ti ti-refresh"></i> Index now'; }
    }
  }

  function onPathInput(inputId, resolvedId) {
    const val = document.getElementById(inputId)?.value.trim() || '';
    const el  = document.getElementById(resolvedId);
    if (el) el.textContent = val ? 'Path set: ' + val : '';
  }

  function openFolderPicker(inputId, resolvedId) {
    _nativeFolderPick(inputId);
  }

  // ── Context tab ───────────────────────────────────────────────────────────

  async function _loadProjectContext(projectId) {
    const ta     = document.getElementById('projContextTextarea');
    const status = document.getElementById('projContextSaveStatus');
    if (!ta) return;
    if (status) status.textContent = 'Loading…';
    try {
      const res  = await fetch(`/api/projects/${projectId}/context`);
      const data = await res.json();
      ta.value      = data.context || '';
      _contextDirty = false;
      if (status) status.textContent = '';
    } catch (err) {
      if (status) status.textContent = 'Failed to load context';
    }
  }

  function _markContextDirty() {
    _contextDirty = true;
    const status = document.getElementById('projContextSaveStatus');
    if (status) status.textContent = 'Unsaved changes';
  }

  async function _saveProjectContext() {
    if (!_editingProjectId) return;
    const ta     = document.getElementById('projContextTextarea');
    const status = document.getElementById('projContextSaveStatus');
    const text   = ta?.value || '';
    if (status) status.textContent = 'Saving…';
    try {
      const res = await fetch(`/api/projects/${_editingProjectId}/context`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ context: text }),
      });
      if (!res.ok) throw new Error('Save failed');
      _contextDirty = false;
      if (status) status.textContent = 'Saved ✓';
      setTimeout(() => { if (status) status.textContent = ''; }, 2500);
      lincolnChat?.showToast?.('Project context saved', 'success');
    } catch (err) {
      if (status) status.textContent = 'Error: ' + err.message;
    }
  }

  // ── Files tab ─────────────────────────────────────────────────────────────

  async function _loadProjectFiles(projectId) {
    const list    = document.getElementById('projFilesList');
    const countEl = document.getElementById('projFilesCount');
    if (!list) return;
    if (countEl) countEl.textContent = 'Loading files…';
    list.innerHTML = '<div style="padding:16px;font-size:12px;color:var(--text-muted)">Loading…</div>';

    try {
      const res  = await fetch(`/api/projects/${projectId}/files`);
      const data = await res.json();
      if (!res.ok) {
        list.innerHTML = `<div style="padding:16px;font-size:12px;color:var(--text-danger)">${_esc(data.error)}</div>`;
        return;
      }
      const files = data.files || [];
      if (countEl) countEl.textContent = `${files.length} file${files.length !== 1 ? 's' : ''} in RAG source folder`;

      if (!files.length) {
        list.innerHTML = '<div style="padding:16px;font-size:12px;color:var(--text-muted)">No files found. Set the RAG source folder in the Settings tab first.</div>';
        return;
      }

      list.innerHTML = files.map(f => `
        <div class="proj-file-row" style="display:flex;align-items:center;gap:8px;padding:7px 14px;border-bottom:0.5px solid var(--border);font-size:12px">
          <i class="ti ti-${f.is_indexable ? 'file-code' : 'file'}"
             style="font-size:13px;color:${f.is_indexable ? 'var(--text-accent)' : 'var(--text-muted)'};flex-shrink:0"></i>
          <div style="flex:1;min-width:0">
            <div style="font-weight:500;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
                 title="${_esc(f.relative_path)}">${_esc(f.name)}</div>
            <div style="color:var(--text-muted);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
                 title="${_esc(f.relative_path)}">${_esc(f.relative_path)}</div>
          </div>
          <span style="color:var(--text-muted);flex-shrink:0;font-size:11px">${f.size_kb} KB</span>
          <span style="color:${f.is_indexable ? 'var(--text-success)' : 'var(--text-muted)'};flex-shrink:0;font-size:10px;font-weight:500"
                title="${f.is_indexable ? 'Will be indexed by RAG' : 'Not indexed'}">
            ${f.is_indexable ? 'RAG' : '—'}
          </span>
          <button onclick="lincolnSidebar._deleteProjectFile('${_esc(f.relative_path)}')"
                  title="Delete this file from project folder"
                  style="flex-shrink:0;border:none;background:none;cursor:pointer;color:var(--text-muted);padding:2px 4px;border-radius:3px"
                  onmouseover="this.style.color='var(--text-danger)'"
                  onmouseout="this.style.color='var(--text-muted)'">
            <i class="ti ti-trash" style="font-size:13px"></i>
          </button>
        </div>
      `).join('');

    } catch (err) {
      list.innerHTML = `<div style="padding:16px;font-size:12px;color:var(--text-danger)">Error: ${_esc(err.message)}</div>`;
    }
  }

  async function _deleteProjectFile(relativePath) {
    if (!_editingProjectId) return;
    if (!confirm(`Delete "${relativePath}" from the project folder?\n\nThis permanently removes the file from disk and triggers a re-index.`)) return;

    try {
      const res = await fetch(`/api/projects/${_editingProjectId}/files`, {
        method:  'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ relative_path: relativePath }),
      });
      const data = await res.json();
      if (!res.ok) {
        lincolnChat?.showToast?.(`Delete failed: ${data.error}`, 'error');
        return;
      }
      lincolnChat?.showToast?.(`Deleted ${relativePath} — re-indexing…`, 'success');
      // Reload file list and start polling
      await _loadProjectFiles(_editingProjectId);
      startIndexPoll(_editingProjectId);
    } catch (err) {
      lincolnChat?.showToast?.(`Error: ${err.message}`, 'error');
    }
  }

  // Expose _loadProjectFiles publicly so the refresh button in HTML can call it
  function _loadProjectFilesPublic() {
    if (_editingProjectId) _loadProjectFiles(_editingProjectId);
  }

  // ── Aider launcher ────────────────────────────────────────────────────────

  async function launchAider() {
    const projectId = _activeProjectId;
    if (!projectId) {
      lincolnChat?.showToast?.('Select a project first', 'info');
      return;
    }
    try {
      const res  = await fetch(`/api/projects/${projectId}/aider`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        lincolnChat?.showToast?.(`Aider error: ${data.error}`, 'error');
      } else {
        lincolnChat?.showToast?.(data.message || 'Aider launched', 'success');
      }
    } catch (err) {
      lincolnChat?.showToast?.(`Aider error: ${err.message}`, 'error');
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

  // ── Sidebar drag-to-resize ────────────────────────────────────────────────

  function _setupSidebarResize() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    // Create drag handle and inject it
    const handle = document.createElement('div');
    handle.id        = 'sidebarResizeHandle';
    handle.className = 'sidebar-resize-handle';
    handle.title     = 'Drag to resize sidebar';
    sidebar.appendChild(handle);

    let dragging   = false;
    let startX     = 0;
    let startWidth = 0;
    const MIN_W    = 180;
    const MAX_W    = 520;

    handle.addEventListener('mousedown', (e) => {
      dragging   = true;
      startX     = e.clientX;
      startWidth = sidebar.getBoundingClientRect().width;
      document.body.style.cursor      = 'col-resize';
      document.body.style.userSelect  = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const delta    = e.clientX - startX;
      const newWidth = Math.min(MAX_W, Math.max(MIN_W, startWidth + delta));
      sidebar.style.width = newWidth + 'px';
    });

    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';
      // Persist width to localStorage so it survives reload
      try { localStorage.setItem('lincoln_sidebar_width', sidebar.style.width); } catch (_) {}
    });

    // Restore saved width on load
    try {
      const saved = localStorage.getItem('lincoln_sidebar_width');
      if (saved) sidebar.style.width = saved;
    } catch (_) {}
  }

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
    closeProjectSettings,
    saveProjectSettings,
    deleteActiveProject,
    indexActiveProject,
    toggleWriteAccess,
    onPathInput,
    openFolderPicker,
    _switchProjTab,
    _markContextDirty,
    _saveProjectContext,
    _loadProjectFiles: _loadProjectFilesPublic,
    _deleteProjectFile,
    openFileBrowser,
    launchAider,
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
    exitProject,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSidebar.init());