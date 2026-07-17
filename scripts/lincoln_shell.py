# -*- coding: utf-8 -*-
# Lincoln Shell - Custom command interceptor
# Wraps Aider with Lincoln-specific commands

import sys
import subprocess
from pathlib import Path

LINCOLN_ROOT  = Path(__file__).parent.parent
SEARCH_SCRIPT = LINCOLN_ROOT / "scripts" / "web_search.py"
RAG_SCRIPT    = LINCOLN_ROOT / "scripts" / "rag_query.py"


def handle_websearch(args):
    """Intercept websearch command and inject results into Aider context."""
    raw    = args.strip()
    tokens = raw.rsplit(' ', 1)
    count  = "5"
    query  = raw

    if len(tokens) == 2 and tokens[1].isdigit():
        count = tokens[1]
        query = tokens[0]

    query = query.strip('"').strip("'")
    print(f"\nLincoln searching: {query} | Results: {count}\n")

    result = subprocess.run(
        [sys.executable, str(SEARCH_SCRIPT), "search", query, count],
        capture_output=True, text=True, encoding='utf-8'
    )
    print(result.stdout)
    if result.stderr:
        print(f"Error: {result.stderr}")


def handle_rag(args):
    """Intercept /rag command and query the Project 1 ChromaDB index."""
    raw = args.strip().strip('"').strip("'")

    if not raw:
        print("Usage: /rag \"your question here\"")
        print("       /rag \"your question here\" --top-k 8")
        return

    # Check for --top-k flag
    top_k = None
    parts = raw.rsplit("--top-k", 1)
    if len(parts) == 2:
        query = parts[0].strip().strip('"').strip("'")
        try:
            top_k = int(parts[1].strip())
        except ValueError:
            query = raw
    else:
        query = raw

    print(f"\nLincoln querying Project 1: {query}\n")

    cmd = [sys.executable, str(RAG_SCRIPT), query]
    if top_k:
        cmd += ["--top-k", str(top_k)]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    print(result.stdout)
    if result.stderr:
        # Filter out INFO log lines — only show real errors
        errors = [l for l in result.stderr.splitlines()
                  if "[ERROR]" in l or "[WARNING]" in l]
        if errors:
            print("\n".join(errors))


def main():
    """Lincoln shell — intercepts commands before passing to Aider."""
    print("Lincoln Shell Active")
    print("Commands: /ask  /rag  websearch  /add  /drop  /exit")
    print("Type 'lincoln --help' for full command reference\n")

    while True:
        try:
            user_input = input("lincoln> ").strip()

            if not user_input:
                continue

            # /rag — query Project 1 index
            if user_input.lower().startswith("/rag"):
                args = user_input[4:].strip()
                handle_rag(args)

            # websearch — DuckDuckGo search or fetch
            elif user_input.lower().startswith("websearch"):
                args = user_input[len("websearch"):].strip()
                handle_websearch(args)

            # exit
            elif user_input.lower() in ["/exit", "exit", "quit"]:
                print("Closing Lincoln...")
                break

            # everything else goes to Aider
            else:
                subprocess.run(
                    ["aider", "--no-auto-commits", "--dry-run",
                     f"--message={user_input}"]
                )

        except KeyboardInterrupt:
            print("\nClosing Lincoln...")
            break


if __name__ == "__main__":
    main()