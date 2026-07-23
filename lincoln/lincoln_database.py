"""
Lincoln Database Service  v0.6.0
=================================
Single owner of data\lincoln_database.db (SQLite).

Owns all structured persistence for Lincoln:
  - Projects      : created, edited, deleted from the UI
  - Settings      : all user-editable and admin settings (nothing hidden)
  - System Prompts: global and per-project persona / instruction blocks
  - Chat sessions : conversation history with per-session project association
  - Chat messages : individual messages within sessions
  - Memory entries: session summaries saved for context injection on startup

Rules:
  - No route, service, or script accesses lincoln_database.db directly.
  - Schema changes are additive only -- never drop or rename existing columns.
  - Collection names are auto-generated from project display name.
    Format: proj_<sanitized_name>_v1
"""

import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from lincoln.lincoln_configuration import CHROMA_DB_PATH, DB_PATH


# ── Default Lincoln persona (seeded once, then fully editable from UI) ────────

_DEFAULT_PERSONA = (
    "You are Lincoln, a local AI assistant running entirely on this machine.\n"
    "You help with coding, mathematical finance, quantitative research, "
    "data science, Fortran/Python/Julia development, options pricing, "
    "translation, document analysis, and web development.\n"
    "You never modify files without explicit approval.\n"
    "All inference runs locally via Ollama. No data leaves this machine.\n\n"
    "Formatting rules: respond conversationally for questions and explanations. "
    "Use markdown sparingly -- only use code blocks for actual code, "
    "bullet points only for genuine lists, headers only for long structured documents. "
    "Do not bold every other phrase. No emojis in technical responses."
)

