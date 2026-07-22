"""
Lincoln Tool Schemas  v0.7.0
==============================
Single source of truth for all tool definitions passed to Ollama's native
function-calling API (tools=[...] in the /api/chat payload).

Security tiers — enforced in lincoln_routes_chat.py:

  SAFE_TOOLS   : Execute autonomously in the backend ReAct loop.
                 No user approval needed. Read-only operations only.
                 Currently: rag_query, read_file

  SEARCH_TOOLS : Fire automatically when the web search toggle is ON.
                 Backend shows the exact query string as a toast + logs it.
                 Master switch in Settings disables entirely (strips schema).
                 Currently: web_search

  WRITE_TOOLS  : Always pause the ReAct loop and show an approval card.
                 The exact payload is displayed before any execution.
                 Currently: execute_python, execute_fortran, write_file,
                            run_aider

Rules:
  - Tool names here must match the dispatch table in lincoln_routes_chat.py.
  - Never add network-capable tools to SAFE_TOOLS.
  - Schema format: Ollama-compatible JSON (subset of OpenAI tool spec).
  - This file has zero Flask/DB dependencies — importable anywhere.
"""

from typing import Literal

# ── Tier classification ───────────────────────────────────────────────────────

SAFE_TOOLS:   list[str] = ["rag_query", "read_file"]
SEARCH_TOOLS: list[str] = ["web_search"]
WRITE_TOOLS:  list[str] = ["execute_python", "execute_fortran", "write_file", "run_aider"]

ALL_TOOL_NAMES: list[str] = SAFE_TOOLS + SEARCH_TOOLS + WRITE_TOOLS


def get_tool_tier(tool_name: str) -> Literal["safe", "search", "write", "unknown"]:
    if tool_name in SAFE_TOOLS:
        return "safe"
    if tool_name in SEARCH_TOOLS:
        return "search"
    if tool_name in WRITE_TOOLS:
        return "write"
    return "unknown"


# ── Tool schema definitions ───────────────────────────────────────────────────
# Format: Ollama /api/chat tools array item.
# Each entry: {"type": "function", "function": {name, description, parameters}}

_RAG_QUERY = {
    "type": "function",
    "function": {
        "name": "rag_query",
        "description": (
            "Query the active project's indexed codebase or document store "
            "to retrieve relevant context. Use this when the user asks about "
            "code in their project, specific files, functions, or "
            "domain-specific content that has been indexed. "
            "Returns the most relevant text chunks. "
            "Only available when a project is active."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A focused natural-language query describing what "
                        "information to retrieve from the project index. "
                        "Be specific — e.g. 'How does the Heston MC pricer "
                        "handle the vol surface calibration?' rather than "
                        "'tell me about the code'."
                    ),
                }
            },
            "required": ["query"],
        },
    },
}

_READ_FILE = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the contents of a specific file from the active project's "
            "code path. Use this when you need to see the exact current content "
            "of a file before suggesting edits, or when the user asks you to "
            "review a specific file. Returns the full file text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Relative path to the file within the project code directory. "
                        "E.g. 'lincoln/lincoln_ollama_service.py' or 'src/pricer.f90'. "
                        "Do not use absolute paths."
                    ),
                }
            },
            "required": ["file_path"],
        },
    },
}

_WEB_SEARCH = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information. Use this for: recent events, "
            "documentation you don't know, library APIs, error messages, or any "
            "factual question that may have changed since your training cutoff. "
            "IMPORTANT: The query must be plain natural-language keywords only — "
            "never include code, file paths, variable names, or proprietary terms. "
            "Keep queries under 100 characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Plain-text search keywords. Examples: "
                        "'numpy einsum performance tips', "
                        "'Heston model calibration scipy', "
                        "'Flask SSE streaming example'. "
                        "Never paste code or proprietary research into this field."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return. Default 5, max 10.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}

_EXECUTE_PYTHON = {
    "type": "function",
    "function": {
        "name": "execute_python",
        "description": (
            "Execute Python code in the local Jupyter kernel. Use this to: "
            "run calculations, test algorithms, process data, generate plots, "
            "or verify that code works before suggesting it to the user. "
            "Requires user approval before execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Complete, self-contained Python code to execute. "
                        "Include all necessary imports. The kernel is persistent "
                        "within a session so prior variables are available."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "One-sentence plain-English description of what this code "
                        "does and why. Shown to the user in the approval card."
                    ),
                },
            },
            "required": ["code", "description"],
        },
    },
}

