"""
Lincoln Database Service
========================
Single owner of data\lincoln_database.db (SQLite).

Owns all structured persistence for Lincoln:
  - Projects      : created, edited, deleted from the UI — never from .env
  - Settings      : theme, default project, top-k, UI preferences
  - Chat sessions : conversation history with per-session project association
  - Chat messages : individual messages within sessions
  - Memory entries: session summaries saved for context injection on startup

Rules:
  - No route, service, or script accesses lincoln_database.db directly.
    All database access flows through functions in this module.
  - Schema changes are additive only — never drop or rename existing columns.
    Add new columns with sensible defaults so existing data stays valid.
  - Collection names are auto-generated from the project display name.
    Format: proj_<sanitized_name>_v1
    The _v1 suffix supports future embed model migration (v2 on rebuild).
  - Project paths and collection names are never stored in .env.
    The UI is the only interface for project management.
"""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from lincoln.lincoln_configuration import CHROMA_DB_PATH, DB_PATH


# ── Schema definition ─────────────────────────────────────────────────────────

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

-- Migration: add code_path and write_enabled to existing databases
-- SQLite ignores these if the columns already exist
CREATE TABLE IF NOT EXISTS _lincoln_migration_v1 (done INTEGER);

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
"""

# Default settings seeded on first run
_DEFAULT_SETTINGS = {
    "theme":               "system",   # light | dark | system
    "default_project_id":  "",         # id of the project active on startup
    "top_k":               "5",        # RAG chunks retrieved per query
    "canvas_open":         "true",     # whether canvas panel is open by default
}


# ── Database connection ───────────────────────────────────────────────────────

def _get_connection() -> sqlite3.Connection:
    """
    Open a connection to lincoln_database.db.
    Creates the data\ directory if it does not yet exist.
    Enables foreign key enforcement on every connection.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ── Database initialisation ───────────────────────────────────────────────────

def initialise_database():
    """
    Create all tables and seed default settings.
    Safe to call on every startup — all CREATE TABLE statements use IF NOT EXISTS.
    Default settings use INSERT OR IGNORE so existing values are never overwritten.
    """
    with _get_connection() as connection:
        connection.executescript(_SCHEMA)

        # Migrate existing databases — add columns if they don't exist yet
        # SQLite doesn't support IF NOT EXISTS on ALTER TABLE, so we catch the error
        for col_sql in [
            "ALTER TABLE lincoln_projects ADD COLUMN code_path TEXT",
            "ALTER TABLE lincoln_projects ADD COLUMN write_enabled INTEGER DEFAULT 0",
        ]:
            try:
                connection.execute(col_sql)
            except Exception:
                pass  # Column already exists — safe to ignore

        for key, value in _DEFAULT_SETTINGS.items():
            connection.execute(
                "INSERT OR IGNORE INTO lincoln_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        connection.commit()

    # Clean up ghost sessions from previous startup bugs — runs every startup, safe
    delete_all_empty_sessions()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    """Current UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _sanitize_name(display_name: str) -> str:
    """
    Convert a human-readable project name to a safe internal key.
    'Options Pricing' → 'options_pricing'
    'My Project 2!'   → 'my_project_2_'
    """
    return re.sub(r"[^a-z0-9_]", "_", display_name.lower().strip())


def _generate_collection_name(display_name: str) -> str:
    """
    Generate a ChromaDB collection name from a project display name.
    'Options Pricing' → 'proj_options_pricing_v1'
    The _v1 suffix supports future embed model migration without data loss.
    """
    return f"proj_{_sanitize_name(display_name)}_v1"


# ── Project management ────────────────────────────────────────────────────────

def get_all_projects() -> list[dict]:
    """Return all projects ordered by creation date (oldest first)."""
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM lincoln_projects ORDER BY created_at ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_by_id(project_id: int) -> dict | None:
    """Return a single project by its database ID, or None if not found."""
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM lincoln_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def get_project_by_name(name: str) -> dict | None:
    """Return a single project by its internal sanitized name, or None if not found."""
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM lincoln_projects WHERE name = ?",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def create_project(display_name: str, path: str, code_path: str | None = None) -> dict:
    """
    Create a new project record in the database.

    Args:
        display_name : Human-readable label shown in the UI (e.g. 'Options Pricing')
        path         : Absolute path to the source folder to index into RAG
        code_path    : Optional path to the code folder for Aider to read.
                       Defaults to None (Aider uses path if not set).
                       write_enabled is always False — Aider never auto-writes.

    Returns:
        The newly created project as a dict.

    Raises:
        ValueError : If display_name is empty, the path does not exist on disk,
                     or a project with the same sanitized name already exists.
    """
    name       = _sanitize_name(display_name)
    collection = _generate_collection_name(display_name)

    if not name or name == "_":
        raise ValueError("Project display name cannot be empty or contain only symbols.")

    # path is optional for conversation-only projects — '.' is the sentinel value
    if path and path != '.' and not Path(path).exists():
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

        connection.execute(
            """
            INSERT INTO lincoln_projects
                (name, display_name, path, code_path, write_enabled, collection, created_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (name, display_name, path, code_path or None, collection, _now()),
        )
        connection.commit()

        row = connection.execute(
            "SELECT * FROM lincoln_projects WHERE name = ?",
            (name,),
        ).fetchone()

    return dict(row)


def update_project_vector_count(project_id: int, vector_count: int):
    """
    Update the vector count and last indexed timestamp after a successful index build.
    Called by lincoln_rag_index_service.py on completion.
    """
    with _get_connection() as connection:
        connection.execute(
            """
            UPDATE lincoln_projects
            SET vector_count = ?, last_indexed = ?
            WHERE id = ?
            """,
            (vector_count, _now(), project_id),
        )
        connection.commit()


def update_project_settings(
    project_id:    int,
    path:          str | None = None,
    code_path:     str | None = None,
    write_enabled: bool | None = None,
):
    """
    Update a project's folder path, code path, and write_enabled flag.
    Only fields explicitly passed are updated — None means leave unchanged.

    Args:
        project_id    : DB row ID of the project
        path          : New RAG source folder path (None = no change)
        code_path     : New Aider code folder path (None = no change)
        write_enabled : True/False for Aider write access (None = no change)
    """
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
    """
    Delete a project from the database.

    Args:
        project_id              : Database row ID of the project to delete.
        wipe_chroma_collection  : If True, also delete the ChromaDB collection
                                  from disk. Default False preserves vectors in
                                  case the deletion was accidental.
    """
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError(f"No project found with id {project_id}.")

    if wipe_chroma_collection:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            client.delete_collection(project["collection"])
        except Exception:
            pass  # Collection may not exist yet — not an error condition

    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_projects WHERE id = ?",
            (project_id,),
        )
        connection.commit()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_all_settings() -> dict:
    """Return all settings as a flat key-value dict."""
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT key, value FROM lincoln_settings"
        ).fetchall()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default: str = "") -> str:
    """Return a single setting value by key, or default if the key does not exist."""
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM lincoln_settings WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else default


