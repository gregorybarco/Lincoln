# 002 - Web Access Approach

## Date: 2026-07-17

## Decision
DuckDuckGo search and direct URL fetching via Python scripts.

## Location
scripts\tools\

## Reasoning
- No Docker required
- No API key needed
- Free forever
- Pure Python
- Zero cloud dependency maintained
- beautifulsoup4 and requests already installed via aider-chat
- Only new dependency is duckduckgo-search

## Use Cases
- Technical documentation for finance project
- Coding questions and library documentation
- Research papers and financial literature
- General Lincoln web capability

## Future
Integrate directly into Lincoln workflow so results inject automatically into Qwen context.