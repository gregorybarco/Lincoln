"""
Lincoln RAG Query
=================
Query the Project 1 ChromaDB index from the command line or inside Aider.
All model names come from main_configuration — never hardcoded here.

Usage:
    python scripts\rag_query.py "how does the Monte Carlo pricer work"
    python scripts\rag_query.py "find the Fortran entry points" --top-k 8
    python scripts\rag_query.py "explain the PDE solver" --no-sources

Inside Aider:
    /run python scripts\rag_query.py "your question here"
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main_configuration.config import (
    CHROMA_DB_PATH, COLLECTION_NAME, DEFAULT_TOP_K,
    EMBED_MODEL, LLM_MODEL, OLLAMA_BASE_URL,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("lincoln_rag_query")


def query_index(question: str, top_k: int = DEFAULT_TOP_K, show_sources: bool = True):
    try:
        import chromadb
        from llama_index.core import Settings, VectorStoreIndex
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.llms.ollama import Ollama
        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.core import StorageContext
    except ImportError as e:
        log.error(f"Missing dependency: {e}"); sys.exit(1)

    if not Path(CHROMA_DB_PATH).exists():
        log.error("No index found. Run rag_indexer.py first."); sys.exit(1)

    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    Settings.llm = Ollama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=180.0)

    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        chroma_collection = chroma_client.get_collection(COLLECTION_NAME)
    except Exception:
        log.error(f"Collection '{COLLECTION_NAME}' not found. Run rag_indexer.py first.")
        sys.exit(1)

    vector_store    = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

    query_engine = index.as_query_engine(similarity_top_k=top_k, response_mode="compact")

    log.info(f"Model: {LLM_MODEL}  |  Embed: {EMBED_MODEL}  |  top_k={top_k}")
    log.info(f"Query: {question!r}")
    response = query_engine.query(question)

    print("\n" + "═" * 70)
    print("ANSWER")
    print("═" * 70)
    print(str(response))

    if show_sources and hasattr(response, "source_nodes"):
        print("\n" + "─" * 70)
        print(f"SOURCES  (top {len(response.source_nodes)} chunks)")
        print("─" * 70)
        for i, node in enumerate(response.source_nodes, 1):
            meta      = node.metadata
            score     = getattr(node, "score", None)
            score_str = f"  score={score:.3f}" if score is not None else ""
            print(f"\n[{i}] {meta.get('file_path', 'unknown')}{score_str}")
            print(f"    language: {meta.get('language', '?')}  |  file: {meta.get('file_name', '?')}")
            print(f"    ···  {node.text[:300].replace(chr(10), ' ')}  ···")
        print("─" * 70)

    print()
    return str(response)


def main():
    parser = argparse.ArgumentParser(description="Lincoln RAG Query")
    parser.add_argument("question",     nargs="+", help="Question to ask")
    parser.add_argument("--top-k",      type=int, default=DEFAULT_TOP_K,
                        help=f"Chunks to retrieve (default: {DEFAULT_TOP_K})")
    parser.add_argument("--no-sources", action="store_true", help="Suppress source chunk display")
    args = parser.parse_args()
    query_index(question=" ".join(args.question), top_k=args.top_k,
                show_sources=not args.no_sources)

if __name__ == "__main__":
    main()