_EXECUTE_FORTRAN = {
    "type": "function",
    "function": {
        "name": "execute_fortran",
        "description": (
            "Compile and run Fortran code using nvfortran (NVIDIA HPC SDK) via WSL. "
            "Use for high-performance numerical computation, Monte Carlo simulations, "
            "or any task requiring compiled Fortran performance. "
            "Requires user approval before compilation and execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Complete Fortran source code (free-form .f90 style).",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Suggested filename for the source file, e.g. 'mc_pricer.f90'. "
                        "Used as the compilation target name."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": (
                        "One-sentence plain-English description of what this code "
                        "computes. Shown to the user in the approval card."
                    ),
                },
                "compile_flags": {
                    "type": "string",
                    "description": (
                        "Optional nvfortran compiler flags. "
                        "Default: '-O2 -Mfree'. "
                        "E.g. '-O3 -mp' for OpenMP parallelism."
                    ),
                    "default": "-O2 -Mfree",
                },
            },
            "required": ["code", "filename", "description"],
        },
    },
}

_WRITE_FILE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": (
            "Write or overwrite a file in the active project's code directory. "
            "Use this to save generated code, update configuration files, or "
            "create new project files. "
            "REQUIRES user approval — the exact file path and content will be "
            "shown before any write occurs. Never use this for files outside "
            "the active project's code_path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Relative path within the project code directory. "
                        "E.g. 'lincoln/lincoln_new_service.py'. "
                        "Absolute paths are rejected."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Complete file content to write.",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "One-sentence plain-English description of what this file "
                        "does and why it is being written. Shown in approval card."
                    ),
                },
            },
            "required": ["file_path", "content", "description"],
        },
    },
}

_RUN_AIDER = {
    "type": "function",
    "function": {
        "name": "run_aider",
        "description": (
            "Launch Aider in suggestion mode to propose edits to existing files "
            "in the active project's code directory. Aider will analyse the files "
            "and suggest diffs — it never auto-commits. The user reviews all "
            "proposed changes before anything is applied. "
            "REQUIRES user approval before launch."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of relative file paths to pass to Aider as edit targets. "
                        "E.g. ['lincoln/lincoln_routes_chat.py', 'lincoln/lincoln_database.py']"
                    ),
                },
                "instruction": {
                    "type": "string",
                    "description": (
                        "Plain-English instruction for Aider describing the changes "
                        "to make. This is passed as the Aider prompt."
                    ),
                },
            },
            "required": ["target_files", "instruction"],
        },
    },
}


# ── Schema registry ───────────────────────────────────────────────────────────

_ALL_SCHEMAS: dict[str, dict] = {
    "rag_query":        _RAG_QUERY,
    "read_file":        _READ_FILE,
    "web_search":       _WEB_SEARCH,
    "execute_python":   _EXECUTE_PYTHON,
    "execute_fortran":  _EXECUTE_FORTRAN,
    "write_file":       _WRITE_FILE,
    "run_aider":        _RUN_AIDER,
}


def get_tool_schemas(
    include_search: bool = False,
    include_write:  bool = True,
    project_active: bool = False,
) -> list[dict]:
    """
    Build the tools array to pass to Ollama for a given request context.

    Args:
        include_search : Include web_search schema. Pass True only when the
                         master web search setting is ON. When False the model
                         never knows search exists and cannot request it.
        include_write  : Include write/execution tools (execute_python, etc.).
                         Set False for read-only sessions.
        project_active : Include rag_query and read_file only when a project
                         is active. Without a project there is nothing to query.

    Returns:
        List of Ollama-compatible tool schema dicts.
    """
    schemas = []

    if project_active:
        schemas.append(_ALL_SCHEMAS["rag_query"])
        schemas.append(_ALL_SCHEMAS["read_file"])

    if include_search:
        schemas.append(_ALL_SCHEMAS["web_search"])

    if include_write:
        schemas.append(_ALL_SCHEMAS["execute_python"])
        schemas.append(_ALL_SCHEMAS["execute_fortran"])
        schemas.append(_ALL_SCHEMAS["write_file"])
        schemas.append(_ALL_SCHEMAS["run_aider"])

    return schemas


def get_schema_by_name(tool_name: str) -> dict | None:
    """Return the full schema dict for a tool by name, or None if not found."""
    return _ALL_SCHEMAS.get(tool_name)
