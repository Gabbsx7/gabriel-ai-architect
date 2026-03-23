"""
Hive Memory — Semantic Retrieval Example
Shows how I use pgvector + embeddings for continuous learning.
"""

from pydantic import BaseModel


class MemoryEntry(BaseModel):
    namespace: str
    content: str
    metadata: dict = {}


async def store_memory(entry: MemoryEntry):
    """Stores embedding in pgvector (production version)."""
    print(f"[HIVE MEMORY] Stored in '{entry.namespace}': {entry.content[:80]}...")


async def search_memory(namespace: str, query: str, top_k: int = 5):
    """Semantic search returning top-K most relevant past executions."""
    print(f"[HIVE MEMORY] Searching '{namespace}' for: {query}")
    return [
        {"content": "Previous execution with high outcome score", "similarity": 0.94},
        {"content": "Similar case in same industry segment", "similarity": 0.89},
    ]