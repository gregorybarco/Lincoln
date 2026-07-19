# Lincoln v0.5.0 — Deployment Instructions

## Files to replace

Copy each file from this output package to the corresponding location in `B:\Homebrewed_AI\Lincoln\`:

| Output file              | Destination                                              |
|--------------------------|----------------------------------------------------------|
| `lincoln_main.css`       | `lincoln\app\static\css\lincoln_main.css`                |
| `lincoln_index.html`     | `lincoln\app\templates\lincoln_index.html`               |
| `lincoln_sidebar.js`     | `lincoln\app\static\js\lincoln_sidebar.js`               |
| `lincoln_chat.js`        | `lincoln\app\static\js\lincoln_chat.js`                  |
| `lincoln_canvas.js`      | `lincoln\app\static\js\lincoln_canvas.js`                |
| `lincoln_routes_files.py`| `lincoln\app\routes\lincoln_routes_files.py`             |

## New Python dependencies

With venv active, run:

```
pip install python-docx openpyxl
```

`pypdf` is already in requirements.txt — no change needed for PDF support.

After installing, freeze:
```
pip freeze > requirements.txt
```

## What changed (v0.5.0 over v0.4.1)

### Bug fixes
- **Chat history click** — clicking a history item no longer shows the project home screen
  AND the chat underneath simultaneously. The project home collapses correctly.

### UI
- **Warm beige** — page background `#f5f0e8`, sidebar `#ede8df` (Claude-esque cream).
- **Resizable sidebar** — drag the right edge of the sidebar to resize (min 160px, max 400px).
- **Resizable canvas** — drag the left edge of the canvas to resize (min 220px, max 700px).
- **Project home** (Claude-inspired):
  - Full project home screen when clicking a project: project name, New chat button,
    Settings button, index status card, recent chats list.
  - Canvas auto-hides on project home screen (no code to show there).
  - Settings accessible directly from project home — no need to use the gear icon.
- **History toggle** — "project chats: off/on" button in the Chat history header.
  Project chats are hidden by default (matching Claude behaviour). Toggle on to see them.
- **History group badges** — count badges next to each group label (General: 5, etc).
- **Project settings path**:
  - Green resolved badge appears under the path input when an absolute path is detected.
  - Browse button opens the Windows native folder picker.
  - Browser security means the full absolute path cannot be read automatically — folder
    name appears as a hint in the placeholder. Paste the full path manually if needed
    (e.g. `B:\personal_projects\CPP_ATEMPT_3`).
  - Aider code folder now has a clear explainer ("what is this?") — leave blank to use
    the same folder as RAG source.

### Syntax highlighting (streaming)
- **Highlight.js** loaded from CDN during streaming — Python, Fortran, C/C++, JavaScript,
  TypeScript, SQL, LaTeX, Bash, Java, R, Markdown all get live colour.
- During streaming: code fences are detected in the accumulating text and rendered as
  highlighted blocks — **no more blob of unstyled text while streaming**.
- After stream completes: full `marked.js` render with hljs for code blocks.
- Canvas code blocks also get syntax highlighting (same hljs palette).
- hljs theme switches with light/dark mode.

### LaTeX / math
- **KaTeX** loaded from CDN — `$...$` inline math and `$$...$$` display math are rendered
  after each message completes. All messages and canvas support this.
- Supports standard LaTeX delimiters: `\(`, `\)`, `\[`, `\]`.

### Table rendering
- Markdown tables: alternating row shading, sticky header, improved borders — Claude-style.
- Inline code in table cells styled correctly.

### File support (expanded)
| Type       | Extensions                          | How                          |
|------------|-------------------------------------|------------------------------|
| LaTeX/math | `.tex` `.latex` `.bib`              | Plain text (UTF-8)           |
| Maple      | `.maple` `.mw` `.mpl`              | Plain text (UTF-8)           |
| Jupyter    | `.ipynb`                            | Code+markdown cells extracted|
| PDF        | `.pdf`                              | Text extracted via pypdf     |
| Word       | `.docx`                             | Text extracted via python-docx|
| Excel      | `.xlsx`                             | Rows extracted via openpyxl  |
| Previous   | All v0.4.1 types                    | Unchanged                    |

Size limits: 512 KB for text/code files, 2 MB for documents (.pdf .docx .xlsx).

## New pip packages needed

```
python-docx   # .docx text extraction
openpyxl      # .xlsx text extraction
```

pypdf is already installed.

## CHANGELOG entry

```
## 2026-07-19  v0.5.0

### Bug fixes
- Chat history click no longer renders project home + chat simultaneously

### UI improvements
- Warm beige background (#f5f0e8 page, #ede8df sidebar)
- Resizable sidebar (drag right edge) and resizable canvas (drag left edge)
- Project home screen: New chat, Settings, index status, recent chats
- Canvas hidden on project home screen
- History toggle: project chats hidden by default, toggle to show
- History group count badges
- Project settings: absolute path detection with green resolved badge
- Project settings: Aider folder explainer
- Write access warning shows dynamically when toggled on

### Syntax highlighting
- Highlight.js added: Python, Fortran, C++, JS, TS, SQL, LaTeX, Bash, R, Markdown
- Live streaming highlight: code fences coloured during token stream (no more blob)
- Canvas code blocks syntax highlighted
- hljs theme syncs with light/dark mode

### Math rendering
- KaTeX added: $...$ inline and $$...$$ display math rendered in all messages

### Table rendering
- Improved markdown table CSS: alternating rows, sticky header, inline code in cells

### File support
- Added: .tex .latex .bib .maple .mw .mpl .ipynb .pdf .docx .xlsx
- PDF text extraction via pypdf
- .docx text extraction via python-docx (new dep)
- .xlsx row extraction via openpyxl (new dep)
- Jupyter notebooks: code + markdown cells extracted
- Document size cap raised to 2 MB (.pdf .docx .xlsx); text files remain 512 KB
```
