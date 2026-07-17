# -*- coding: utf-8 -*-
# Lincoln Shell - Custom command interceptor
# Wraps Aider with Lincoln-specific commands

import sys
import subprocess
from pathlib import Path

LINCOLN_ROOT = Path(__file__).parent.parent
SEARCH_SCRIPT = LINCOLN_ROOT / "scripts" / "web_search.py"

def handle_websearch(args):
    """Intercept websearch command and inject results into Aider context."""
    parts = args.strip().split()
    
    if len(parts) < 1:
        print("Usage: websearch \"query\" [number of results]")
        return
    
    # Extract query - handle quoted strings
    raw = args.strip()
    
    # Get result count if provided as last argument
    tokens = raw.rsplit(' ', 1)
    count = "5"
    query = raw
    
    if len(tokens) == 2 and tokens[1].isdigit():
        count = tokens[1]
        query = tokens[0]
    
    # Strip surrounding quotes from query
    query = query.strip('"').strip("'")
    
    print(f"\nLincoln searching: {query} | Results: {count}\n")
    
    result = subprocess.run(
        [sys.executable, str(SEARCH_SCRIPT), "search", query, count],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    print(result.stdout)
    if result.stderr:
        print(f"Error: {result.stderr}")

def main():
    """Lincoln shell - intercepts commands before passing to Aider."""
    print("Lincoln Shell Active - type 'websearch \"query\"' or any Aider command")
    print("Type /exit to close Lincoln\n")
    
    while True:
        try:
            user_input = input("> ").strip()
            
            if not user_input:
                continue
                
            # Intercept Lincoln commands
            if user_input.lower().startswith("websearch"):
                args = user_input[len("websearch"):].strip()
                handle_websearch(args)
                
            elif user_input.lower() in ["/exit", "exit", "quit"]:
                print("Closing Lincoln...")
                break
                
            else:
                # Pass everything else to Aider
                subprocess.run(["aider", "--no-auto-commits", "--dry-run", 
                               f"--message={user_input}"])
                
        except KeyboardInterrupt:
            print("\nClosing Lincoln...")
            break

if __name__ == "__main__":
    main()