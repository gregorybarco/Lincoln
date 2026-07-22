"""
Lincoln Web Search Service  v0.7.0
====================================
Provides web search for Lincoln's ReAct agent loop and manual UI trigger.

Engines (in priority order):
  1. DuckDuckGo (primary)   — no API key, no account, immediate.
  2. Google Custom Search   — fallback when DDG rate-limits or times out.
     Requires GOOGLE_API_KEY and GOOGLE_CSE_ID in .env.
     SafeSearch hardcoded to 'active' — cannot be overridden by the LLM.

Security model:
  - The LLM never makes network requests directly. It emits a tool call
    JSON string. This backend intercepts it, sanitizes the query, and
    makes the actual HTTP request.
  - sanitize_query() rejects: code patterns, file paths, queries over
    120 chars. Prevents accidental confidential data exfiltration.
  - web_search_enabled DB setting acts as master switch. When False,
    this module's search() raises SearchDisabledError and the tool schema
    is stripped from the Ollama payload — the model never knows it exists.
  - Google safe='active' is hardcoded. The LLM cannot request unfiltered
    results regardless of what it generates.

Functions:
  search(query, max_results)              → list of result dicts
  fetch(url)                              → clean text content of page
  format_search_results_for_context(res) → formatted string for LLM
  sanitize_query(query)                  → (clean_query, None) | (None, error_str)
"""

import re
import sys

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")


# ── Custom exceptions ─────────────────────────────────────────────────────────

class SearchDisabledError(Exception):
    """Raised when web_search_enabled=false in DB settings."""


class QuerySanitizationError(Exception):
    """Raised when a query fails safety/privacy checks."""


# ── Query sanitizer ───────────────────────────────────────────────────────────
# Prevents the LLM from accidentally leaking code or proprietary content
# into external search queries.

_MAX_QUERY_CHARS = 120

# Patterns that indicate the LLM is injecting code or file paths into a query
_CODE_PATTERNS = [
    (r"def\s+\w+\(",              "Python function definition"),
    (r"subroutine\s+\w+",         "Fortran subroutine"),
    (r"^\s*import\s+\w+",         "Code import statement"),
    (r"class\s+\w+\s*[:(]",       "Class definition"),
    (r"[{};]\s*\n",               "Code block syntax"),
    (r"\/[\w_]+\.(?:py|f90|js|ts|cpp|h)\b", "File path with extension"),
    (r"\\[\w_]+\\[\w_]+",         "Windows file path"),
    (r"localhost:\d{4}",          "Local server address"),
    (r"(api[_-]?key|secret|token|password)\s*[=:]", "Credential pattern"),
]

_COMPILED_CODE_PATTERNS = [(re.compile(p, re.IGNORECASE | re.MULTILINE), label)
                            for p, label in _CODE_PATTERNS]


def sanitize_query(query: str) -> tuple[str, str | None]:
    """
    Validate and clean a search query.

    Returns:
        (cleaned_query, None)       if the query is safe
        (None, error_message)       if the query should be blocked

    The error message is returned to the LLM as a tool result so it
    understands why the search was blocked and can try a simpler query.
    """
    if not query or not query.strip():
        return None, "Search query cannot be empty."

    cleaned = query.strip()

    # Length check — long queries often contain pasted code
    if len(cleaned) > _MAX_QUERY_CHARS:
        return None, (
            f"Search query too long ({len(cleaned)} chars, max {_MAX_QUERY_CHARS}). "
            f"Summarise your search intent as plain keywords under {_MAX_QUERY_CHARS} characters."
        )

    # Code/path pattern check
    for pattern, label in _COMPILED_CODE_PATTERNS:
        if pattern.search(cleaned):
            return None, (
                f"Search blocked: query appears to contain {label}. "
                f"Web search queries must be plain natural-language keywords only. "
                f"Never include code, file paths, or credentials in a search query."
            )

    return cleaned, None


# ── DuckDuckGo search (primary) ───────────────────────────────────────────────

def _search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """
    Search DuckDuckGo. Returns structured results or raises on failure.
    Uses the ddgs library (pip install ddgs).
    """
    from ddgs import DDGS
    results = []
    with DDGS() as ddgs:
        raw = ddgs.text(query, safesearch="on", max_results=max_results)
        for item in raw:
            results.append({
                "title":   item.get("title", ""),
                "url":     item.get("href", ""),
                "snippet": item.get("body", ""),
                "engine":  "ddg",
            })
    return results


# ── Google Custom Search (fallback) ──────────────────────────────────────────

