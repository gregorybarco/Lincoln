"""
Lincoln Web Search Service
==========================
Provides DuckDuckGo search and URL fetch capabilities for Lincoln.

Used by:
  - lincoln\app\routes\lincoln_routes_chat.py  (web search from UI)
  - bin\lincoln_websearch.bat                  (terminal shortcut)

No API keys required. No cloud dependencies beyond the target URLs fetched.
All requests go through the user's own network connection.

Functions:
  search(query, max_results) → list of result dicts
  fetch(url)                 → clean text content of the page
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


def search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search DuckDuckGo and return structured results.

    Args:
        query       : Search query string
        max_results : Maximum number of results to return (default 5)

    Returns:
        List of dicts, each with keys: title, url, snippet
    """
    results = []
    with DDGS() as ddgs:
        raw = ddgs.text(query, max_results=max_results)
        for item in raw:
            results.append({
                "title":   item.get("title", ""),
                "url":     item.get("href", ""),
                "snippet": item.get("body", ""),
            })
    return results


def fetch(url: str) -> str:
    """
    Fetch a URL and return clean readable text with all scripts and styles removed.
    No character limit — full content flows into Qwen context (see ADR-004).

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

    # Remove non-content elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    text  = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def format_search_results_for_context(results: list[dict]) -> str:
    """
    Format search results as clean text for injection into Qwen context.

    Args:
        results : List of result dicts from search()

    Returns:
        Formatted string suitable for LLM context injection
    """
    if not results:
        return "No results found."

    lines = []
    for i, result in enumerate(results, 1):
        lines.append(f"[{i}] {result['title']}")
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
        results = search(query, count)
        print(format_search_results_for_context(results))

    else:
        print(f"Unknown mode '{mode}'. Use 'search' or 'fetch'.")
        sys.exit(1)
