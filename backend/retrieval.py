from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI  # type: ignore

from .config import settings
from .lance_store import LanceStore


class Retriever:
    def __init__(self, store: Optional[LanceStore] = None) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment.")
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.store = store or LanceStore()

    def embed(self, text: str) -> List[float]:
        e = self.client.embeddings.create(model=settings.embedding_model, input=[text])
        return e.data[0].embedding  # type: ignore

    def search(
        self, match_id: str, query: str, k: int = 8, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        qv = self.embed(query)
        results = self.store.search(qv, match_id=match_id, k=k, filters=filters or {})
        # Shape results for API
        out: List[Dict[str, Any]] = []
        for r in results:
            out.append(
                {
                    "chunk_id": r.get("chunk_id"),
                    "match_id": r.get("match_id"),
                    "file_path": r.get("file_path"),
                    "source_type": r.get("source_type"),
                    "rally_id": r.get("rally_id"),
                    "text": r.get("text"),
                    "score": r.get("_distance", None),
                }
            )
        return out


