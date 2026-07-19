"""
Lincoln — Local AI Agent
========================
A fully local, privacy-first AI agent with zero cloud exposure.

Version history:
  0.1.0  Initial build — Ollama + Aider + Qwen 3.5 9B
  0.2.0  Web search — DuckDuckGo + BeautifulSoup fetch
  0.3.0  RAG pipeline — LlamaIndex + ChromaDB + nomic-embed-text
  0.4.0  Web UI — Flask interface, DB-driven projects, service layer

Package layout:
  lincoln_configuration.py      Infrastructure config loader (.env)
  lincoln_database.py           SQLite persistence — projects, sessions, settings
  lincoln_rag_index_service.py  RAG pipeline — indexing and querying via ChromaDB
  lincoln_ollama_service.py     Ollama LLM service — chat and streaming
  lincoln_memory_service.py     Session memory — context injection on startup
  lincoln_web_search.py         Web search — DuckDuckGo and URL fetch
  app\                          Flask web application
"""

__version__  = "0.4.0"
__codename__ = "Architect"
__author__   = "Lincoln Project"