def save_setting(key: str, value: str):
    """Save a single setting. Creates the key if it does not exist."""
    with _get_connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO lincoln_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        connection.commit()


def save_settings(updates: dict):
    """Save multiple settings in a single transaction."""
    with _get_connection() as connection:
        for key, value in updates.items():
            connection.execute(
                "INSERT OR REPLACE INTO lincoln_settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        connection.commit()


# ── Chat sessions ─────────────────────────────────────────────────────────────

def get_all_sessions(limit: int = 50) -> list[dict]:
    """
    Return recent chat sessions, newest first.
    Excludes ghost sessions — 'New chat' with no messages (created by old startup bug).
    Includes the project display name for sidebar rendering.
    """
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                s.*,
                p.display_name AS project_display_name
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
    """Delete all ghost 'New chat' sessions that have no messages. One-time cleanup."""
    with _get_connection() as connection:
        connection.execute(
            """
            DELETE FROM lincoln_chat_sessions
            WHERE title = 'New chat'
            AND NOT EXISTS (
                SELECT 1 FROM lincoln_chat_messages m WHERE m.session_id = lincoln_chat_sessions.id
            )
            """
        )
        connection.commit()


def delete_all_sessions():
    """Delete all chat sessions and messages. Used by bulk clear history."""
    with _get_connection() as connection:
        connection.execute("DELETE FROM lincoln_chat_messages")
        connection.execute("DELETE FROM lincoln_chat_sessions")
        connection.commit()


def create_session(
    title:      str       = "New chat",
    project_id: int | None = None,
) -> dict:
    """Create a new chat session and return it as a dict."""
    with _get_connection() as connection:
        now = _now()
        connection.execute(
            """
            INSERT INTO lincoln_chat_sessions
                (title, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (title, project_id, now, now),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM lincoln_chat_sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row)


def rename_session(session_id: int, new_title: str):
    """Rename a chat session. Called after the first user message is sent."""
    with _get_connection() as connection:
        connection.execute(
            "UPDATE lincoln_chat_sessions SET title = ? WHERE id = ?",
            (new_title, session_id),
        )
        connection.commit()


def delete_session(session_id: int):
    """
    Delete a chat session and all its messages.
    Foreign key CASCADE handles message deletion automatically.
    """
    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM lincoln_chat_sessions WHERE id = ?",
            (session_id,),
        )
        connection.commit()


# ── Chat messages ─────────────────────────────────────────────────────────────

def get_session_messages(session_id: int) -> list[dict]:
    """Return all messages for a session in chronological order."""
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
    """
    Add a message to a session and update the session's updated_at timestamp.

    Args:
        session_id : ID of the parent session
        role       : 'user' | 'assistant' | 'system'
        content    : Message text

    Returns:
        The newly created message as a dict.
    """
    now = _now()
    with _get_connection() as connection:
        connection.execute(
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
            "SELECT * FROM lincoln_chat_messages ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row)


# ── Memory entries ────────────────────────────────────────────────────────────

def save_memory_entry(
    content:    str,
    project_id: int | None = None,
    tag:        str | None = None,
):
    """
    Save a memory entry for context injection on future session startups.

    Args:
        content    : The memory text (e.g. a session summary)
        project_id : Optional project association
        tag        : Optional category tag (e.g. 'session_summary', 'decision')
    """
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
    """
    Return the most recent memory entries for session context injection.
    Called by the Flask app on startup to populate the session context strip.
    """
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
