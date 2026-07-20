/**
 * Lincoln Settings
 * ================
 * Owns the settings panel and model selector:
 *   - Opening and closing the settings overlay
 *   - Theme switching (light / dark / system)
 *   - Model selector dropdown in the input bar
 *   - Loading and saving settings via /api/settings
 *   - Loading available models from /api/models
 *   - Rendering system status in the settings panel
 *   - Checking Ollama health on startup (updates sidebar dot)
 */

const lincolnSettings = (() => {

  let _activeModel   = null;
  let _settings      = {};
  let _modelDropdownOpen = false;

  // ── Initialise ────────────────────────────────────────────────────────────

  async function init() {
    await Promise.all([
      loadSettings(),
      loadModels(),
      checkOllamaHealth(),
    ]);

    // Listen for OS theme changes when in 'system' mode to swap syntax highlighting dynamically
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if ((_settings.theme || 'system') === 'system') {
        _applyTheme('system');
      }
    });
  }

  // ── Settings load / save ──────────────────────────────────────────────────

  async function loadSettings() {
    try {
      const res  = await fetch('/api/settings');
      const data = await res.json();
      _settings  = data.ui_settings || {};

      // Apply theme
      const theme = _settings.theme || 'system';
      _applyTheme(theme);
      _updateThemeButtons(theme);

      // Apply top-k
      const topKInput = document.getElementById('topKInput');
      if (topKInput) topKInput.value = _settings.top_k || '5';

      // Show embed model
      const embedBadge = document.getElementById('embedModelBadge');
      if (embedBadge && data.infrastructure) {
        embedBadge.textContent = data.infrastructure.embed_model || 'nomic-embed-text';
      }

    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  }

  async function _saveSetting(key, value) {
    try {
      await fetch('/api/settings', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ [key]: value }),
      });
    } catch (err) {
      console.error('Failed to save setting:', err);
    }
  }


  // ── Theme ─────────────────────────────────────────────────────────────────

  function setTheme(theme) {
    _applyTheme(theme);
    _updateThemeButtons(theme);
    _saveSetting('theme', theme);
  }

  function _applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    
    // Swap syntax highlighting theme based on active color scheme
    const hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
      const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
      hljsLink.href = isDark 
        ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css'
        : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css';
    }
  }

  function _updateThemeButtons(active) {
    document.querySelectorAll('.theme-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.theme === active);
    });
  }


  // ── Models ────────────────────────────────────────────────────────────────

  async function loadModels() {
    try {
      const res  = await fetch('/api/models');
      const data = await res.json();
      const models = data.models || [];
      const defaultModel = data.default_model || 'qwen3.5:9b';

      // Set active model to default if not already set
      if (!_activeModel) {
        _activeModel = defaultModel;
        _updateModelPillLabel(_activeModel);
      }

      // Populate model dropdown
      _renderModelDropdown(models, defaultModel);

      // Populate settings default model select
      const select = document.getElementById('defaultModelSelect');
      if (select) {
        select.innerHTML = models.map(m => `
          <option value="${m.name}" ${m.name === defaultModel ? 'selected' : ''}>
            ${m.name}
          </option>
        `).join('');
      }

    } catch (err) {
      console.error('Failed to load models:', err);
    }
  }

  function _renderModelDropdown(models, defaultModel) {
    const dropdown = document.getElementById('modelDropdown');
    if (!dropdown) return;

    if (!models.length) {
      dropdown.innerHTML = '<div style="padding:10px 12px;font-size:12px;color:var(--text-muted)">No models found in Ollama.</div>';
      return;
    }

    dropdown.innerHTML = models.map(m => `
      <div class="model-dropdown-item ${m.name === _activeModel ? 'selected' : ''}"
           onclick="lincolnSettings.selectModel('${m.name}')">
        <span>${m.name}</span>
        ${m.name === defaultModel ? '<span class="model-dropdown-tag">default</span>' : ''}
      </div>
    `).join('');
  }

  function selectModel(modelName) {
    _activeModel = modelName;
    _updateModelPillLabel(modelName);
    closeModelDropdown();

    // Update dropdown selection highlight
    document.querySelectorAll('.model-dropdown-item').forEach(el => {
      el.classList.toggle('selected', el.querySelector('span')?.textContent === modelName);
    });
  }

  function _updateModelPillLabel(modelName) {
    const label = document.getElementById('activeModelLabel');
    if (label) label.textContent = modelName;
  }

  function toggleModelDropdown() {
    const dropdown = document.getElementById('modelDropdown');
    if (!dropdown) return;
    _modelDropdownOpen = !_modelDropdownOpen;
    dropdown.classList.toggle('open', _modelDropdownOpen);
  }

  function closeModelDropdown() {
    _modelDropdownOpen = false;
    document.getElementById('modelDropdown')?.classList.remove('open');
  }

  function setDefaultModel(modelName) {
    _saveSetting('default_model', modelName);
  }

  function saveTopK(value) {
    _saveSetting('top_k', value);
  }


  // ── Ollama health ─────────────────────────────────────────────────────────

  async function checkOllamaHealth() {
    try {
      const res    = await fetch('/api/models/health');
      const health = await res.json();
      const dot    = document.getElementById('ollamaStatusDot');
      if (dot) {
        dot.classList.remove('online', 'offline');
        dot.classList.add(health.status === 'ok' ? 'online' : 'offline');
        dot.title = health.message;
      }
    } catch (err) {
      const dot = document.getElementById('ollamaStatusDot');
      if (dot) { dot.classList.add('offline'); dot.title = 'Ollama unreachable'; }
    }
  }


  // ── System status ─────────────────────────────────────────────────────────

  async function loadSystemStatus() {
    const list = document.getElementById('systemStatusList');
    if (!list) return;
    list.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">Loading…</div>';

    try {
      const res    = await fetch('/api/settings/status');
      const status = await res.json();

      const items = [
        {
          label: 'Ollama',
          dot:   status.ollama?.status === 'ok' ? 'ok' : 'err',
          right: status.ollama?.url || '',
        },
        {
          label: 'ChromaDB',
          dot:   status.chromadb?.status === 'ok' ? 'ok' : 'warn',
          right: status.chromadb?.projects?.map(p => `${p.project}: ${p.vectors.toLocaleString()} vectors`).join(' · ') || 'not built',
        },
        {
          label: 'Database',
          dot:   status.database?.status === 'ok' ? 'ok' : 'err',
          right: status.database?.status === 'ok' ? `${status.database.size_kb} KB` : 'not found',
        },
        {
          label: 'MLflow',
          dot:   'warn',
          right: 'not configured',
        },
      ];

      list.innerHTML = items.map(item => `
        <div class="status-item">
          <div class="status-item-left">
            <div class="status-dot ${item.dot}"></div>
            ${item.label}
          </div>
          <div class="status-item-right">${item.right}</div>
        </div>
      `).join('');

    } catch (err) {
      list.innerHTML = '<div style="font-size:12px;color:var(--text-danger)">Failed to load status.</div>';
    }
  }


  // ── Panel open / close ────────────────────────────────────────────────────

  function open() {
    document.getElementById('settingsOverlay').style.display = 'flex';
    loadSystemStatus();
  }

  function close() {
    document.getElementById('settingsOverlay').style.display = 'none';
  }


  // ── Close dropdown on outside click ──────────────────────────────────────

  document.addEventListener('click', (e) => {
    const pill     = document.getElementById('modelPill');
    const dropdown = document.getElementById('modelDropdown');
    if (pill && dropdown && !pill.contains(e.target) && !dropdown.contains(e.target)) {
      closeModelDropdown();
    }
  });


  // ── Public API ────────────────────────────────────────────────────────────

  return {
    init,
    open,
    close,
    setTheme,
    selectModel,
    toggleModelDropdown,
    closeModelDropdown,
    setDefaultModel,
    saveTopK,
    get activeModel() { return _activeModel; },
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnSettings.init());