_DEFAULT_FORMATTING_RULES = (
    "Response length: match the complexity of the question. "
    "Short questions get short answers. "
    "Do not pad responses with summaries of what you just said. "
    "Do not begin responses with 'Certainly!' or similar filler."
)


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lincoln_projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    path          TEXT NOT NULL,
    code_path     TEXT,
    write_enabled INTEGER DEFAULT 0,
    collection    TEXT UNIQUE NOT NULL,
    vector_count  INTEGER DEFAULT 0,
    last_indexed  TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lincoln_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lincoln_chat_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL DEFAULT 'New chat',
    project_id INTEGER REFERENCES lincoln_projects(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lincoln_chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL
                       REFERENCES lincoln_chat_sessions(id)
                       ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content    TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lincoln_memory_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES lincoln_projects(id) ON DELETE SET NULL,
    tag        TEXT,
    content    TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lincoln_system_prompts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL DEFAULT 'global',
    project_id INTEGER REFERENCES lincoln_projects(id) ON DELETE CASCADE,
    label      TEXT NOT NULL,
    content    TEXT NOT NULL,
    enabled    INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS lincoln_pending_tool_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL,
    tool_name    TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    arguments    TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# All user-visible settings with defaults.
# Nothing is hidden -- every value that affects Lincoln's behaviour lives here.
_DEFAULT_SETTINGS = {
    # Appearance
    "theme":                        "system",
    "ui_font_family":               "system-ui",
    # Chat behaviour
    "default_project_id":           "",
    "canvas_open":                  "true",
    "history_limit":                "100",
    "sidebar_show_project_chats":   "false",
    # RAG
    "top_k":                        "5",
    "rag_snippet_chars":            "500",
    # Uploads
    "upload_max_text_kb":           "512",
    "upload_max_doc_mb":            "2",
    "upload_retention_days":        "30",
    # Ollama / LLM
    "ollama_timeout_sec":           "180",
    "web_search_enabled":           "false",
    # Build tools (your machine -- editable from UI)
    "nvfortran_path":               "/opt/nvidia/hpc_sdk/Linux_x86_64/26.3/compilers/bin/nvfortran",
    "f2py_fcompiler_flag":          "nv",
    "wsl_distro":                   "Ubuntu",
    "maple_path":                   "D:\\Maple\\bin.X86_64_WINDOWS",
    "oneapi_path":                  "C:\\Program Files (x86)\\Intel\\oneAPI",
    # Aider
    "aider_launch_mode":            "cmd",
    # Version (DB-backed so it is editable from Settings UI without touching __init__.py)
    "lincoln_version":              "0.7.0",
    "lincoln_codename":             "Navigator",
    # Web search behaviour
    "web_search_always_on":         "false",
    "web_search_primary":           "ddg_with_fallback",
    #Version control
    "app_version": "0.7.2",
    "app_codename": "Navigator",
}


# ── Connection ────────────────────────────────────────────────────────────────

def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ── Initialisation ────────────────────────────────────────────────────────────

def initialise_database():
    """
    Create all tables, run migrations, seed defaults.
    Safe to call on every startup -- all statements are idempotent.
    """
    with _get_connection() as connection:
        connection.executescript(_SCHEMA)

        # Additive migrations for existing databases
        _migrations = [
            "ALTER TABLE lincoln_projects ADD COLUMN code_path TEXT",
            "ALTER TABLE lincoln_projects ADD COLUMN write_enabled INTEGER DEFAULT 0",
            # v0.7.0: per-project context window (free-text instructions injected
            # into system prompt after global blocks, before RAG context)
            "ALTER TABLE lincoln_projects ADD COLUMN context TEXT DEFAULT ''",
        ]
        for sql in _migrations:
            try:
                connection.execute(sql)
            except Exception:
                pass  # Column already exists

        # Seed default settings (INSERT OR IGNORE preserves existing values)
        for key, value in _DEFAULT_SETTINGS.items():
            connection.execute(
                "INSERT OR IGNORE INTO lincoln_settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        connection.commit()

    # Seed default system prompts if the table is empty
    _seed_default_system_prompts()

    # Clean up ghost sessions from previous startup bugs
    delete_all_empty_sessions()


def _seed_default_system_prompts():
    """Seed the default Lincoln persona and formatting prompts on first run."""
    with _get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM lincoln_system_prompts WHERE scope = 'global'"
        ).fetchone()[0]
        if count > 0:
            return  # Already seeded

        now = _now()
        connection.execute(
            """
            INSERT INTO lincoln_system_prompts
                (scope, project_id, label, content, enabled, sort_order, created_at, updated_at)
            VALUES ('global', NULL, ?, ?, 1, 0, ?, ?)
            """,
            ("Lincoln persona -- core behaviour", _DEFAULT_PERSONA, now, now),
        )
        connection.execute(
            """
            INSERT INTO lincoln_system_prompts
                (scope, project_id, label, content, enabled, sort_order, created_at, updated_at)
            VALUES ('global', NULL, ?, ?, 1, 1, ?, ?)
            """,
            ("Response style rules", _DEFAULT_FORMATTING_RULES, now, now),
        )
        connection.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_name(display_name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", display_name.lower().strip())


def _generate_collection_name(display_name: str) -> str:
    return f"proj_{_sanitize_name(display_name)}_v1"


# ── System prompts ────────────────────────────────────────────────────────────

def get_global_system_prompts() -> list[dict]:
    """Return all global prompt blocks ordered by sort_order."""
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM lincoln_system_prompts
            WHERE scope = 'global'
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_system_prompts(project_id: int) -> list[dict]:
    """Return all prompt blocks for a specific project."""
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM lincoln_system_prompts
            WHERE scope = 'project' AND project_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_active_system_prompt(project_id: int | None = None) -> str:
    """
    Assemble the full system prompt for a chat request.
    Concatenates all enabled global blocks, then all enabled project blocks.
    Returns the combined string for injection into the Ollama message list.
    """
    parts = []

    # Global blocks
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT content FROM lincoln_system_prompts
            WHERE scope = 'global' AND enabled = 1
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
    for row in rows:
        parts.append(row["content"])

    # Project-specific blocks
    if project_id:
        with _get_connection() as connection:
            rows = connection.execute(
                """
                SELECT content FROM lincoln_system_prompts
                WHERE scope = 'project' AND project_id = ? AND enabled = 1
                ORDER BY sort_order ASC, id ASC
                """,
                (project_id,),
            ).fetchall()
        for row in rows:
            parts.append(row["content"])

    # Always inject the current date so the LLM knows when it is.
    # This prevents stale 2024-2025 date references in web search queries.
    date_line = f"Today's date: {date.today().isoformat()}"
    parts.insert(0, date_line)

    return "\n\n---\n\n".join(parts) if parts else f"{date_line}\n\nYou are Lincoln, a local AI assistant."


def create_system_prompt(
    label:      str,
    content:    str,
    scope:      str = "global",
    project_id: int | None = None,
    enabled:    bool = True,
) -> dict:
    """Create a new system prompt block."""
    now = _now()

    # Get next sort_order for this scope
    with _get_connection() as connection:
        if scope == "global":
            max_order = connection.execute(
                "SELECT MAX(sort_order) FROM lincoln_system_prompts WHERE scope = 'global'"
            ).fetchone()[0]
        else:
            max_order = connection.execute(
                "SELECT MAX(sort_order) FROM lincoln_system_prompts WHERE scope = 'project' AND project_id = ?",
                (project_id,),
            ).fetchone()[0]

        sort_order = (max_order or 0) + 1

        cursor = connection.execute(
            """
            INSERT INTO lincoln_system_prompts
                (scope, project_id, label, content, enabled, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (scope, project_id, label, content, 1 if enabled else 0, sort_order, now, now),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM lincoln_system_prompts WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def update_system_prompt(
    prompt_id:  int,
    label:      str | None = None,
    content:    str | None = None,
    enabled:    bool | None = None,
    sort_order: int | None = None,
) -> dict | None:
    """Update fields of an existing system prompt block."""
    fields = []
    values = []

    if label is not None:
        fields.append("label = ?")
        values.append(label)
    if content is not None:
        fields.append("content = ?")
        values.append(content)
    if enabled is not None:
        fields.append("enabled = ?")
        values.append(1 if enabled else 0)
    if sort_order is not None:
        fields.append("sort_order = ?")
        values.append(sort_order)

    if not fields:
        return None

    fields.append("updated_at = ?")
    values.append(_now())
    values.append(prompt_id)

    with _get_connection() as connection:
        connection.execute(
            f"UPDATE lincoln_system_prompts SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM lincoln_system_prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_system_prompt(prompt_id: int):
    """Delete a system prompt block by id."""
    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_system_prompts WHERE id = ?",
            (prompt_id,),
        )
        connection.commit()


def reorder_system_prompts(ordered_ids: list[int]):
    """
    Set sort_order for a list of prompt ids.
    ordered_ids: list of prompt ids in the desired display order.
    """
    with _get_connection() as connection:
        for i, prompt_id in enumerate(ordered_ids):
            connection.execute(
                "UPDATE lincoln_system_prompts SET sort_order = ?, updated_at = ? WHERE id = ?",
                (i, _now(), prompt_id),
            )
        connection.commit()


# ── Projects ──────────────────────────────────────────────────────────────────

def get_all_projects() -> list[dict]:
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM lincoln_projects ORDER BY created_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_by_id(project_id: int) -> dict | None:
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM lincoln_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def get_project_by_name(name: str) -> dict | None:
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM lincoln_projects WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def get_project_context(project_id: int) -> str:
    """
    Return the per-project context instructions for a project.
    These are injected into the system prompt after global blocks,
    before RAG context. Returns empty string if not set.
    """
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT context FROM lincoln_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return ""
    return row["context"] or ""


def set_project_context(project_id: int, context: str) -> None:
    """Save per-project context instructions to the DB."""
    with _get_connection() as connection:
        connection.execute(
            "UPDATE lincoln_projects SET context = ? WHERE id = ?",
            (context.strip(), project_id),
        )
        connection.commit()


def create_project(display_name: str, path: str, code_path: str | None = None) -> dict:
    name       = _sanitize_name(display_name)
    collection = _generate_collection_name(display_name)

    if not name or name == "_":
        raise ValueError("Project display name cannot be empty or contain only symbols.")

    if path and path != "." and not Path(path).exists():
        raise ValueError(
            f"Project path does not exist on disk: {path}\n"
            f"Create the folder first, then add it as a project."
        )

    if code_path and not Path(code_path).exists():
        raise ValueError(
            f"Code path does not exist on disk: {code_path}\n"
            f"Create the folder first or leave it blank."
        )

    with _get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM lincoln_projects WHERE name = ?",
            (name,),
        ).fetchone()
        if existing:
            raise ValueError(
                f"A project named '{name}' already exists. "
                f"Choose a different display name."
            )

        cursor = connection.execute(
            """
            INSERT INTO lincoln_projects
                (name, display_name, path, code_path, write_enabled, collection, created_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (name, display_name, path, code_path or None, collection, _now()),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM lincoln_projects WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def update_project_vector_count(project_id: int, vector_count: int):
    with _get_connection() as connection:
        connection.execute(
            "UPDATE lincoln_projects SET vector_count = ?, last_indexed = ? WHERE id = ?",
            (vector_count, _now(), project_id),
        )
        connection.commit()


def update_project_settings(
    project_id:    int,
    path:          str | None = None,
    code_path:     str | None = None,
    write_enabled: bool | None = None,
) -> None:
    fields = []
    values = []

    if path is not None:
        fields.append("path = ?")
        values.append(path)
    if code_path is not None:
        fields.append("code_path = ?")
        values.append(code_path if code_path else None)
    if write_enabled is not None:
        fields.append("write_enabled = ?")
        values.append(1 if write_enabled else 0)

    if not fields:
        return

    values.append(project_id)
    with _get_connection() as connection:
        connection.execute(
            f"UPDATE lincoln_projects SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        connection.commit()


def delete_project(project_id: int, wipe_chroma_collection: bool = False):
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError(f"No project found with id {project_id}.")

    if wipe_chroma_collection:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            client.delete_collection(project["collection"])
        except Exception:
            pass

    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_projects WHERE id = ?",
            (project_id,),
        )
        connection.commit()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_all_settings() -> dict:
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT key, value FROM lincoln_settings"
        ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default: str = "") -> str:
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM lincoln_settings WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else default


def save_setting(key: str, value: str):
    with _get_connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO lincoln_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        connection.commit()


def save_settings(updates: dict):
    with _get_connection() as connection:
        for key, value in updates.items():
            connection.execute(
                "INSERT OR REPLACE INTO lincoln_settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        connection.commit()


# ── Chat sessions ─────────────────────────────────────────────────────────────

def get_all_sessions(
    limit:      int = 100,
    project_id: int | None = None,
) -> list[dict]:
    """
    Return recent chat sessions, newest first.
    Excludes ghost sessions (New chat with no messages).
    Optionally filters by project_id.
    """
    with _get_connection() as connection:
        if project_id is not None:
            rows = connection.execute(
                """
                SELECT s.*, p.display_name AS project_display_name
                FROM lincoln_chat_sessions s
                LEFT JOIN lincoln_projects p ON s.project_id = p.id
                WHERE s.project_id = ?
                AND NOT (
                    s.title = 'New chat'
                    AND NOT EXISTS (
                        SELECT 1 FROM lincoln_chat_messages m WHERE m.session_id = s.id
                    )
                )
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT s.*, p.display_name AS project_display_name
                FROM lincoln_chat_sessions s
                LEFT JOIN lincoln_projects p ON s.project_id = p.id
                WHERE NOT (
                    s.title = 'New chat'
                    AND NOT EXISTS (
                        SELECT 1 FROM lincoln_chat_messages m WHERE m.session_id = s.id
                    )
                )
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def delete_all_empty_sessions():
    with _get_connection() as connection:
        connection.execute(
            """
            DELETE FROM lincoln_chat_sessions
            WHERE title = 'New chat'
            AND NOT EXISTS (
                SELECT 1 FROM lincoln_chat_messages m
                WHERE m.session_id = lincoln_chat_sessions.id
            )
            """
        )
        connection.commit()


def delete_all_sessions():
    """Delete ALL chat sessions and messages (bulk clear)."""
    with _get_connection() as connection:
        connection.execute("DELETE FROM lincoln_chat_messages")
        connection.execute("DELETE FROM lincoln_chat_sessions")
        connection.commit()


def delete_sessions_bulk(session_ids: list[int]):
    """Delete a specific set of sessions by id (multi-select delete)."""
    if not session_ids:
        return
    placeholders = ",".join("?" * len(session_ids))
    with _get_connection() as connection:
        connection.execute(
            f"DELETE FROM lincoln_chat_sessions WHERE id IN ({placeholders})",
            session_ids,
        )
        connection.commit()


def create_session(
    title:      str = "New chat",
    project_id: int | None = None,
) -> dict:
    with _get_connection() as connection:
        now = _now()
        cursor = connection.execute(
            """
            INSERT INTO lincoln_chat_sessions
                (title, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (title, project_id, now, now),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM lincoln_chat_sessions WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def rename_session(session_id: int, new_title: str):
    with _get_connection() as connection:
        connection.execute(
            "UPDATE lincoln_chat_sessions SET title = ? WHERE id = ?",
            (new_title, session_id),
        )
        connection.commit()


def delete_session(session_id: int):
    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_chat_sessions WHERE id = ?",
            (session_id,),
        )
        connection.commit()


# ── Chat messages ─────────────────────────────────────────────────────────────

def get_session_messages(session_id: int) -> list[dict]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM lincoln_chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_message(session_id: int, role: str, content: str) -> dict:
    now = _now()
    with _get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO lincoln_chat_messages
                (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now),
        )
        connection.execute(
            "UPDATE lincoln_chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM lincoln_chat_messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


# ── Memory entries ────────────────────────────────────────────────────────────

def save_memory_entry(
    content:    str,
    project_id: int | None = None,
    tag:        str | None = None,
):
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO lincoln_memory_entries
                (project_id, tag, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, tag, content, _now()),
        )
        connection.commit()


def get_recent_memory_entries(limit: int = 5) -> list[dict]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT m.*, p.display_name AS project_display_name
            FROM lincoln_memory_entries m
            LEFT JOIN lincoln_projects p ON m.project_id = p.id
            ORDER BY m.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_all_memory_entries(project_id: int | None = None) -> list[dict]:
    """Return all memory entries for the Memory panel full list."""
    with _get_connection() as connection:
        if project_id is not None:
            rows = connection.execute(
                """
                SELECT m.*, p.display_name AS project_display_name
                FROM lincoln_memory_entries m
                LEFT JOIN lincoln_projects p ON m.project_id = p.id
                WHERE m.project_id = ?
                ORDER BY m.created_at DESC
                """,
                (project_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT m.*, p.display_name AS project_display_name
                FROM lincoln_memory_entries m
                LEFT JOIN lincoln_projects p ON m.project_id = p.id
                ORDER BY m.created_at DESC
                """
            ).fetchall()
    return [dict(row) for row in rows]


def delete_memory_entry(entry_id: int):
    """Delete a single memory entry."""
    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_memory_entries WHERE id = ?",
            (entry_id,),
        )
        connection.commit()


def delete_memory_entries_bulk(entry_ids: list[int]):
    """Delete a specific set of memory entries (multi-select delete)."""
    if not entry_ids:
        return
    placeholders = ",".join("?" * len(entry_ids))
    with _get_connection() as connection:
        connection.execute(
            f"DELETE FROM lincoln_memory_entries WHERE id IN ({placeholders})",
            entry_ids,
        )
        connection.commit()


def delete_all_memory_entries():
    """Delete all memory entries."""
    with _get_connection() as connection:
        connection.execute("DELETE FROM lincoln_memory_entries")
        connection.commit()


"""
lincoln_database.py  — v0.7.0 ADDITIONS ONLY
=============================================
These are the additions to append to the bottom of your existing
lincoln_database.py. Do NOT replace the whole file.

Add two things:

1. Add this line to the _SCHEMA string (inside the triple-quoted block,
   after the lincoln_system_prompts table definition):

   ---- PASTE INTO _SCHEMA ----

CREATE TABLE IF NOT EXISTS lincoln_pending_tool_calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL,
    tool_name    TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    arguments    TEXT NOT NULL,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

   ---- END PASTE ----

2. Append the three functions below to the bottom of lincoln_database.py.
   No other changes needed.
"""

import json

# ── Pending tool calls (ReAct human-in-the-loop gate) ────────────────────────
# When the ReAct loop encounters a WRITE_TOOL or SEARCH_TOOL that requires
# approval, it saves the pending call here, pauses the SSE stream, and sends
# an approval_required event to the UI.
#
# When the user clicks Approve or Deny, /api/chat/resolve_tool loads the
# pending call, executes or skips the tool, appends the result to history,
# and re-enters the ReAct loop to get the final LLM response.


def save_pending_tool_call(
    session_id:   int,
    tool_name:    str,
    tool_call_id: str,
    arguments:    dict,
) -> None:
    """
    Save a pending tool call awaiting user approval.
    Only one pending call per session is supported at a time.
    Any existing pending call for this session is replaced.
    """
    from lincoln.lincoln_database import _get_connection, _now

    with _get_connection() as connection:
        # Clear any stale pending call for this session first
        connection.execute(
            "DELETE FROM lincoln_pending_tool_calls WHERE session_id = ?",
            (session_id,),
        )
        connection.execute(
            """
            INSERT INTO lincoln_pending_tool_calls
                (session_id, tool_name, tool_call_id, arguments, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, tool_name, tool_call_id, json.dumps(arguments), _now()),
        )
        connection.commit()


def get_pending_tool_call(session_id: int) -> dict | None:
    """
    Retrieve the pending tool call for a session.
    Returns None if no pending call exists.
    """
    from lincoln.lincoln_database import _get_connection

    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM lincoln_pending_tool_calls WHERE session_id = ?",
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)
    result["arguments"] = json.loads(result["arguments"])
    return result


def clear_pending_tool_call(session_id: int) -> None:
    """
    Remove the pending tool call for a session after it has been resolved
    (approved or denied).
    """
    from lincoln.lincoln_database import _get_connection

    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_pending_tool_calls WHERE session_id = ?",
            (session_id,),
        )
        connection.commit()