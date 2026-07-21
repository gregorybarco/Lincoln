/**
 * Lincoln Settings  v0.6.0  Navigator
 * ======================================
 * Complete settings panel — nothing hidden, everything editable.
 *
 * Sections:
 *   Appearance      — theme, font family, font size
 *   Chat            — history limit, show project chats
 *   Prompts & Persona — global system prompt blocks (editable textareas)
 *   RAG & Index     — top-k, snippet chars
 *   Uploads         — max sizes, retention days
 *   Web Search      — enabled default, max results
 *   Build Tools     — nvfortran, f2py flag, WSL distro, Maple, oneAPI (editable)
 *   Models          — Ollama URL, default LLM (admin)
 *   System          — UI port, VRAM cap (admin)
 *   Infrastructure  — .env values, greyed until admin mode unlocked
 *   Status          — live system health
 *
 * Admin mode: toggles a data attribute on the panel. Greyed fields become
 * editable. Each admin field shows a restart/re-index warning.
 */

const lincolnSettings = (() => {

  let _settings         = {};
  let _infra            = {};
  let _adminMode        = false;
  let _fontsLoaded      = false;
  let activeModel       = null;

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
      ${_sectionAppearance()}
      ${_sectionChat()}
      ${_sectionPrompts(prompts)}
      ${_sectionRAG()}
      ${_sectionUploads()}
      ${_sectionWebSearch()}
      ${_sectionBuildTools()}
      ${_sectionModels()}
      ${_sectionInfrastructure()}
      ${_sectionStatus()}
    `;

    _attachListeners();
    _applyAdminMode();
  }

  // ── Section: Appearance ───────────────────────────────────────────────────

  function _sectionAppearance() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">Appearance</h3>
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
      </div>
    `;
  }

  // ── Section: Chat ─────────────────────────────────────────────────────────

  function _sectionChat() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">Chat & History</h3>
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
      </div>
    `;
  }

  // ── Section: Prompts & Persona ────────────────────────────────────────────

  function _sectionPrompts(prompts) {
    const promptBlocks = Array.isArray(prompts) ? prompts : [];
    const blocksHtml   = promptBlocks.map(p => _promptBlockHTML(p)).join('');

    return `
      <div class="settings-section">
        <h3 class="settings-section-title">Prompts &amp; Persona</h3>
        <p class="settings-hint" style="margin-bottom:12px">
          These instruction blocks define how Lincoln behaves. They are assembled into
          the system prompt on every message, in order. Edit any block freely —
          this is how you control Lincoln's personality, tone, and domain knowledge.
          Project-level instructions are set in each project's Settings tab.
        </p>

        <div id="globalPromptBlocks">
          ${blocksHtml}
        </div>

        <button class="btn-secondary" style="margin-top:8px" onclick="lincolnSettings.addPromptBlock()">
          <i class="ti ti-plus"></i> Add instruction block
        </button>
      </div>
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
            placeholder="Block label (e.g. 'Lincoln persona')"
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
          placeholder="Write your instruction here. Lincoln will follow it on every message."
          rows="6"
          onblur="lincolnSettings._updatePromptField(${p.id}, 'content', this.value)"
        >${_esc(p.content)}</textarea>
        <p class="settings-hint">
          Changes saved when you click outside the text box (on blur).
        </p>
      </div>
    `;
  }

  async function addPromptBlock() {
    // Both label and content are required by the route — send non-empty defaults
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
      // newPrompt.id is now the real DB id — no more undefined
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
      <div class="settings-section">
        <h3 class="settings-section-title">RAG &amp; Index</h3>
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
      </div>
    `;
  }

  // ── Section: Uploads ──────────────────────────────────────────────────────

  function _sectionUploads() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">File Uploads</h3>
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
            Frees disk space from old chat attachments.
          </p>
        </div>
      </div>
    `;
  }

  // ── Section: Web Search ───────────────────────────────────────────────────

  function _sectionWebSearch() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">Web Search</h3>
        <div class="settings-field settings-field-row">
          <label class="settings-label">Enable web search toggle by default</label>
          <input type="checkbox" class="settings-checkbox" data-key="web_search_enabled"
            ${_v('web_search_enabled') === 'true' ? 'checked' : ''}>
        </div>
        <p class="settings-hint">
          The globe icon in the input bar enables web search per message.
          Web results are injected into the system prompt before streaming.
          Powered by DuckDuckGo (no API key required).
        </p>
      </div>
    `;
  }

  // ── Section: Build Tools ──────────────────────────────────────────────────

  function _sectionBuildTools() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">Build Tools</h3>
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
          <p class="settings-hint">NVIDIA HPC SDK Fortran compiler. Used for build advice and Aider WSL launch.</p>
        </div>
        <div class="settings-field">
          <label class="settings-label">f2py compiler flag</label>
          <input class="settings-input" type="text"
            data-key="f2py_fcompiler_flag" value="${_esc(_v('f2py_fcompiler_flag', 'nv'))}"
            placeholder="nv">
          <p class="settings-hint">Passed as --fcompiler=&lt;value&gt; to f2py. For nvfortran: nv</p>
        </div>
        <div class="settings-field">
          <label class="settings-label">WSL distro name</label>
          <input class="settings-input" type="text"
            data-key="wsl_distro" value="${_esc(_v('wsl_distro', 'Ubuntu'))}"
            placeholder="Ubuntu">
          <p class="settings-hint">Used when launching Aider in WSL mode. Matches your default wsl -l output.</p>
        </div>
        <div class="settings-field">
          <label class="settings-label">Aider launch mode</label>
          <select class="settings-select" data-key="aider_launch_mode">
            <option value="cmd" ${_v('aider_launch_mode') === 'cmd' ? 'selected' : ''}>Windows cmd terminal</option>
            <option value="wsl" ${_v('aider_launch_mode') === 'wsl' ? 'selected' : ''}>WSL bash terminal (for WSL-path projects)</option>
          </select>
          <p class="settings-hint">
            Use WSL mode for OptionsPricing and other projects where the source lives under WSL.
          </p>
        </div>
        <div class="settings-field">
          <label class="settings-label">Maple installation path (Windows)</label>
          <input class="settings-input" type="text"
            data-key="maple_path"
            value="${_esc(_v('maple_path', 'D:\\Maple\\bin.X86_64_WINDOWS'))}"
            placeholder="D:\Maple\bin.X86_64_WINDOWS">
          <p class="settings-hint">Path to Maple bin directory. cmaple.exe must be in this folder.</p>
        </div>
        <div class="settings-field">
          <label class="settings-label">Intel oneAPI root (Windows)</label>
          <input class="settings-input" type="text"
            data-key="oneapi_path"
            value="${_esc(_v('oneapi_path', 'C:\\Program Files (x86)\\Intel\\oneAPI'))}"
            placeholder="C:\Program Files (x86)\Intel\oneAPI">
          <p class="settings-hint">
            Used for MKL build advice. Intel MKL is linked at
            &lt;oneapi_path&gt;\mkl\latest.
          </p>
        </div>
        <div id="toolPathsStatus" style="margin-top:8px">
          <p class="settings-hint">Loading tool detection status…</p>
        </div>
      </div>
    `;
  }

  // ── Section: Models ───────────────────────────────────────────────────────

  function _sectionModels() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">Models</h3>
        <div class="settings-field">
          <label class="settings-label">Ollama response timeout (seconds)</label>
          <input class="settings-input" type="number" min="30" max="600"
            data-key="ollama_timeout_sec" value="${_esc(_v('ollama_timeout_sec', '180'))}">
          <p class="settings-hint">
            How long Lincoln waits for a streaming response before giving up.
            Increase for very long Fortran analysis or large document tasks.
          </p>
        </div>
      </div>
    `;
  }

  // ── Section: Infrastructure (.env admin) ──────────────────────────────────

  function _sectionInfrastructure() {
    return `
      <div class="settings-section">
        <div class="settings-section-header">
          <h3 class="settings-section-title">Infrastructure</h3>
          <button class="admin-mode-toggle" id="adminModeBtn"
            onclick="lincolnSettings.toggleAdminMode()">
            <i class="ti ti-lock"></i>
            <span id="adminModeBtnLabel">Enable admin mode</span>
          </button>
        </div>
        <p class="settings-hint" style="margin-bottom:12px">
          These values are read from <code>.env</code> at startup and affect the
          entire Lincoln system. They are shown here so nothing is hidden from you.
          Enable admin mode to edit them. <strong>Changes require a restart to take effect.</strong>
        </p>
        <div data-admin-section>
          ${_infraField('OLLAMA_API_BASE',    _infra.ollama_base_url || '',
            'Ollama server URL',
            'URL where Ollama is running. Default: http://localhost:11434',
            '')}
          ${_infraField('LINCOLN_LLM_MODEL', _infra.llm_model || '',
            'Default LLM model',
            'The model loaded by default. Can be overridden per session in the UI model selector.',
            '')}
          ${_infraField('LINCOLN_EMBED_MODEL', _infra.embed_model || '',
            'Embedding model',
            'Fixed embedding model used by ChromaDB. Changing this requires a full re-index of all projects.',
            'warning-reindex')}
          ${_infraField('LINCOLN_CHUNK_SIZE', _infra.chunk_size || '',
            'RAG chunk size (tokens)',
            'Number of tokens per text chunk during indexing. Changing this requires re-indexing all projects.',
            'warning-reindex')}
          ${_infraField('LINCOLN_UI_PORT',   _infra.ui_port || '5000',
            'UI port',
            'Port Lincoln serves on. Default: 5000. Change requires restart.',
            'warning-restart')}
          ${_infraField('LINCOLN_VRAM_GB',   _infra.vram_gb || '16',
            'VRAM cap (GB)',
            'Used to calculate the context window ceiling. Set to your GPU\'s available VRAM.',
            '')}
        </div>
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
      } else {
        alert(data.error || 'Failed to save infrastructure setting.');
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  }

  // ── Section: System Status ────────────────────────────────────────────────

  function _sectionStatus() {
    return `
      <div class="settings-section">
        <h3 class="settings-section-title">System Status</h3>
        <div id="statusContent">
          <p class="settings-hint">Loading status…</p>
        </div>
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

      el.innerHTML = `
        <table class="status-table">
          <tbody>
            <tr><td>Lincoln version</td><td>${_esc(data.version || '')}</td></tr>
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
    const section   = document.querySelector('[data-admin-section]');
    const inputs    = document.querySelectorAll('.infra-input');
    const saveBtns  = document.querySelectorAll('.infra-save-btn');

    if (!btn) return;

    btn.classList.toggle('admin-mode-active', _adminMode);
    if (label) label.textContent = _adminMode ? 'Disable admin mode' : 'Enable admin mode';

    inputs.forEach(input => { input.disabled = !_adminMode; });
    saveBtns.forEach(btn  => { btn.style.display = _adminMode ? 'inline-flex' : 'none'; });

    if (section) {
      section.dataset.adminMode = _adminMode ? 'true' : 'false';
    }
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

      // Set default active model
      const preferred = data.default_model || '';
      if (!activeModel) {
        activeModel = preferred || (_availableModels[0]?.name ?? 'qwen3.5:9b');
      }

      // Update the pill label
      _updateModelPillLabel();

      // Build/rebuild the dropdown items
      _renderModelDropdown();

      // Close dropdown when clicking outside
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
    // Auto-save any input/select/checkbox change
    const panel = document.getElementById('settingsPanelContent');
    if (!panel) return;

    panel.addEventListener('change', (e) => {
      if (e.target.dataset.key) {
        _saveUserSettings();
      }
    });

    // Textarea changes (prompts) are handled per-block via onblur
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
    get activeModel() { return activeModel; },
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSettings.loadModels());
