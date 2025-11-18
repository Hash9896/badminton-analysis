from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import settings

# Lazy import to fail gracefully if lancedb is missing
_lancedb = None


def _ensure_lancedb():
    global _lancedb
    if _lancedb is None:
        try:
            import lancedb  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "lancedb is required. Please install with `pip install lancedb`."
            ) from e
        _lancedb = lancedb
    return _lancedb


class LanceStore:
    def __init__(self, db_dir: Optional[str] = None) -> None:
        lancedb = _ensure_lancedb()
        self.db_dir = db_dir or settings.vector_db_dir
        os.makedirs(self.db_dir, exist_ok=True)
        self.db = lancedb.connect(self.db_dir)
        self.table_name = "match_chunks"

    def _table_exists(self) -> bool:
        try:
            names = set(self.db.table_names())
        except Exception:
            # Older lancedb might expose .table_names as list
            names = set(list(self.db.table_names()))
        return self.table_name in names

    @property
    def table(self):
        # Prefer explicit open through method below to avoid opening before creation.
        return self.db.open_table(self.table_name)

    def upsert_chunks(self, rows: Iterable[Dict[str, Any]]) -> int:
        rows_list = list(rows)
        if not rows_list:
            return 0
        # Create table on first insert so schema is inferred from data
        if not self._table_exists():
            self.db.create_table(self.table_name, data=rows_list)
        else:
            self.table.add(rows_list)
        return len(rows_list)

    def search(
        self,
        embedding: List[float],
        match_id: str,
        k: int = 8,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Vector search scoped by match_id with optional metadata filters.
        """
        if not self._table_exists():
            return []
        q = self.table.search(embedding).metric("cosine").limit(k)
        q = q.where(f"match_id = '{match_id}'")
        if filters:
            for key, val in filters.items():
                if val is None:
                    continue
                # Basic equality filters
                if isinstance(val, str):
                    q = q.where(f"{key} = '{val}'")
                else:
                    q = q.where(f"{key} = {val}")
        results = q.to_list()
        return results


