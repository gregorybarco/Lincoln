/**
 * Lincoln Canvas  v0.6.1  Navigator
 * ===================================
 * Destination: B:\Homebrewed_AI\Lincoln\lincoln\app\static\js\lincoln_canvas.js
 *
 * Changes over v0.6.0:
 *   - All language run buttons now POST to /api/jupyter/execute and show output inline
 *   - Copy button kept alongside run button for all languages
 *   - Spinner state while execution is in flight
 *   - Fixed response key: API returns {result:...} not {output:...}
 *   - WSL/Fortran/C/C++/Julia/R/Bash/Maple all go through the same runBlock() path
 */

const lincolnCanvas = (() => {

  const _SK = 'lincoln_canvas_v3';

  let _codeBlocks     = [];
  let _activeTab      = 'code';
  let _selected       = new Set();
  let _lastClickedIdx = null;

  // Languages that can be run via /api/jupyter/execute
  const _RUNNABLE = new Set([
    'python', 'py', 'ipython', 'jupyter',
    'fortran', 'f90', 'f95', 'f03', 'f08', 'f',
    'c', 'cpp', 'c++', 'cxx',
    'julia', 'jl',
    'r', 'rmarkdown', 'rmd',
    'bash', 'sh', 'shell',
    'maple', 'mpl', 'mm',
  ]);

  const _HTML_LANGS = new Set(['html', 'htm']);

  // Human-readable label for toast/title
  const _LANG_LABEL = {
    python: 'Python', py: 'Python', ipython: 'Python', jupyter: 'Python',
    fortran: 'Fortran', f90: 'Fortran', f95: 'Fortran', f03: 'Fortran', f08: 'Fortran', f: 'Fortran',
    c: 'C', cpp: 'C++', 'c++': 'C++', cxx: 'C++',
    julia: 'Julia', jl: 'Julia',
    r: 'R', rmarkdown: 'R', rmd: 'R',
    bash: 'Bash', sh: 'Bash', shell: 'Bash',
    maple: 'Maple', mpl: 'Maple', mm: 'Maple',
  };

  // ── Init ────────────────────────────────────────────────────────────────────

  function init() {
    _loadFromSession();
    _renderActiveTab();
  }

  // ── Tab switching ───────────────────────────────────────────────────────────

  function switchTab(tab) {
    _activeTab = tab;
    ['tabCode', 'tabFiles', 'tabDiff'].forEach(id =>
      document.getElementById(id)?.classList.remove('active')
    );
    document.getElementById(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`)?.classList.add('active');
    _selected.clear();
    _lastClickedIdx = null;
    _renderActiveTab();
  }

  function _renderActiveTab() {
    if (_activeTab === 'code')  _renderCode();
    if (_activeTab === 'files') _renderFiles();
    if (_activeTab === 'diff')  _renderDiff();
    _renderSelectionToolbar();
  }

  // ── Filename resolution ─────────────────────────────────────────────────────

  function resolveFilename(baseName, sessionId) {
    const stripped = baseName.replace(/_v\d+(\.[^.]+)$/, '$1');
    const count = _codeBlocks.filter(b => {
      const bStripped = b.filename.replace(/_v\d+(\.[^.]+)$/, '$1');
      return bStripped === stripped && b.sessionId === sessionId;
    }).length;
    if (count === 0) return stripped;
    return stripped.replace(/(\.[^.]+)$/, `_v${count + 1}$1`);
  }

  // ── Block management ────────────────────────────────────────────────────────

  function pinCodeBlock({ language, filename, content, projectName, sessionId, prev = null }) {
    const id = Date.now() + Math.random().toString(36).slice(2, 6);
    _codeBlocks.push({ id, language, filename, content, projectName, sessionId, prev: prev ?? null, output: null, running: false });
    _saveToSession();
    _activeTab = 'code';
    ['tabCode', 'tabFiles', 'tabDiff'].forEach(tabId =>
      document.getElementById(tabId)?.classList.remove('active')
    );
    document.getElementById('tabCode')?.classList.add('active');
    _renderCode();
    _renderSelectionToolbar();
  }

  // ── Selection ───────────────────────────────────────────────────────────────

  function _onBlockClick(event, idx) {
    if (event.target.closest('.canvas-code-actions')) return;
    if (event.target.closest('.canvas-block-checkbox-wrap')) return;
    if (event.shiftKey && _lastClickedIdx !== null) {
      const min = Math.min(_lastClickedIdx, idx);
      const max = Math.max(_lastClickedIdx, idx);
      for (let i = min; i <= max; i++) _selected.add(i);
    } else if (event.ctrlKey || event.metaKey) {
      if (_selected.has(idx)) _selected.delete(idx); else _selected.add(idx);
    } else {
      return;
    }
    _lastClickedIdx = idx;
    _syncBlockCheckboxes();
    _renderSelectionToolbar();
  }

  function _onBlockCheckbox(event, idx) {
    event.stopPropagation();
    if (event.shiftKey && _lastClickedIdx !== null) {
      const min = Math.min(_lastClickedIdx, idx);
      const max = Math.max(_lastClickedIdx, idx);
      for (let i = min; i <= max; i++) _selected.add(i);
    } else {
      if (_selected.has(idx)) _selected.delete(idx); else _selected.add(idx);
    }
    _lastClickedIdx = idx;
    _syncBlockCheckboxes();
    _renderSelectionToolbar();
  }

  function _selectAllBlocks() {
    _codeBlocks.forEach((_, i) => _selected.add(i));
    _syncBlockCheckboxes();
    _renderSelectionToolbar();
  }

  function _syncBlockCheckboxes() {
    document.querySelectorAll('.canvas-code-block').forEach((el, idx) => {
      const cb = el.querySelector('.canvas-block-checkbox');
      if (cb) cb.checked = _selected.has(idx);
      el.classList.toggle('block-selected', _selected.has(idx));
    });
  }

  function hasSelection() { return _selected.size > 0; }

  function clearSelection() {
    _selected.clear();
    _lastClickedIdx = null;
    _syncBlockCheckboxes();
    _renderSelectionToolbar();
  }

  // ── Selection toolbar ───────────────────────────────────────────────────────

  function _renderSelectionToolbar() {
    let toolbar = document.getElementById('canvasSelectionToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id        = 'canvasSelectionToolbar';
      toolbar.className = 'selection-toolbar canvas-selection-toolbar';
      const canvasBody  = document.getElementById('canvasBody');
      canvasBody?.parentElement?.insertBefore(toolbar, canvasBody);
    }
    if (_selected.size === 0) { toolbar.style.display = 'none'; return; }
    toolbar.style.display = 'flex';
    toolbar.innerHTML = `
      <span class="selection-count">${_selected.size} block${_selected.size !== 1 ? 's' : ''}</span>
      <button class="selection-btn" onclick="lincolnCanvas._selectAllBlocks()">All</button>
      <button class="selection-btn" onclick="lincolnCanvas._downloadSelected()">
        <i class="ti ti-download"></i> Download
      </button>
      <button class="selection-btn selection-btn-danger" onclick="lincolnCanvas._deleteSelected()">
        <i class="ti ti-trash"></i> Delete
      </button>
      <button class="selection-btn" onclick="lincolnCanvas.clearSelection()">
        <i class="ti ti-x"></i>
      </button>
    `;
  }

  // ── Bulk actions ─────────────────────────────────────────────────────────────

  async function _downloadSelected() {
    const selected = [..._selected].map(i => _codeBlocks[i]).filter(Boolean);
    if (!selected.length) return;
    if (selected.length === 1) { saveBlock([..._selected][0]); return; }
    if (typeof JSZip !== 'undefined') {
      const zip = new JSZip();
      selected.forEach(b => zip.file(b.filename || 'code.txt', b.content));
      const blob = await zip.generateAsync({ type: 'blob' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url; a.download = 'lincoln_canvas_blocks.zip'; a.click();
      URL.revokeObjectURL(url);
    } else {
      selected.forEach((b, i) => setTimeout(() => {
        const blob = new Blob([b.content], { type: 'text/plain' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href = url; a.download = b.filename || `block_${i}.txt`; a.click();
        URL.revokeObjectURL(url);
      }, i * 200));
    }
  }

  function _deleteSelected() {
    if (!_selected.size) return;
    if (!confirm(`Remove ${_selected.size} block${_selected.size !== 1 ? 's' : ''} from canvas?`)) return;
    [..._selected].sort((a, b) => b - a).forEach(i => _codeBlocks.splice(i, 1));
    _selected.clear(); _lastClickedIdx = null;
    _saveToSession(); _renderActiveTab();
  }

  // ── Action buttons ──────────────────────────────────────────────────────────

  function _actionButtonHTML(block, idx) {
    const lang  = (block.language || '').toLowerCase();
    const label = _LANG_LABEL[lang] || lang;
    let   btns  = '';

    if (_RUNNABLE.has(lang)) {
      // Run button — always shown for executable languages
      btns += `<button class="canvas-code-action-btn canvas-run-btn ${block.running ? 'canvas-run-spinning' : ''}"
        onclick="lincolnCanvas.runBlock(${idx})"
        title="Run ${label} code"
        ${block.running ? 'disabled' : ''}
        style="color:var(--text-success)">
        <i class="ti ${block.running ? 'ti-loader-2' : 'ti-player-play'}"></i>
      </button>`;
    }

    if (_HTML_LANGS.has(lang)) {
      btns += `<button class="canvas-code-action-btn"
        onclick="lincolnCanvas._previewHTML(${idx})" title="Preview HTML">
        <i class="ti ti-eye"></i></button>`;
    }

    return btns;
  }

  // ── HTML preview ────────────────────────────────────────────────────────────

  function _previewHTML(idx) {
    const block   = _codeBlocks[idx];
    if (!block) return;
    const blockEl = document.querySelector(`.canvas-code-block[data-idx="${idx}"]`);
    if (!blockEl) return;
    let preview = blockEl.querySelector('.html-preview-frame');
    if (preview) { preview.remove(); return; }
    preview           = document.createElement('iframe');
    preview.className = 'html-preview-frame';
    preview.sandbox   = 'allow-scripts';
    preview.srcdoc    = block.content;
    blockEl.appendChild(preview);
  }

  // ── Run block ───────────────────────────────────────────────────────────────

  async function runBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block || block.running) return;

    const lang = (block.language || '').toLowerCase();

    if (!_RUNNABLE.has(lang)) {
      lincolnChat?.showToast?.(`'${block.language}' cannot be run directly`, 'info');
      return;
    }

    // Set running state — spinner on
    _codeBlocks[idx].running = true;
    _codeBlocks[idx].output  = null;
    _saveToSession();
    _renderCode();

    const label = _LANG_LABEL[lang] || lang;
    lincolnChat?.showToast?.(`Running ${label}…`, 'info');

    try {
      const res  = await fetch('/api/jupyter/execute', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ code: block.content, language: lang }),
      });
      const data = await res.json();
      _codeBlocks[idx].output = data.result || data.error || '(no output)';
    } catch (err) {
      _codeBlocks[idx].output = `❌ Network error: ${err.message}`;
    }

    _codeBlocks[idx].running = false;
    _saveToSession();
    _renderCode();

    // Scroll output into view
    requestAnimationFrame(() => {
      const el = document.querySelector(`.canvas-code-block[data-idx="${idx}"] .canvas-output-block`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  }

  // ── Copy block ──────────────────────────────────────────────────────────────

  async function copyBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block) return;
    try {
      await navigator.clipboard.writeText(block.content);
      const btn = document.querySelector(`.canvas-code-block[data-idx="${idx}"] .canvas-copy-btn`);
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="ti ti-check"></i>';
        setTimeout(() => { btn.innerHTML = orig; }, 1500);
      }
    } catch (e) { console.error('Copy failed:', e); }
  }

  // ── Save / delete ───────────────────────────────────────────────────────────

  function saveBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block) return;
    const blob = new Blob([block.content], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = block.filename || `lincoln_code_${idx}.txt`; a.click();
    URL.revokeObjectURL(url);
  }

  function deleteBlock(idx) {
    if (!confirm(`Remove "${_codeBlocks[idx]?.filename || 'this block'}" from canvas?`)) return;
    _codeBlocks.splice(idx, 1); _selected.clear();
    _saveToSession(); _renderActiveTab();
  }

  function clear() {
    _codeBlocks = []; _selected.clear();
    _saveToSession(); _renderActiveTab();
  }

  // ── Output clear ────────────────────────────────────────────────────────────

  function clearOutput(idx) {
    if (!_codeBlocks[idx]) return;
    _codeBlocks[idx].output = null;
    _saveToSession();
    _renderCode();
  }

  // ── Session persistence ─────────────────────────────────────────────────────

  function _saveToSession() {
    try { sessionStorage.setItem(_SK, JSON.stringify(_codeBlocks)); } catch (_) {}
  }

  function _loadFromSession() {
    try {
      const r = sessionStorage.getItem(_SK);
      if (r) {
        _codeBlocks = JSON.parse(r);
        // Reset any stale running states from a previous page load
        _codeBlocks.forEach(b => { b.running = false; });
      }
    } catch (_) { _codeBlocks = []; }
  }

  // ── Code block extraction ───────────────────────────────────────────────────

  function extractCodeBlocks(text) {
    const blocks = [], regex = /```(\w*)\n([\s\S]*?)```/g;
    let match;
    while ((match = regex.exec(text)) !== null)
      blocks.push({ language: match[1] || 'text', content: match[2].trimEnd() });
    return blocks;
  }

  // ── Rendering ───────────────────────────────────────────────────────────────

  function _highlighted(code, lang) {
    if (typeof hljs === 'undefined') return _esc(code);
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value; } catch (_) {}
    }
    try { return hljs.highlightAuto(code).value; } catch (_) { return _esc(code); }
  }

  function _hlClass(lang) { return lang ? `language-${lang} hljs` : 'hljs'; }

  function _esc(str) {
    const d = document.createElement('div'); d.textContent = str || ''; return d.innerHTML;
  }

  function _renderCode() {
    const body = document.getElementById('canvasBody');
    if (!body) return;
    if (!_codeBlocks.length) {
      body.innerHTML = `<div class="canvas-empty-state" id="canvasEmpty">
        <i class="ti ti-code"></i><div>Code from responses appears here</div></div>`;
      return;
    }
    body.innerHTML = _codeBlocks.map((block, idx) => `
      <div class="canvas-code-block ${_selected.has(idx) ? 'block-selected' : ''}"
           data-idx="${idx}"
           onclick="lincolnCanvas._onBlockClick(event, ${idx})">
        <div class="canvas-code-header">
          <label class="canvas-block-checkbox-wrap" onclick="event.stopPropagation()">
            <input type="checkbox" class="canvas-block-checkbox"
              ${_selected.has(idx) ? 'checked' : ''}
              onchange="lincolnCanvas._onBlockCheckbox(event, ${idx})">
          </label>
          <span class="canvas-code-lang">
            <i class="ti ti-file-code" style="font-size:11px;margin-right:4px"></i>
            ${_esc(block.filename || 'code')}
            ${block.projectName ? `<span style="color:var(--text-muted)"> &middot; ${_esc(block.projectName)}</span>` : ''}
          </span>
          <div class="canvas-code-actions">
            ${_actionButtonHTML(block, idx)}
            <button class="canvas-code-action-btn canvas-copy-btn"
              onclick="lincolnCanvas.copyBlock(${idx})" title="Copy code">
              <i class="ti ti-copy"></i></button>
            <button class="canvas-code-action-btn" onclick="lincolnCanvas.saveBlock(${idx})" title="Download">
              <i class="ti ti-download"></i></button>
            <button class="canvas-code-action-btn" onclick="lincolnCanvas.deleteBlock(${idx})" title="Remove"
                    style="color:var(--text-danger)">
              <i class="ti ti-x"></i></button>
          </div>
        </div>
        <div class="canvas-code-content">
          <pre><code class="${_hlClass(block.language)}">${_highlighted(block.content, block.language)}</code></pre>
        </div>
        ${block.running ? `
          <div class="canvas-output-block canvas-output-running">
            <span class="canvas-output-spinner"><i class="ti ti-loader-2"></i></span>
            Running…
          </div>` : ''}
        ${!block.running && block.output ? `
          <div class="canvas-output-block">
            <div class="canvas-output-header">
              <span><i class="ti ti-terminal" style="margin-right:4px"></i>Output</span>
              <button class="canvas-output-clear" onclick="lincolnCanvas.clearOutput(${idx})" title="Clear output">
                <i class="ti ti-x"></i>
              </button>
            </div>
            <pre class="canvas-output-pre">${_esc(block.output)}</pre>
          </div>` : ''}
      </div>`).join('');
  }

  function _renderFiles() {
    const body = document.getElementById('canvasBody');
    if (!body) return;
    if (!_codeBlocks.length) {
      body.innerHTML = '<div class="canvas-empty-state"><i class="ti ti-files"></i><div>No files yet</div></div>';
      return;
    }
    body.innerHTML = `<div style="display:flex;flex-direction:column;gap:4px;padding:4px 0">
      ${_codeBlocks.map((block, idx) => `
        <div class="canvas-file-row">
          <input type="checkbox" class="canvas-block-checkbox"
            ${_selected.has(idx) ? 'checked' : ''}
            onchange="lincolnCanvas._onBlockCheckbox(event, ${idx})"
            onclick="event.stopPropagation()">
          <i class="ti ti-file-code"></i>
          <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_esc(block.filename || 'code')}</span>
          <span style="font-size:10px;color:var(--text-muted)">${_esc(block.language || '')}</span>
          <button class="canvas-code-action-btn" onclick="lincolnCanvas.saveBlock(${idx})" title="Download">
            <i class="ti ti-download"></i></button>
        </div>`).join('')}
    </div>`;
  }

  function _renderDiff() {
    const body = document.getElementById('canvasBody');
    if (!body) return;
    const withDiff = _codeBlocks.filter(b => b.prev !== null && b.prev !== undefined);
    if (!withDiff.length) {
      body.innerHTML = '<div class="canvas-empty-state"><i class="ti ti-git-diff"></i><div>No diffs yet</div></div>';
      return;
    }
    body.innerHTML = withDiff.map(block => {
      const prev = (block.prev || '').split('\n');
      const curr = (block.content || '').split('\n');
      const maxLen = Math.max(prev.length, curr.length);
      let adds = 0, removes = 0, diffLines = '';
      for (let i = 0; i < maxLen; i++) {
        const p = prev[i], c = curr[i];
        if (p === undefined)      { diffLines += `<span class="diff-line diff-add">+ ${_esc(c)}</span>`; adds++; }
        else if (c === undefined) { diffLines += `<span class="diff-line diff-remove">- ${_esc(p)}</span>`; removes++; }
        else if (p !== c)         { diffLines += `<span class="diff-line diff-remove">- ${_esc(p)}</span><span class="diff-line diff-add">+ ${_esc(c)}</span>`; adds++; removes++; }
        else                      { diffLines += `<span class="diff-line diff-same">  ${_esc(p)}</span>`; }
      }
      return `<div class="canvas-diff-block">
        <div class="diff-summary">
          <i class="ti ti-git-diff" style="font-size:12px"></i>
          <span style="flex:1;font-size:11px">${_esc(block.filename || 'code')}</span>
          <span class="diff-badge-add">+${adds}</span>
          <span class="diff-badge-remove">-${removes}</span>
        </div>
        <pre class="diff-pre">${diffLines}</pre>
      </div>`;
    }).join('');
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  return {
    init, switchTab, resolveFilename, pinCodeBlock,
    runBlock, copyBlock, saveBlock, deleteBlock, clearOutput, clear,
    extractCodeBlocks, hasSelection, clearSelection,
    _onBlockClick, _onBlockCheckbox, _selectAllBlocks,
    _downloadSelected, _deleteSelected,
    _previewHTML,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnCanvas.init());
