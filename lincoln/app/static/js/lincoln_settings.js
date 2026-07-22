/**
 * Lincoln Settings  v0.7.1
 * ======================================
 * Settings panel -- left-nav tabbed layout, 860px wide.
 *
 * Tabs (left nav):
 *   Appearance      -- theme, font family
 *   Chat            -- history limit, show project chats
 *   Prompts         -- global system prompt blocks (editable textareas)
 *   RAG             -- top-k, snippet chars
 *   Uploads         -- max sizes, retention days
 *   Web Search      -- master toggle, always-on mode
 *   Build Tools     -- nvfortran, f2py, WSL, Maple, oneAPI, Aider
 *   Models          -- Ollama timeout
 *   Infrastructure  -- .env values + version/codename + Google keys + admin actions
 *   Status          -- live system health
 *
 * Admin mode: unlocks Infrastructure fields.
 * Changes require restart for .env values; DB settings take effect immediately.
 */

const lincolnSettings = (() => {

  let _settings    = {};
  let _infra       = {};
  let _adminMode   = false;
  let _fontsLoaded = false;
  let _activeTab   = 'appearance';
  let activeModel  = null;

  // ── Open / close ──────────────────────────────────────────────────────────

  function open() {
    const overlay = document.getElementById('settingsOverlay');
    if (overlay) overlay.style.display = 'flex';
    _load();
  }

  function close() {
    const overlay = document.getElementById('settingsOverlay');
    if (overlay) overlay.style.display = 'none';
  }

  // ── Load all data ─────────────────────────────────────────────────────────

  async function _load() {
    try {
      const [settingsRes, promptsRes] = await Promise.all([
        fetch('/api/settings'),
        fetch('/api/settings/prompts'),
      ]);
      const data = await settingsRes.json();
      _settings  = data.ui_settings || {};
      _infra     = data.infrastructure || {};
      const prompts = await promptsRes.json();

      _renderAll(prompts);
      _loadStatus();
      if (!_fontsLoaded) { _loadFonts(); _fontsLoaded = true; }
      _loadToolPaths();

      // NEW: Update sidebar version badge dynamically from DB
      const versionBadge = document.getElementById('sidebarVersionDisplay');
      if (versionBadge) versionBadge.textContent = 'v' + _v('lincoln_version', '0.7.0');

    } catch (err) {
      console.error('Settings load error:', err);
    }
  }

  function _v(key, fallback = '') {
    return _settings[key] ?? fallback;
  }

  // ── Main render ───────────────────────────────────────────────────────────

  function _renderAll(prompts) {
    const panel = document.getElementById('settingsPanelContent');
    if (!panel) return;

    panel.innerHTML = `
      <div class="settings-layout">
        <nav class="settings-nav">
          ${_navItem('appearance', 'ti-palette',    'Appearance')}
          ${_navItem('chat',       'ti-message',    'Chat')}
          ${_navItem('prompts',    'ti-text',       'Prompts')}
          ${_navItem('rag',        'ti-database',   'RAG')}
          ${_navItem('uploads',    'ti-upload',     'Uploads')}
          ${_navItem('websearch',  'ti-world',      'Web Search')}
          ${_navItem('buildtools', 'ti-terminal-2', 'Build Tools')}
          ${_navItem('models',     'ti-cpu',        'Models')}
          ${_navItem('infra',      'ti-server',     'Infrastructure')}
          ${_navItem('status',     'ti-activity',   'Status')}
        </nav>
        <div class="settings-pane-container">
          <div class="settings-pane" id="pane-appearance">${_sectionAppearance()}</div>
          <div class="settings-pane" id="pane-chat">${_sectionChat()}</div>
          <div class="settings-pane" id="pane-prompts">${_sectionPrompts(prompts)}</div>
          <div class="settings-pane" id="pane-rag">${_sectionRAG()}</div>
          <div class="settings-pane" id="pane-uploads">${_sectionUploads()}</div>
          <div class="settings-pane" id="pane-websearch">${_sectionWebSearch()}</div>
          <div class="settings-pane" id="pane-buildtools">${_sectionBuildTools()}</div>
          <div class="settings-pane" id="pane-models">${_sectionModels()}</div>
          <div class="settings-pane" id="pane-infra">${_sectionInfrastructure()}</div>
          <div class="settings-pane" id="pane-status">${_sectionStatus()}</div>
        </div>
      </div>
    `;

    _attachListeners();
    _applyAdminMode();
    _switchTab(_activeTab);
  }

  function _navItem(id, icon, label) {
    return `
      <button class="settings-nav-item ${_activeTab === id ? 'active' : ''}"
              id="snav-${id}"
              onclick="lincolnSettings._switchTab('${id}')">
        <i class="ti ${icon}"></i>
        <span>${label}</span>
      </button>
    `;
  }

  function _switchTab(tabId) {
    _activeTab = tabId;
    // Hide all panes
    document.querySelectorAll('.settings-pane').forEach(p => p.style.display = 'none');
    // Show target pane
    const target = document.getElementById(`pane-${tabId}`);
    if (target) target.style.display = 'BLOCK';
    // Update nav active state
    document.querySelectorAll('.settings-nav-item').forEach(btn => btn.classList.remove('active'));
    const navBtn = document.getElementById(`snav-${tabId}`);
    if (navBtn) navBtn.classList.add('active');
  }

  // ── Section: Appearance ───────────────────────────────────────────────────

  function _sectionAppearance() {
    return `
      <h3 class="settings-pane-title">Appearance</h3>
      <div class="settings-field">
        <label class="settings-label">Theme</label>
        <select class="settings-select" data-key="theme">
          <option value="system" ${_v('theme') === 'system' ? 'selected' : ''}>System default</option>
          <option value="dark"   ${_v('theme') === 'dark'   ? 'selected' : ''}>Dark</option>
          <option value="light"  ${_v('theme') === 'light'  ? 'selected' : ''}>Light</option>
        </select>
      </div>
      <div class="settings-field">
        <label class="settings-label">Font family</label>
        <select class="settings-select" id="fontFamilySelect" data-key="ui_font_family">
          <option value="system-ui">System default</option>
        </select>
        <p class="settings-hint">Applied to all Lincoln UI text.</p>
      </div>
    `;
  }

  // ── Section: Chat ─────────────────────────────────────────────────────────

  function _sectionChat() {
    return `
      <h3 class="settings-pane-title">Chat &amp; History</h3>
      <div class="settings-field">
        <label class="settings-label">History limit</label>
        <input class="settings-input" type="number" min="10" max="1000"
          data-key="history_limit" value="${_esc(_v('history_limit', '100'))}">
        <p class="settings-hint">Maximum number of past sessions shown in the sidebar.</p>
      </div>
      <div class="settings-field settings-field-row">
        <label class="settings-label">Show project chats in sidebar by default</label>
        <input type="checkbox" class="settings-checkbox" data-key="sidebar_show_project_chats"
          ${_v('sidebar_show_project_chats') === 'true' ? 'checked' : ''}>
      </div>
    `;
  }

  // ── Section: Prompts & Persona ────────────────────────────────────────────

  function _sectionPrompts(prompts) {
    const promptBlocks = Array.isArray(prompts) ? prompts : [];
    const blocksHtml   = promptBlocks.map(p => _promptBlockHTML(p)).join('');

    return `
      <h3 class="settings-pane-title">Prompts &amp; Persona</h3>
      <p class="settings-hint" style="margin-bottom:12px">
        These instruction blocks define how Lincoln behaves. They are assembled into
        the system prompt on every message, in order. Edit any block freely.
        Project-level instructions are set in each project's Settings → Context tab.
      </p>
      <div id="globalPromptBlocks">
        ${blocksHtml}
      </div>
      <button class="btn-secondary" style="margin-top:8px" onclick="lincolnSettings.addPromptBlock()">
        <i class="ti ti-plus"></i> Add instruction block
      </button>
    `;
  }

  function _promptBlockHTML(p) {
    return `
      <div class="prompt-block" data-prompt-id="${p.id}">
        <div class="prompt-block-header">
          <div class="prompt-drag-handle" title="Drag to reorder">
            <i class="ti ti-grip-vertical"></i>
          </div>
          <input class="prompt-label-input" type="text"
            value="${_esc(p.label)}"
            placeholder="Block label"
            onchange="lincolnSettings._updatePromptField(${p.id}, 'label', this.value)">
          <label class="prompt-toggle-label" title="Enable / disable this block">
            <input type="checkbox" class="prompt-enabled-cb"
              ${p.enabled ? 'checked' : ''}
              onchange="lincolnSettings._updatePromptField(${p.id}, 'enabled', this.checked)">
            <span>Active</span>
          </label>
          <button class="prompt-delete-btn" title="Delete this block"
            onclick="lincolnSettings._deletePromptBlock(${p.id})">
            <i class="ti ti-trash"></i>
          </button>
        </div>
        <textarea class="prompt-content-textarea"
          placeholder="Write your instruction here."
          rows="6"
          onblur="lincolnSettings._updatePromptField(${p.id}, 'content', this.value)"
        >${_esc(p.content)}</textarea>
        <p class="settings-hint">Changes saved when you click outside (on blur).</p>
      </div>
    `;
  }

  async function addPromptBlock() {
    const label   = 'New instruction block';
    const content = 'Enter your instructions here.';
    try {
      const res = await fetch('/api/settings/prompts', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ label, content, enabled: true }),
      });
      if (!res.ok) {
        const err = await res.json();
        console.error('Add prompt block failed:', err);
        return;
      }
      const newPrompt = await res.json();
      const container = document.getElementById('globalPromptBlocks');
      if (container && newPrompt.id) {
        container.insertAdjacentHTML('beforeend', _promptBlockHTML(newPrompt));
      }
    } catch (err) {
      console.error('Add prompt block error:', err);
    }
  }

  async function _updatePromptField(promptId, field, value) {
    try {
      await fetch(`/api/settings/prompts/${promptId}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ [field]: value }),
      });
    } catch (err) {
      console.error('Update prompt field error:', err);
    }
  }

  async function _deletePromptBlock(promptId) {
    if (!confirm('Delete this instruction block? This cannot be undone.')) return;
    try {
      await fetch(`/api/settings/prompts/${promptId}`, { method: 'DELETE' });
      document.querySelector(`[data-prompt-id="${promptId}"]`)?.remove();
    } catch (err) {
      console.error('Delete prompt block error:', err);
    }
  }

  // ── Section: RAG & Index ──────────────────────────────────────────────────

  function _sectionRAG() {
    return `
      <h3 class="settings-pane-title">RAG &amp; Index</h3>
      <div class="settings-field">
        <label class="settings-label">Top-K results</label>
        <input class="settings-input" type="number" min="1" max="20"
          data-key="top_k" value="${_esc(_v('top_k', '5'))}">
        <p class="settings-hint">Number of source chunks retrieved per query.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">Snippet length (characters)</label>
        <input class="settings-input" type="number" min="100" max="2000"
          data-key="rag_snippet_chars" value="${_esc(_v('rag_snippet_chars', '500'))}">
        <p class="settings-hint">
          Length of source code preview shown below RAG results.
          Increase for Fortran/mathematical code with long function signatures.
        </p>
      </div>
    `;
  }

  // ── Section: Uploads ──────────────────────────────────────────────────────

  function _sectionUploads() {
    return `
      <h3 class="settings-pane-title">File Uploads</h3>
      <div class="settings-field">
        <label class="settings-label">Max text / code file size (KB)</label>
        <input class="settings-input" type="number" min="64" max="8192"
          data-key="upload_max_text_kb" value="${_esc(_v('upload_max_text_kb', '512'))}">
        <p class="settings-hint">Applies to .py, .f90, .jl, .r, .tex, and all code files.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">Max document file size (MB)</label>
        <input class="settings-input" type="number" min="1" max="50"
          data-key="upload_max_doc_mb" value="${_esc(_v('upload_max_doc_mb', '2'))}">
        <p class="settings-hint">Applies to PDF, Word (.docx), Excel (.xlsx), and Maple (.mw) files.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">Upload retention (days)</label>
        <input class="settings-input" type="number" min="1" max="365"
          data-key="upload_retention_days" value="${_esc(_v('upload_retention_days', '30'))}">
        <p class="settings-hint">
          Extracted upload files older than this are deleted at startup.
        </p>
      </div>
    `;
  }

  // ── Section: Web Search ───────────────────────────────────────────────────

  function _sectionWebSearch() {
    return `
      <h3 class="settings-pane-title">Web Search</h3>
      <div class="settings-field settings-field-row">
        <label class="settings-label">Enable web search master switch</label>
        <input type="checkbox" class="settings-checkbox" data-key="web_search_enabled"
          ${_v('web_search_enabled') === 'true' ? 'checked' : ''}>
      </div>
      <p class="settings-hint" style="margin-bottom:12px">
        Master switch — must be ON for any web search to fire.
        The globe pill in the input bar toggles search per message.
        Powered by DuckDuckGo (no API key required). Google Custom Search is
        configured as fallback in the Infrastructure tab.
      </p>
      <div class="settings-field settings-field-row">
        <label class="settings-label">Always-on search mode</label>
        <input type="checkbox" class="settings-checkbox" data-key="web_search_always_on"
          ${_v('web_search_always_on') === 'true' ? 'checked' : ''}>
      </div>
      <p class="settings-hint">
        When enabled, the globe pill starts active on every message and does not
        reset after sending. Requires master switch to also be ON.
      </p>
    `;
  }

  // ── Section: Build Tools ──────────────────────────────────────────────────

  function _sectionBuildTools() {
    return `
      <h3 class="settings-pane-title">Build Tools</h3>
      <p class="settings-hint" style="margin-bottom:12px">
        These paths are used when Lincoln generates build advice, launches Aider,
        or constructs WSL commands. Edit them here if your tool locations change.
      </p>
      <div class="settings-field">
        <label class="settings-label">nvfortran path (WSL absolute path)</label>
        <input class="settings-input" type="text"
          data-key="nvfortran_path"
          value="${_esc(_v('nvfortran_path', '/opt/nvidia/hpc_sdk/Linux_x86_64/26.3/compilers/bin/nvfortran'))}"
          placeholder="/opt/nvidia/hpc_sdk/.../nvfortran">
        <p class="settings-hint">NVIDIA HPC SDK Fortran compiler.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">f2py compiler flag</label>
        <input class="settings-input" type="text"
          data-key="f2py_fcompiler_flag" value="${_esc(_v('f2py_fcompiler_flag', 'nv'))}"
          placeholder="nv">
        <p class="settings-hint">Passed as --fcompiler=&lt;value&gt; to f2py.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">WSL distro name</label>
        <input class="settings-input" type="text"
          data-key="wsl_distro" value="${_esc(_v('wsl_distro', 'Ubuntu'))}"
          placeholder="Ubuntu">
        <p class="settings-hint">Used when launching Aider in WSL mode.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">Aider launch mode</label>
        <select class="settings-select" data-key="aider_launch_mode">
          <option value="cmd" ${_v('aider_launch_mode') === 'cmd' ? 'selected' : ''}>Windows cmd terminal</option>
          <option value="wsl" ${_v('aider_launch_mode') === 'wsl' ? 'selected' : ''}>WSL bash terminal</option>
        </select>
      </div>
      <div class="settings-field">
        <label class="settings-label">Maple installation path (Windows)</label>
        <input class="settings-input" type="text"
          data-key="maple_path"
          value="${_esc(_v('maple_path', 'D:\\\\Maple\\\\bin.X86_64_WINDOWS'))}"
          placeholder="D:\\Maple\\bin.X86_64_WINDOWS">
        <p class="settings-hint">Path to Maple bin directory. cmaple.exe must be in this folder.</p>
      </div>
      <div class="settings-field">
        <label class="settings-label">Intel oneAPI root (Windows)</label>
        <input class="settings-input" type="text"
          data-key="oneapi_path"
          value="${_esc(_v('oneapi_path', 'C:\\\\Program Files (x86)\\\\Intel\\\\oneAPI'))}"
          placeholder="C:\\Program Files (x86)\\Intel\\oneAPI">
        <p class="settings-hint">Used for MKL build advice.</p>
      </div>
      <div id="toolPathsStatus" style="margin-top:8px">
        <p class="settings-hint">Loading tool detection status...</p>
      </div>
    `;
  }

  // ── Section: Models ───────────────────────────────────────────────────────

  function _sectionModels() {
    return `
      <h3 class="settings-pane-title">Models</h3>
      <div class="settings-field">
        <label class="settings-label">Ollama response timeout (seconds)</label>
        <input class="settings-input" type="number" min="30" max="600"
          data-key="ollama_timeout_sec" value="${_esc(_v('ollama_timeout_sec', '180'))}">
        <p class="settings-hint">
          How long Lincoln waits for a streaming response before giving up.
          Increase for very long Fortran analysis or large document tasks.
        </p>
      </div>
    `;
  }

  // ── Section: Infrastructure (.env admin) ──────────────────────────────────

  function _sectionInfrastructure() {
    return `
      <h3 class="settings-pane-title">Infrastructure</h3>
      <div class="settings-section-header" style="margin-bottom:12px">
        <button class="admin-mode-toggle" id="adminModeBtn"
          onclick="lincolnSettings.toggleAdminMode()">
          <i class="ti ti-lock"></i>
          <span id="adminModeBtnLabel">Enable admin mode</span>
        </button>
      </div>
      <p class="settings-hint" style="margin-bottom:16px">
        Infrastructure values are read from <code>.env</code> at startup.
        Enable admin mode to edit them.
        <strong>Changes to .env values require a restart.</strong>
        Version and codename changes take effect immediately.
      </p>

      <div class="settings-subgroup-title">Version</div>
      <div class="settings-field settings-two-col">
        <div>
          <label class="settings-label">Version number</label>
          <input class="settings-input" type="text"
            data-key="lincoln_version"
            value="${_esc(_v('lincoln_version', '0.7.0'))}"
            placeholder="0.7.0">
          <p class="settings-hint">Stored in DB. Shown in UI header and terminal banner.</p>
        </div>
        <div>
          <label class="settings-label">Codename</label>
          <input class="settings-input" type="text"
            data-key="lincoln_codename"
            value="${_esc(_v('lincoln_codename', 'Navigator'))}"
            placeholder="Navigator">
          <p class="settings-hint">Shown in terminal banner alongside version.</p>
        </div>
      </div>

      <div class="settings-subgroup-title" style="margin-top:16px">Ollama / LLM</div>
      <div data-admin-section>
        ${_infraField('OLLAMA_API_BASE',    _infra.ollama_base_url || '',
          'Ollama server URL',
          'URL where Ollama is running. Default: http://localhost:11434', '')}
        ${_infraField('LINCOLN_LLM_MODEL', _infra.llm_model || '',
          'Default LLM model',
          'The model loaded by default. Can be overridden per session in the UI model selector.', '')}
        ${_infraField('LINCOLN_EMBED_MODEL', _infra.embed_model || '',
          'Embedding model',
          'Fixed embedding model used by ChromaDB. Changing this requires a full re-index of all projects.',
          'warning-reindex')}
        ${_infraField('LINCOLN_CHUNK_SIZE', _infra.chunk_size || '',
          'RAG chunk size (tokens)',
          'Number of tokens per text chunk during indexing. Changing requires re-indexing all projects.',
          'warning-reindex')}
        ${_infraField('LINCOLN_UI_PORT',   _infra.ui_port || '5000',
          'UI port',
          'Port Lincoln serves on. Default: 5000.',
          'warning-restart')}
        ${_infraField('LINCOLN_VRAM_GB',   _infra.vram_gb || '16',
          'VRAM cap (GB)',
          "Used to calculate the context window ceiling. Set to your GPU's available VRAM.", '')}

        <div class="settings-subgroup-title" style="margin-top:16px">Google Custom Search (fallback)</div>
        <p class="settings-hint" style="margin-bottom:8px">
          Optional fallback when DuckDuckGo rate-limits. Free tier: 100 queries/day.<br>
          Setup: <a href="https://console.cloud.google.com" target="_blank">console.cloud.google.com</a>
          → Custom Search JSON API → create key.
          <a href="https://cse.google.com" target="_blank">cse.google.com</a>
          → new engine → enable "Search the entire web" → copy CX id.
        </p>
        ${_infraField('GOOGLE_API_KEY', _infra.google_api_key || '',
          'Google API Key',
          'API key for Custom Search JSON API. Leave blank to use DDG only.', '')}
        ${_infraField('GOOGLE_CSE_ID',  _infra.google_cse_id  || '',
          'Google CSE ID (cx)',
          'Custom Search Engine ID. Found at cse.google.com after creating an engine.', '')}

        <div class="settings-subgroup-title" style="margin-top:16px">Admin Actions</div>
        <p class="settings-hint" style="margin-bottom:10px">
          One-click dev tools. Only visible in admin mode.
        </p>
        <div class="infra-action-row" id="adminActionRow" style="display:none">
          <button class="infra-action-btn" onclick="lincolnSettings._openDevTerminal()">
            <i class="ti ti-terminal-2"></i>
            Open Dev Terminal
          </button>
          <button class="infra-action-btn infra-action-danger" onclick="lincolnSettings._confirmGitReset()">
            <i class="ti ti-refresh-alert"></i>
            Git Reset Hard
          </button>
        </div>
        <p class="settings-hint" id="adminActionsHint">Enable admin mode to see actions.</p>
      </div>
    `;
  }

  function _infraField(envKey, value, label, hint, warningClass) {
    const warnHtml = warningClass === 'warning-reindex'
      ? `<p class="settings-warn">⚠ Changing this requires re-indexing all projects.</p>`
      : warningClass === 'warning-restart'
      ? `<p class="settings-warn">⚠ Restart Lincoln after saving this change.</p>`
      : '';

    return `
      <div class="settings-field infra-field" data-env-key="${envKey}">
        <label class="settings-label">${_esc(label)}</label>
        <div class="infra-input-row">
          <input class="settings-input infra-input" type="text"
            value="${_esc(value)}"
            disabled
            placeholder="${_esc(envKey)}">
          <button class="infra-save-btn" style="display:none"
            onclick="lincolnSettings._saveEnvField('${envKey}', this)">
            Save
          </button>
        </div>
        <p class="settings-hint">${_esc(hint)}</p>
        ${warnHtml}
        <p class="settings-hint infra-restart-note" style="display:none;color:var(--text-warning)">
          ✓ Saved to .env — restart Lincoln for this change to take effect.
        </p>
      </div>
    `;
  }

  async function _saveEnvField(envKey, btn) {
    const field = btn.closest('.infra-field');
    const input = field.querySelector('.infra-input');
    const value = input.value.trim();
    if (!value) return;

    try {
      const res  = await fetch('/api/settings/env', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ key: envKey, value }),
      });
      const data = await res.json();
      if (res.ok) {
        field.querySelector('.infra-restart-note').style.display = 'block';
        lincolnChat?.showToast?.(`${envKey} saved — restart to apply`, 'info');
      } else {
        lincolnChat?.showToast?.(data.error || 'Failed to save setting.', 'error');
      }
    } catch (err) {
      lincolnChat?.showToast?.(`Error: ${err.message}`, 'error');
    }
  }

  async function _openDevTerminal() {
    try {
      const res  = await fetch('/api/settings/open-terminal', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        lincolnChat?.showToast?.('Dev terminal opened.', 'info');
      } else {
        lincolnChat?.showToast?.(data.error || 'Failed to open terminal.', 'error');
      }
    } catch (err) {
      lincolnChat?.showToast?.(`Error: ${err.message}`, 'error');
    }
  }

  async function _confirmGitReset() {
    if (!confirm(
      'Git Reset Hard\n\n' +
      'This will run: git reset --hard HEAD\n\n' +
      'ALL uncommitted changes will be lost. ' +
      'This cannot be undone.\n\n' +
      'Are you sure?'
    )) return;

    try {
      const res  = await fetch('/api/settings/git-reset', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        lincolnChat?.showToast?.('Git reset complete. Restart Lincoln.', 'info');
      } else {
        lincolnChat?.showToast?.(data.error || 'Git reset failed.', 'error');
      }
    } catch (err) {
      lincolnChat?.showToast?.(`Error: ${err.message}`, 'error');
    }
  }

  // ── Section: System Status ────────────────────────────────────────────────

  function _sectionStatus() {
    return `
      <h3 class="settings-pane-title">System Status</h3>
      <div id="statusContent">
        <p class="settings-hint">Loading status...</p>
      </div>
    `;
  }

  async function _loadStatus() {
    const el = document.getElementById('statusContent');
    if (!el) return;
    try {
      const res  = await fetch('/api/settings/status');
      const data = await res.json();

      const ok  = '<span style="color:var(--text-success)">✓</span>';
      const bad = '<span style="color:var(--text-danger)">✗</span>';

      const ollamaOk = data.ollama?.status === 'ok';
      const dbOk     = data.database?.status === 'ok';
      const tessOk   = data.tesseract?.status === 'ok';

      const chromaRows = (data.chromadb?.projects || []).map(p =>
        `<tr><td>${_esc(p.project)}</td><td>${p.vectors.toLocaleString()} vectors</td></tr>`
      ).join('');

      // NEW: Force the UI to read from DB settings, ignoring the stale backend response
      const fullVersionStr = `${_v('lincoln_version', '0.7.0')} -- ${_v('lincoln_codename', 'Navigator')}`;

      el.innerHTML = `
        <table class="status-table">
          <tbody>
            <tr><td>Lincoln version</td><td>${_esc(fullVersionStr)}</td></tr>
            <tr><td>Ollama</td><td>${ollamaOk ? ok : bad} ${_esc(data.ollama?.message || '')}</td></tr>
            <tr><td>Database</td><td>${dbOk ? ok : bad} ${_esc(data.database?.path || '')} (${data.database?.size_kb} KB)</td></tr>
            <tr><td>Tesseract OCR</td><td>${tessOk ? ok : bad} ${tessOk ? 'Available' : _esc(data.tesseract?.note || 'Not installed')}</td></tr>
            ${chromaRows}
          </tbody>
        </table>
      `;
    } catch (err) {
      el.innerHTML = `<p class="settings-hint" style="color:var(--text-danger)">Status load failed: ${err.message}</p>`;
    }
  }

  // ── Tool path detection ───────────────────────────────────────────────────

  async function _loadToolPaths() {
    const el = document.getElementById('toolPathsStatus');
    if (!el) return;
    try {
      const res  = await fetch('/api/settings/tools');
      const data = await res.json();
      const tools = data.tools || {};

      const rows = Object.entries(tools).map(([name, info]) => {
        const icon = info.found
          ? '<span style="color:var(--text-success)">✓</span>'
          : '<span style="color:var(--text-muted)">–</span>';
        return `
          <tr>
            <td>${_esc(name)}</td>
            <td>${icon}</td>
            <td style="font-family:monospace;font-size:11px">${_esc(info.path)}</td>
          </tr>
        `;
      }).join('');

      el.innerHTML = `
        <p class="settings-hint" style="margin-bottom:6px">Detected at startup:</p>
        <table class="status-table"><tbody>${rows}</tbody></table>
      `;
    } catch (_) {
      el.innerHTML = '';
    }
  }

  // ── Font selector ─────────────────────────────────────────────────────────

  async function _loadFonts() {
    const select = document.getElementById('fontFamilySelect');
    if (!select) return;
    try {
      const res   = await fetch('/api/settings/fonts');
      const data  = await res.json();
      const fonts = data.fonts || [];
      const current = _v('ui_font_family', 'system-ui');

      select.innerHTML = fonts.map(f =>
        `<option value="${_esc(f)}" ${f === current ? 'selected' : ''}>${_esc(f)}</option>`
      ).join('');
    } catch (_) { }
  }

  // ── Admin mode ────────────────────────────────────────────────────────────

  function toggleAdminMode() {
    _adminMode = !_adminMode;
    _applyAdminMode();
  }

  function _applyAdminMode() {
    const btn       = document.getElementById('adminModeBtn');
    const label     = document.getElementById('adminModeBtnLabel');
    const inputs    = document.querySelectorAll('.infra-input');
    const saveBtns  = document.querySelectorAll('.infra-save-btn');
    const actionRow = document.getElementById('adminActionRow');
    const actionHint= document.getElementById('adminActionsHint');

    if (!btn) return;

    btn.classList.toggle('admin-mode-active', _adminMode);
    if (label) label.textContent = _adminMode ? 'Disable admin mode' : 'Enable admin mode';

    inputs.forEach(input  => { input.disabled = !_adminMode; });
    saveBtns.forEach(b    => { b.style.display = _adminMode ? 'inline-flex' : 'none'; });
    if (actionRow)  actionRow.style.display  = _adminMode ? 'flex' : 'none';
    if (actionHint) actionHint.style.display = _adminMode ? 'none' : 'block';

    const section = document.querySelector('[data-admin-section]');
    if (section) section.dataset.adminMode = _adminMode ? 'true' : 'false';
  }

  // ── Save user settings ────────────────────────────────────────────────────

  async function _saveUserSettings() {
    const updates = {};

    document.querySelectorAll('[data-key]').forEach(el => {
      const key = el.dataset.key;
      if (!key) return;
      if (el.type === 'checkbox') {
        updates[key] = el.checked ? 'true' : 'false';
      } else {
        updates[key] = el.value;
      }
    });

    try {
      await fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(updates),
      });
      _applyTheme(updates.theme || _v('theme'));
      _applyFont(updates.ui_font_family || _v('ui_font_family'));
      // Sync always-on search pill state
      if (typeof lincolnChat !== 'undefined' && lincolnChat.syncAlwaysOnSearch) {
        lincolnChat.syncAlwaysOnSearch(updates.web_search_always_on === 'true');
      }
    } catch (err) {
      console.error('Settings save error:', err);
    }
  }

  function _applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  function _applyFont(font) {
    if (font && font !== 'system-ui') {
      document.documentElement.style.setProperty('--ui-font', `"${font}", system-ui, sans-serif`);
    } else {
      document.documentElement.style.setProperty('--ui-font', 'system-ui, sans-serif');
    }
  }

  // ── Model selector (pill dropdown in input bar) ───────────────────────────

  let _modelDropdownOpen = false;
  let _availableModels   = [];

  async function loadModels() {
    try {
      const res  = await fetch('/api/models');
      const data = await res.json();
      _availableModels = data.models || [];

      const preferred = data.default_model || '';
      if (!activeModel) {
        activeModel = preferred || (_availableModels[0]?.name ?? 'qwen3.5:9b');
      }

      _updateModelPillLabel();
      _renderModelDropdown();

      document.addEventListener('click', (e) => {
        const dropdown = document.getElementById('modelDropdown');
        const pill     = document.getElementById('modelPill');
        if (dropdown && pill && !pill.contains(e.target) && !dropdown.contains(e.target)) {
          _closeModelDropdown();
        }
      }, { capture: true });

    } catch (_) { }
  }

  function _updateModelPillLabel() {
    const label = document.getElementById('activeModelLabel');
    if (label) label.textContent = activeModel || 'qwen3.5:9b';
  }

  function _renderModelDropdown() {
    const dropdown = document.getElementById('modelDropdown');
    if (!dropdown) return;
    dropdown.innerHTML = _availableModels.map(m => `
      <div class="model-dropdown-item ${m.name === activeModel ? 'selected' : ''}"
           onclick="lincolnSettings.selectModel('${_esc(m.name)}')">
        <span>${_esc(m.name)}</span>
        <span class="model-dropdown-tag">${_formatSize(m.size)}</span>
      </div>`).join('');
  }

  function _formatSize(bytes) {
    if (!bytes) return '';
    const gb = bytes / 1e9;
    return gb >= 1 ? gb.toFixed(1) + ' GB' : Math.round(bytes / 1e6) + ' MB';
  }

  function toggleModelDropdown() {
    _modelDropdownOpen ? _closeModelDropdown() : _openModelDropdown();
  }

  function _openModelDropdown() {
    _modelDropdownOpen = true;
    const dropdown = document.getElementById('modelDropdown');
    if (dropdown) dropdown.classList.add('open');
  }

  function _closeModelDropdown() {
    _modelDropdownOpen = false;
    const dropdown = document.getElementById('modelDropdown');
    if (dropdown) dropdown.classList.remove('open');
  }

  function selectModel(modelName) {
    activeModel = modelName;
    _updateModelPillLabel();
    _renderModelDropdown();
    _closeModelDropdown();
    lincolnChat?.showToast?.(`Model: ${modelName}`, 'info');
  }

  // ── Event listeners ───────────────────────────────────────────────────────

  function _attachListeners() {
    const panel = document.getElementById('settingsPanelContent');
    if (!panel) return;

    panel.addEventListener('change', (e) => {
      if (e.target.dataset.key) {
        _saveUserSettings();
      }
    });
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str ?? '';
    return d.innerHTML;
  }

  // ── Public API ────────────────────────────────────────────────────────────

  return {
    open,
    close,
    loadModels,
    toggleAdminMode,
    toggleModelDropdown,
    selectModel,
    addPromptBlock,
    _updatePromptField,
    _deletePromptBlock,
    _saveEnvField,
    _openDevTerminal,
    _confirmGitReset,
    _switchTab,
    get activeModel() { return activeModel; },
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSettings.loadModels());
