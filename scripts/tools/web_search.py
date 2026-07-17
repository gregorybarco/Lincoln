# Lincoln Web Search Tool
# Searches DuckDuckGo and fetches page content for injection into Qwen context

import sys
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

def search(query, max_results=5):
    """Search DuckDuckGo and return results as clean text."""
    print(f"\n--- Searching for: {query} | Results requested: {max_results} ---\n")
    
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        
    for i, result in enumerate(results, 1):
        print(f"[{i}] {result['title']}")
        print(f"    URL: {result['href']}")
        print(f"    {result['body']}\n")

def fetch(url):
    """Fetch a webpage and return clean readable text."""
    print(f"\n--- Fetching: {url} ---\n")
    
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    for element in soup(["script", "style"]):
        element.decompose()
    
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    clean_text = "\n".join(lines)
    
    print(clean_text[:3000])
    print("\n--- End of fetched content ---")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Search: python scripts/tools/web_search.py search 'your query'")
        print("  Search with results: python scripts/tools/web_search.py search 'your query' 10")
        print("  Fetch:  python scripts/tools/web_search.py fetch 'https://url.com'")
        sys.exit(1)
        
    command = sys.argv[1]
    argument = sys.argv[2]
    
    # Dynamic results - default 5, override with third argument
    max_results = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    
    if command == "search":
        search(argument, max_results)
    elif command == "fetch":
        fetch(argument)
    else:
        print(f"Unknown command: {command}. Use 'search' or 'fetch'.")