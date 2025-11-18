from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd  # type: ignore
from openai import OpenAI  # type: ignore

from .config import settings
from .lance_store import LanceStore


def _file_iter(root_dir: str) -> Iterable[Tuple[str, str]]:
    """
    Yield (abs_path, rel_path_from_root) for files under root_dir.
    """
    for base, _dirs, files in os.walk(root_dir):
        for f in files:
            if f.startswith("."):
                continue
            abs_path = os.path.join(base, f)
            rel_path = os.path.relpath(abs_path, root_dir)
            yield abs_path, rel_path


def _chunk_text(text: str, max_chars: int = 3000, overlap: int = 300) -> List[str]:
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= n:
            break
        start = end - overlap
        if start < 0:
            start = 0
    return chunks


def _normalize_json_to_text(obj: Any) -> str:
    """
    Produce a compact but readable text from arbitrary JSON for retrieval.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        return str(obj)


def _csv_to_text_rows(abs_path: str, limit_rows: int = 2000) -> List[str]:
    try:
        df = pd.read_csv(abs_path)
    except Exception:
        return []
    # Convert each row to key=value pairs
    texts: List[str] = []
    for idx, row in df.head(limit_rows).iterrows():
        parts = []
        for col in df.columns:
            val = row[col]
            parts.append(f"{col}={val}")
        texts.append("; ".join(parts))
    return texts


def _detect_source_type(filename: str) -> str:
    lower = filename.lower()
    if "narrative" in lower:
        return "narrative"
    if "timeseries" in lower:
        return "timeseries"
    if "summary" in lower or "report" in lower:
        return "summary"
    if "effectiveness" in lower or "zone" in lower or "distribution" in lower:
        return "stat"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".txt"):
        return "text"
    return "other"


def _hash_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _infer_rally_id_from_text(text: str) -> Optional[str]:
    # Very loose heuristic (G1-R5, R123, etc.)
    # We avoid heavy parsing for speed.
    import re
    m = re.search(r"(?:G\d+-)?R\d+", text)
    return m.group(0) if m else None


def build_match_index(match_id: str, match_dir: str, store: Optional[LanceStore] = None) -> Dict[str, Any]:
    """
    Build embeddings and index chunks for a given match folder.
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment.")

    client = OpenAI(api_key=settings.openai_api_key)
    store = store or LanceStore()

    rows_to_upsert: List[Dict[str, Any]] = []

    for abs_path, rel_path in _file_iter(match_dir):
        filename = os.path.basename(abs_path)
        source_type = _detect_source_type(filename)
        # Extract text chunks
        text_chunks: List[str] = []
        if filename.lower().endswith(".txt"):
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
            except Exception:
                txt = ""
            text_chunks = _chunk_text(txt)
        elif filename.lower().endswith(".json"):
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
            except Exception:
                data = None
            txt = _normalize_json_to_text(data)
            text_chunks = _chunk_text(txt)
        elif filename.lower().endswith(".csv"):
            rows_text = _csv_to_text_rows(abs_path)
            # Group rows into chunks
            buffer = []
            current_len = 0
            max_chars = 3000
            for t in rows_text:
                if current_len + len(t) + 1 > max_chars:
                    if buffer:
                        text_chunks.append("\n".join(buffer))
                        buffer = []
                        current_len = 0
                buffer.append(t)
                current_len += len(t) + 1
            if buffer:
                text_chunks.append("\n".join(buffer))
        else:
            # Skip videos and unknowns
            continue

        # Embed and stage rows
        for i, chunk_text in enumerate(text_chunks):
            chunk_id = _hash_id(f"{match_id}|{rel_path}|{i}|{len(chunk_text)}")
            rally_id = _infer_rally_id_from_text(chunk_text)
            rows_to_upsert.append(
                {
                    "chunk_id": chunk_id,
                    "match_id": match_id,
                    "file_path": rel_path,
                    "source_type": source_type,
                    "rally_id": rally_id,
                    "text": chunk_text,
                }
            )

    # Batch in groups for embeddings
    BATCH = 64
    embedded_rows: List[Dict[str, Any]] = []
    for start in range(0, len(rows_to_upsert), BATCH):
        batch = rows_to_upsert[start : start + BATCH]
        if not batch:
            continue
        inputs = [r["text"] for r in batch]
        emb = client.embeddings.create(model=settings.embedding_model, input=inputs)
        vectors = [d.embedding for d in emb.data]  # type: ignore
        for row, vec in zip(batch, vectors):
            row["vector"] = vec
            embedded_rows.append(row)

    upserted = store.upsert_chunks(embedded_rows)
    return {"match_id": match_id, "chunks_indexed": upserted}


