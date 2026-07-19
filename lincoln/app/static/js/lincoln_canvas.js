/**
 * Lincoln Canvas  v0.4.1
 * =======================
 * Changes from v0.4.0:
 *   - Diff tab: real inline diff against previous version of same block
 *   - Files tab: lists all saved canvas blocks with delete per block
 *   - Save button per code block: downloads file to disk
 *   - Delete button per code block: removes from canvas and sessionStorage
 *   - Session persistence: blocks survive page tab switches via sessionStorage
 *   - Canvas is populated on session restore via lincolnChat.loadSession()
 */

const lincolnCanvas = (() => {

  let _activeTab  = 'code';
  let _codeBlocks = [];    // { id, language, filename, content, projectName, sessionId, prev }

  const _SK = 'lincoln_canvas_blocks';   // sessionStorage key


  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    _loadFromSession();
    _renderActiveTab();
  }


  // ── Tab switching ─────────────────────────────────────────────────────────

  function switchTab(tab) {
    _activeTab = tab;
    ['canvasTabCode', 'canvasTabFiles', 'canvasTabDiff'].forEach(id =>
      document.getElementById(id)?.classList.remove('active')
    );
    const map = { code: 'canvasTabCode', files: 'canvasTabFiles', diff: 'canvasTabDiff' };
    document.getElementById(map[tab])?.classList.add('active');
    _renderActiveTab();
  }

  function _renderActiveTab() {
    if (_activeTab === 'code')  _renderCode();
    if (_activeTab === 'files') _renderFiles();
    if (_activeTab === 'diff')  _renderDiff();
  }


  // ── Add a code block ──────────────────────────────────────────────────────

  function pinCodeBlock({ language, filename, content, projectName, sessionId }) {
    // If same filename already exists, keep previous version for diff
    const existing = _codeBlocks.find(b => b.filename === filename);
    const prev     = existing ? existing.content : null;
    const id       = Date.now() + Math.random().toString(36).slice(2, 6);

    if (existing) {
      existing.prev     = existing.content;
      existing.content  = content;
      existing.language = language;
    } else {
      _codeBlocks.push({ id, language, filename, content, projectName, sessionId, prev });
    }

    _saveToSession();
    _renderActiveTab();
  }


  // ── Code tab ──────────────────────────────────────────────────────────────

  function _renderCode() {
    const body  = document.getElementById('canvasBody');
    if (!body) return;

    if (!_codeBlocks.length) {
      body.innerHTML = `
        <div class="canvas-empty-state" id="canvasEmpty">
          <i class="ti ti-code"></i>
          <div>Code from responses appears here</div>
        </div>
      `;
      return;
    }

    body.innerHTML = `
      <div class="canvas-code-blocks" style="display:flex;flex-direction:column">
        ${_codeBlocks.map((block, idx) => `
          <div class="canvas-file-ref">
            <i class="ti ti-file-code"></i>
            ${_esc(block.filename || 'code')}
            ${block.projectName ? ' · <span style="color:var(--text-muted)">' + _esc(block.projectName) + '</span>' : ''}
          </div>
          <div class="canvas-code-block">
            <div class="canvas-code-header">
              <span class="canvas-code-lang">${_esc(block.language || 'text')}</span>
              <div style="display:flex;gap:6px;align-items:center">
                <button class="canvas-copy-btn" onclick="lincolnCanvas.copyBlock(${idx})" title="Copy">
                  <i class="ti ti-copy"></i> copy
                </button>
                <button class="canvas-copy-btn" onclick="lincolnCanvas.saveBlock(${idx})" title="Save to disk">
                  <i class="ti ti-download"></i> save
                </button>
                <button class="canvas-copy-btn" onclick="lincolnCanvas.deleteBlock(${idx})" title="Remove" style="color:var(--text-danger)">
                  <i class="ti ti-trash"></i>
                </button>
              </div>
            </div>
            <pre id="codeBlock_${idx}">${_esc(block.content)}</pre>
          </div>
        `).join('')}
      </div>
    `;
  }


  // ── Files tab ─────────────────────────────────────────────────────────────

  function _renderFiles() {
    const body = document.getElementById('canvasBody');
    if (!body) return;

    if (!_codeBlocks.length) {
      body.innerHTML = `
        <div class="canvas-empty-state">
          <i class="ti ti-files"></i>
          <div>No saved canvas blocks yet</div>
        </div>
      `;
      return;
    }

    body.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:6px;padding:4px 0">
        ${_codeBlocks.map((block, idx) => `
          <div class="canvas-file-row">
            <i class="ti ti-file-code" style="color:var(--accent-text);font-size:14px;flex-shrink:0"></i>
            <div style="flex:1;min-width:0">
              <div style="font-size:12px;font-weight:500;color:var(--text-primary);
                          white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                ${_esc(block.filename || 'code')}
              </div>
              <div style="font-size:10px;color:var(--text-muted)">
                ${_esc(block.language)} · ${block.content.split('\n').length} lines
                ${block.projectName ? ' · ' + _esc(block.projectName) : ''}
              </div>
            </div>
            <div style="display:flex;gap:4px;flex-shrink:0">
              <button class="canvas-copy-btn" onclick="lincolnCanvas.saveBlock(${idx})" title="Download">
                <i class="ti ti-download"></i>
              </button>
              <button class="canvas-copy-btn" onclick="lincolnCanvas.deleteBlock(${idx})" title="Delete" style="color:var(--text-danger)">
                <i class="ti ti-trash"></i>
              </button>
            </div>
          </div>
        `).join('')}
        <div style="margin-top:8px;padding-top:8px;border-top:0.5px solid var(--border)">
          <button class="canvas-copy-btn" onclick="lincolnCanvas.clear()" style="color:var(--text-danger)">
            <i class="ti ti-trash"></i> Clear all canvas blocks
          </button>
        </div>
      </div>
    `;
  }


  // ── Diff tab ──────────────────────────────────────────────────────────────

  function _renderDiff() {
    const body = document.getElementById('canvasBody');
    if (!body) return;

    const diffable = _codeBlocks.filter(b => b.prev !== null && b.prev !== undefined);

    if (!diffable.length) {
      body.innerHTML = `
        <div class="canvas-empty-state">
          <i class="ti ti-git-diff"></i>
          <div>Diff appears when the same<br>file is generated twice</div>
        </div>
      `;
      return;
    }

    body.innerHTML = diffable.map(block => `
      <div class="canvas-file-ref">
        <i class="ti ti-git-diff"></i>
        ${_esc(block.filename)} — changes
      </div>
      <div class="canvas-diff-block">
        ${_computeDiff(block.prev, block.content)}
      </div>
    `).join('');
  }

  function _computeDiff(oldText, newText) {
    const oldLines = (oldText || '').split('\n');
    const newLines = (newText || '').split('\n');

    // Simple line-by-line diff (LCS-lite: enough for code review)
    const result = [];
    const maxLen = Math.max(oldLines.length, newLines.length);

    // Build a basic edit script: removed lines (-), added lines (+), unchanged (=)
    // Using a greedy approach: match lines in order
    let oi = 0, ni = 0;
    while (oi < oldLines.length || ni < newLines.length) {
      const ol = oldLines[oi];
      const nl = newLines[ni];

      if (oi >= oldLines.length) {
        result.push({ type: 'add',    line: nl });
        ni++;
      } else if (ni >= newLines.length) {
        result.push({ type: 'remove', line: ol });
        oi++;
      } else if (ol === nl) {
        result.push({ type: 'same',   line: ol });
        oi++; ni++;
      } else {
        // Look ahead: check if old line appears soon in new (deletion), or vice versa (addition)
        const newAhead  = newLines.slice(ni, ni + 4).indexOf(ol);
        const oldAhead  = oldLines.slice(oi, oi + 4).indexOf(nl);

        if (newAhead !== -1 && (oldAhead === -1 || newAhead <= oldAhead)) {
          result.push({ type: 'add', line: nl });
          ni++;
        } else if (oldAhead !== -1) {
          result.push({ type: 'remove', line: ol });
          oi++;
        } else {
          result.push({ type: 'remove', line: ol });
          result.push({ type: 'add',    line: nl });
          oi++; ni++;
        }
      }
    }

    const rendered = result.map(r => {
      if (r.type === 'add')    return `<div class="diff-line diff-add">+ ${_esc(r.line)}</div>`;
      if (r.type === 'remove') return `<div class="diff-line diff-remove">- ${_esc(r.line)}</div>`;
      return `<div class="diff-line diff-same">  ${_esc(r.line)}</div>`;
    }).join('');

    const adds    = result.filter(r => r.type === 'add').length;
    const removes = result.filter(r => r.type === 'remove').length;

    return `
      <div class="diff-summary">
        <span class="diff-badge-add">+${adds}</span>
        <span class="diff-badge-remove">−${removes}</span>
      </div>
      <pre class="diff-pre">${rendered}</pre>
    `;
  }


  // ── Block actions ─────────────────────────────────────────────────────────

  async function copyBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block) return;
    try {
      await navigator.clipboard.writeText(block.content);
      const btns = document.querySelectorAll('.canvas-copy-btn');
      // Find the copy button for this index (first button in the header of block idx)
      const btn = document.querySelectorAll('.canvas-code-block .canvas-code-header')[idx]
                    ?.querySelector('.canvas-copy-btn');
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="ti ti-check"></i> copied';
        setTimeout(() => { btn.innerHTML = orig; }, 1800);
      }
    } catch (err) {
      console.error('Copy failed:', err);
    }
  }

  function saveBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block) return;
    const blob = new Blob([block.content], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = block.filename || `lincoln_code_${idx}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function deleteBlock(idx) {
    if (!confirm(`Remove "${_codeBlocks[idx]?.filename || 'this block'}" from canvas?`)) return;
    _codeBlocks.splice(idx, 1);
    _saveToSession();
    _renderActiveTab();
  }

  function clear() {
    _codeBlocks = [];
    _saveToSession();
    _renderActiveTab();
  }


  // ── Session persistence ───────────────────────────────────────────────────

  function _saveToSession() {
    try {
      sessionStorage.setItem(_SK, JSON.stringify(_codeBlocks));
    } catch (_) { /* sessionStorage full — ignore */ }
  }

  function _loadFromSession() {
    try {
      const raw = sessionStorage.getItem(_SK);
      if (raw) _codeBlocks = JSON.parse(raw);
    } catch (_) { _codeBlocks = []; }
  }


  // ── Extract code blocks from markdown ─────────────────────────────────────

  function extractCodeBlocks(text) {
    const blocks = [];
    const regex  = /```(\w*)\n([\s\S]*?)```/g;
    let match;
    while ((match = regex.exec(text)) !== null) {
      blocks.push({ language: match[1] || 'text', content: match[2].trimEnd() });
    }
    return blocks;
  }


  // ── Utilities ─────────────────────────────────────────────────────────────

  function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }


  // ── Public API ────────────────────────────────────────────────────────────

  return {
    init,
    switchTab,
    pinCodeBlock,
    copyBlock,
    saveBlock,
    deleteBlock,
    clear,
    extractCodeBlocks,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnCanvas.init());
