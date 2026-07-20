/**
 * Lincoln Canvas  v0.5.0
 * =======================
 * Changes from v0.4.1:
 *   - Code blocks in canvas rendered with hljs syntax highlighting
 *   - Canvas hides/shows handled by lincolnCanvasUI (in lincoln_index.html)
 *     when project home is shown/hidden
 *   - Tab switching: Code / Files / Diff
 *   - Copy / save / delete actions per block
 *   - Session persistence via sessionStorage
 *   - NEW: Run Python blocks via Jupyter Sandbox
 */

const lincolnCanvas = (() => {

  const _SK = 'lincoln_canvas_v2';

  let _codeBlocks  = [];
  let _activeTab   = 'code';
  let _diffContent = null;


  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    _loadFromSession();
    _renderActiveTab();
  }


  // ── Tab switching ─────────────────────────────────────────────────────────

  function switchTab(tab) {
    _activeTab = tab;
    ['tabCode', 'tabFiles', 'tabDiff'].forEach(id => {
      document.getElementById(id)?.classList.remove('active');
    });
    document.getElementById(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`)?.classList.add('active');
    _renderActiveTab();
  }

  function _renderActiveTab() {
    if (_activeTab === 'code')  _renderCode();
    if (_activeTab === 'files') _renderFiles();
    if (_activeTab === 'diff')  _renderDiff();
  }


  // ── Resolve filename with versioning ─────────────────────────────────────
  //
  // Called by lincoln_chat.js before pinCodeBlock.
  // If "ollama_service_fix.py" already exists in this session, returns
  // "ollama_service_fix_v2.py", then "_v3", etc.
  // On reload (loadSession) blocks are added in order so versioning rebuilds
  // correctly from the paired user messages.

  function resolveFilename(baseName, sessionId) {
    // Strip any existing _vN suffix so we always work from the true base
    const stripped = baseName.replace(/_v\d+(\.[^.]+)$/, '$1');

    // Count how many blocks in this session share the same stripped base
    const count = _codeBlocks.filter(b => {
      const bStripped = b.filename.replace(/_v\d+(\.[^.]+)$/, '$1');
      return bStripped === stripped && b.sessionId === sessionId;
    }).length;

    if (count === 0) return stripped;              // first occurrence — no suffix
    return stripped.replace(/(\.[^.]+)$/, `_v${count + 1}$1`);
  }


  // ── Pin a code block ──────────────────────────────────────────────────────
  //
  // filename is now pre-resolved (unique) from lincoln_chat.js, so we
  // always push a new block — no dedup collision, no silent overwrites.

  function pinCodeBlock({ language, filename, content, projectName, sessionId, prev = null }) {
    const id = Date.now() + Math.random().toString(36).slice(2, 6);
    _codeBlocks.push({ id, language, filename, content, projectName, sessionId, prev: prev ?? null });

    _saveToSession();

    // Always switch to Code tab so the new block is immediately visible
    _activeTab = 'code';
    ['tabCode', 'tabFiles', 'tabDiff'].forEach(tabId => {
      document.getElementById(tabId)?.classList.remove('active');
    });
    document.getElementById('tabCode')?.classList.add('active');

    _renderCode();
  }


  // ── Code tab ──────────────────────────────────────────────────────────────

  function _renderCode() {
    const body = document.getElementById('canvasBody');
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

    body.innerHTML = _codeBlocks.map((block, idx) => `
      <div class="canvas-code-block">
        <div class="canvas-code-header">
          <span class="canvas-code-lang">
            <i class="ti ti-file-code" style="font-size:11px;margin-right:4px"></i>
            ${_esc(block.filename || 'code')}
            ${block.projectName ? `<span style="color:var(--text-muted)"> · ${_esc(block.projectName)}</span>` : ''}
          </span>
          <div class="canvas-code-actions">
            <!-- NEW EXECUTE IN JUPYTER BUTTON -->
            <button id="run-btn-${idx}" class="canvas-code-action-btn" onclick="lincolnCanvas.runBlock(${idx})" title="Run in Sandbox" style="color:var(--text-success)">
              <i class="ti ti-player-play"></i>
            </button>
            <button class="canvas-code-action-btn" onclick="lincolnCanvas.copyBlock(${idx})" title="Copy">
              <i class="ti ti-copy"></i>
            </button>
            <button class="canvas-code-action-btn" onclick="lincolnCanvas.saveBlock(${idx})" title="Download">
              <i class="ti ti-download"></i>
            </button>
            <button class="canvas-code-action-btn" onclick="lincolnCanvas.deleteBlock(${idx})" title="Remove"
                    style="color:var(--text-danger)">
              <i class="ti ti-x"></i>
            </button>
          </div>
        </div>
        <div class="canvas-code-content">
          <pre><code class="${_hlClass(block.language)}">${_highlighted(block.content, block.language)}</code></pre>
        </div>
        ${block.output ? block.output : ''}
      </div>
    `).join('');
  }

  /** Returns highlighted HTML for a code block */
  function _highlighted(code, lang) {
    if (typeof hljs === 'undefined') return _esc(code);
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value; }
      catch (_) {}
    }
    try { return hljs.highlightAuto(code).value; }
    catch (_) { return _esc(code); }
  }

  function _hlClass(lang) {
    if (!lang) return '';
    return `language-${lang}`;
  }


  // ── Files tab ─────────────────────────────────────────────────────────────

  function _renderFiles() {
    const body = document.getElementById('canvasBody');
    if (!body) return;

    if (!_codeBlocks.length) {
      body.innerHTML = '<div class="canvas-empty-state"><i class="ti ti-files"></i><div>No files yet</div></div>';
      return;
    }

    body.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:4px;padding:4px 0">
        ${_codeBlocks.map((block, idx) => `
          <div class="canvas-file-ref" style="cursor:pointer" onclick="lincolnCanvas.switchTab('code')">
            <i class="ti ti-file-code"></i>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              ${_esc(block.filename || 'code')}
            </span>
            <span style="font-size:10px;color:var(--text-muted)">${_esc(block.language || '')}</span>
          </div>
        `).join('')}
      </div>
    `;
  }


  // ── Diff tab ──────────────────────────────────────────────────────────────

  function _renderDiff() {
    const body = document.getElementById('canvasBody');
    if (!body) return;

    const blocksWithDiff = _codeBlocks.filter(b => b.prev !== null && b.prev !== undefined);

    if (!blocksWithDiff.length) {
      body.innerHTML = '<div class="canvas-empty-state"><i class="ti ti-git-diff"></i><div>No diffs yet</div></div>';
      return;
    }

    body.innerHTML = blocksWithDiff.map(block => {
      const prev    = (block.prev || '').split('\n');
      const curr    = (block.content || '').split('\n');
      const maxLen  = Math.max(prev.length, curr.length);
      let diffLines = '';

      for (let i = 0; i < maxLen; i++) {
        const p = prev[i];
        const c = curr[i];
        if (p === undefined) {
          diffLines += `<span class="diff-line diff-add">+ ${_esc(c)}</span>`;
        } else if (c === undefined) {
          diffLines += `<span class="diff-line diff-remove">- ${_esc(p)}</span>`;
        } else if (p !== c) {
          diffLines += `<span class="diff-line diff-remove">- ${_esc(p)}</span>`;
          diffLines += `<span class="diff-line diff-add">+ ${_esc(c)}</span>`;
        } else {
          diffLines += `<span class="diff-line diff-same">  ${_esc(p)}</span>`;
        }
      }

      return `
        <div style="margin-bottom:12px">
          <div class="canvas-file-ref" style="border-bottom:none;margin-bottom:4px">
            <i class="ti ti-git-diff"></i>
            ${_esc(block.filename || 'code')}
          </div>
          <div class="diff-viewer">${diffLines}</div>
        </div>
      `;
    }).join('');
  }


  // ── Block actions ─────────────────────────────────────────────────────────

  async function runBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block || !block.content) return;
    
    const btn = document.getElementById(`run-btn-${idx}`);
    if (btn) btn.innerHTML = '<i class="ti ti-loader ti-spin"></i>';
    
    try {
      const res = await fetch('/api/jupyter/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: block.content, language: block.language })
      });
      const data = await res.json();
      
      let outHtml = '';
      if (!res.ok) {
        outHtml = `<div style="color:var(--text-danger);margin-top:8px;font-family:var(--font-mono);font-size:11px;background:var(--danger-bg);border-top:0.5px solid var(--border);padding:8px;white-space:pre-wrap;max-height:200px;overflow-y:auto;">Error:\n${_esc(data.error)}</div>`;
      } else {
        outHtml = `<div style="color:var(--text-primary);margin-top:8px;font-family:var(--font-mono);font-size:11px;background:var(--bg-page);border-top:1px solid var(--border);padding:8px;white-space:pre-wrap;max-height:200px;overflow-y:auto;">Out[${idx+1}]:\n${_esc(data.result)}</div>`;
      }
      
      block.output = outHtml;
      _saveToSession();
      if (_activeTab === 'code') _renderCode();
      
    } catch (err) {
      alert('Execution failed: ' + err.message);
      if (btn) btn.innerHTML = '<i class="ti ti-player-play"></i>';
    }
  }

  async function copyBlock(idx) {
    const block = _codeBlocks[idx];
    if (!block) return;
    try {
      await navigator.clipboard.writeText(block.content);
      const btn = document.querySelectorAll('.canvas-code-action-btn')[idx * 4 + 1]; // Offset due to Run button
      if (btn) {
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="ti ti-check"></i>';
        setTimeout(() => { btn.innerHTML = orig; }, 1500);
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
    _codeBlocks  = [];
    _diffContent = null;
    _saveToSession();
    _renderActiveTab();
  }


  // ── Session persistence ───────────────────────────────────────────────────

  function _saveToSession() {
    try {
      sessionStorage.setItem(_SK, JSON.stringify(_codeBlocks));
    } catch (_) {}
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
    resolveFilename,
    pinCodeBlock,
    runBlock,
    copyBlock,
    saveBlock,
    deleteBlock,
    clear,
    extractCodeBlocks,
  };

})();

document.addEventListener('DOMContentLoaded', () => lincolnCanvas.init());