def _search_google(query: str, max_results: int = 5) -> list[dict]:
    """
    Search via Google Custom Search JSON API.
    Requires GOOGLE_API_KEY and GOOGLE_CSE_ID in .env / environment.

    SafeSearch is hardcoded to 'active' — the LLM cannot change this.
    """
    try:
        from lincoln.lincoln_configuration import GOOGLE_API_KEY, GOOGLE_CSE_ID
    except ImportError:
        raise RuntimeError("Google API credentials not found in lincoln_configuration.")

    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        raise RuntimeError(
            "Google API key or CSE ID not configured. "
            "Add GOOGLE_API_KEY and GOOGLE_CSE_ID to your .env file."
        )

    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "google-api-python-client not installed. "
            "Run: pip install google-api-python-client"
        )

    service  = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
    response = service.cse().list(
        q=query,
        cx=GOOGLE_CSE_ID,
        safe="active",                    # Hardcoded — LLM cannot override
        num=min(max_results, 10),
    ).execute()

    results = []
    for item in response.get("items", []):
        results.append({
            "title":   item.get("title", ""),
            "url":     item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "engine":  "google",
        })
    return results


# ── Master search function ────────────────────────────────────────────────────

def search(
    query:       str,
    max_results: int = 5,
    _skip_sanitize: bool = False,   # True only for manual UI trigger
) -> list[dict]:
    """
    Execute a web search with DDG primary / Google fallback.

    Args:
        query        : Search query (will be sanitized unless _skip_sanitize)
        max_results  : Maximum results to return
        _skip_sanitize: Bypass sanitizer for manual human-triggered searches
                        (the user typed the query themselves, not the LLM)

    Returns:
        List of result dicts: {title, url, snippet, engine}

    Raises:
        SearchDisabledError      : master switch is off
        QuerySanitizationError   : query blocked by sanitizer
        RuntimeError             : both engines failed
    """
    # Check master switch
    try:
        from lincoln.lincoln_database import get_setting
        if get_setting("web_search_enabled", "false").lower() != "true":
            raise SearchDisabledError(
                "Web search is disabled. Enable it in Settings > Web Search."
            )
    except SearchDisabledError:
        raise
    except Exception:
        pass  # DB unavailable — allow search to proceed

    # Sanitize LLM-generated queries (not manual human queries)
    if not _skip_sanitize:
        cleaned, error = sanitize_query(query)
        if error:
            raise QuerySanitizationError(error)
        query = cleaned

    # Try DDG first
    ddg_error = None
    try:
        results = _search_ddg(query, max_results)
        if results:
            print(f"[Lincoln] web_search DDG OK — query='{query}' results={len(results)}")
            return results
    except Exception as e:
        ddg_error = str(e)
        print(f"[Lincoln] web_search DDG failed ({ddg_error}), trying Google fallback")

    # Google fallback
    try:
        results = _search_google(query, max_results)
        print(f"[Lincoln] web_search Google fallback OK — query='{query}' results={len(results)}")
        return results
    except Exception as google_error:
        raise RuntimeError(
            f"Both search engines failed. "
            f"DDG: {ddg_error} | Google: {google_error}"
        )


# ── URL fetch ─────────────────────────────────────────────────────────────────

def fetch(url: str) -> str:
    """
    Fetch a URL and return clean readable text (scripts/styles stripped).

    Args:
        url : Full URL including scheme (https://...)

    Returns:
        Clean plain text content of the page.

    Raises:
        requests.RequestException on network failure or timeout.
    """
    headers  = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    text  = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# ── Context formatter ─────────────────────────────────────────────────────────

def format_search_results_for_context(results: list[dict]) -> str:
    """
    Format search results as clean text for injection into LLM context.

    Args:
        results : List of result dicts from search()

    Returns:
        Formatted string suitable for system prompt injection.
    """
    if not results:
        return "No search results found."

    lines = []
    for i, result in enumerate(results, 1):
        engine_tag = f" [{result.get('engine', '?').upper()}]" if result.get("engine") else ""
        lines.append(f"[{i}]{engine_tag} {result['title']}")
        lines.append(f"    URL: {result['url']}")
        lines.append(f"    {result['snippet']}")
        lines.append("")
    return "\n".join(lines)


# ── Terminal entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python lincoln_web_search.py search <query> [count]")
        print("  python lincoln_web_search.py fetch <url>")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "fetch":
        if len(sys.argv) < 3:
            print("Usage: python lincoln_web_search.py fetch <url>")
            sys.exit(1)
        print(f"\n--- Fetching: {sys.argv[2]} ---\n")
        print(fetch(sys.argv[2]))
        print("\n--- End of fetched content ---")

    elif mode == "search":
        args = sys.argv[2:]
        if not args:
            print("Usage: python lincoln_web_search.py search <query> [count]")
            sys.exit(1)
        count = int(args[-1]) if args[-1].isdigit() else 5
        query = " ".join(args[:-1] if args[-1].isdigit() else args)
        print(f"\n--- Searching: {query} | Results: {count} ---\n")
        results = search(query, count, _skip_sanitize=True)
        print(format_search_results_for_context(results))

    else:
        print(f"Unknown mode '{mode}'. Use 'search' or 'fetch'.")
        sys.exit(1)
