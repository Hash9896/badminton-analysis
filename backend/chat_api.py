from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI  # type: ignore

from .config import settings
from .indexer import build_match_index
from .retrieval import Retriever
from . import tools as domain_tools


app = FastAPI(title="Match Analysis Chat API", version="0.1.0")

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IndexRequest(BaseModel):
    match_id: str
    # Absolute or relative to repo root; when omitted, resolve under DATA_ROOT_DIR/match_id
    match_dir: Optional[str] = None


class SearchRequest(BaseModel):
    match_id: str
    query: str
    k: int = 8
    filters: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    match_id: str
    message: str
    k: int = 6
    # Optional: allow client to hint a specific tool call
    tool_hint: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "model": settings.chat_model, "embedding_model": settings.embedding_model}


@app.post("/index")
def index_match(req: IndexRequest) -> Dict[str, Any]:
    # Resolve match_dir
    if req.match_dir:
        match_dir = req.match_dir
    else:
        # Allow `Aikya/1` style match_id -> join under data root
        match_dir = os.path.join(settings.data_root_dir, req.match_id)
    if not os.path.isdir(match_dir):
        raise HTTPException(status_code=400, detail=f"match_dir not found: {match_dir}")
    res = build_match_index(match_id=req.match_id, match_dir=match_dir)
    return res


@app.post("/search")
def search(req: SearchRequest) -> Dict[str, Any]:
    retriever = Retriever()
    results = retriever.search(req.match_id, req.query, k=req.k, filters=req.filters or {})
    return {"hits": results}


SYSTEM_PROMPT = (
    "You are a badminton match analysis assistant. Only answer questions using the provided retrieved context, "
    "which is strictly scoped to the active match. Always cite sources with file_path and optional rally_id. "
    "If the context is insufficient to answer, say what is missing and ask a clarifying question."
)


@app.post("/chat")
def chat(req: ChatRequest) -> Dict[str, Any]:
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")
    retriever = Retriever()

    # Heuristic tool routing before retrieval (simple, non-LLM)
    lower_q = req.message.lower()
    tool_result: Optional[Dict[str, Any]] = None
    tool_used: Optional[str] = None
    try:
        if req.tool_hint == "get_errors" or ("error" in lower_q and ("p0" in lower_q or "p1" in lower_q)):
            player = "P0" if "p0" in lower_q else ("P1" if "p1" in lower_q else (req.tool_args or {}).get("player"))
            tool_result = domain_tools.get_errors(req.match_id, player=player or "P0")
            tool_used = "get_errors"
        elif req.tool_hint == "get_winners" or ("winner" in lower_q and ("p0" in lower_q or "p1" in lower_q)):
            player = "P0" if "p0" in lower_q else ("P1" if "p1" in lower_q else (req.tool_args or {}).get("player"))
            tool_result = domain_tools.get_winners(req.match_id, player=player or "P0")
            tool_used = "get_winners"
        elif req.tool_hint == "get_winning_losing_rallies" or (("losing" in lower_q or "winning" in lower_q) and ("rallies" in lower_q or "rally" in lower_q)):
            player = "P0" if "p0" in lower_q else ("P1" if "p1" in lower_q else (req.tool_args or {}).get("player"))
            outcome = "winning" if "winning" in lower_q else ("losing" if "losing" in lower_q else (req.tool_args or {}).get("outcome"))
            tool_result = domain_tools.get_winning_losing_rallies(req.match_id, player=player or "P0", outcome=outcome or "winning")
            tool_used = "get_winning_losing_rallies"
        elif req.tool_hint == "get_sr_patterns" or ("serve" in lower_q and "receive" in lower_q):
            player = "P0" if "p0" in lower_q else ("P1" if "p1" in lower_q else (req.tool_args or {}).get("player"))
            tool_result = domain_tools.get_sr_patterns(req.match_id, player=player or "P1")
            tool_used = "get_sr_patterns"
        elif req.tool_hint == "get_three_shot_sequences" or ("3-shot" in lower_q or "three-shot" in lower_q or "three shot" in lower_q):
            tool_result = domain_tools.get_three_shot_sequences(req.match_id)
            tool_used = "get_three_shot_sequences"
        elif req.tool_hint == "get_zone_effectiveness" or ("zone" in lower_q and "effect" in lower_q):
            player = "P0" if "p0" in lower_q else ("P1" if "p1" in lower_q else None)
            tool_result = domain_tools.get_zone_effectiveness(req.match_id, player=player)
            tool_used = "get_zone_effectiveness"
        else:
            # Rally id detection e.g., R23
            import re as _re
            m = _re.search(r"(?:g\d+-)?r\d+", lower_q)
            if req.tool_hint == "get_rally" or m:
                rid = (req.tool_args or {}).get("rally_id") or (m.group(0).upper() if m else None)
                if rid:
                    tool_result = domain_tools.get_rally(req.match_id, rally_id=rid)
                    tool_used = "get_rally"
    except Exception as te:
        tool_result = {"error": str(te)}

    # Build context
    hits = retriever.search(req.match_id, req.message, k=req.k)
    context_blocks: List[str] = []
    if tool_result is not None:
        context_blocks.append(f"[tool: {tool_used or 'unknown'}]\n{json.dumps(tool_result)[:8000]}")
    for h in hits:
        file_path = h.get("file_path", "?")
        rally_id = h.get("rally_id")
        text = h.get("text", "")
        header = f"[source: {file_path}" + (f", rally: {rally_id}]" if rally_id else "]")
        context_blocks.append(f"{header}\n{text}")
    context_text = "\n\n---\n\n".join(context_blocks[: req.k])

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        completion = client.chat.completions.create(
            model=settings.chat_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Context (retrieved, do not invent beyond this):\n{context_text}\n\n"
                    f"User question: {req.message}\n\n"
                    "Instructions:\n"
                    "- Answer concisely.\n"
                    "- Include a short list of key points with numbers.\n"
                    "- Add a Sources section with [file_path, rally_id if available].",
                },
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    answer = completion.choices[0].message.content if completion.choices else ""  # type: ignore
    return {
        "answer": answer,
        "hits": hits,
        "model": settings.chat_model,
        "tool_used": tool_used,
        "tool_result_excerpt": (json.dumps(tool_result)[:5000] if tool_result is not None else None),
    }

# -------------------- Tool Endpoints --------------------

from fastapi import Query


@app.get("/tools/errors")
def api_get_errors(match_id: str, player: str, zone: Optional[str] = None, stroke: Optional[str] = None,
                   rally_start: Optional[int] = Query(None), rally_end: Optional[int] = Query(None)) -> Dict[str, Any]:
    return domain_tools.get_errors(match_id, player, zone, stroke, rally_start, rally_end)


@app.get("/tools/winners")
def api_get_winners(match_id: str, player: str, zone: Optional[str] = None, stroke: Optional[str] = None,
                    rally_start: Optional[int] = Query(None), rally_end: Optional[int] = Query(None)) -> Dict[str, Any]:
    return domain_tools.get_winners(match_id, player, zone, stroke, rally_start, rally_end)


@app.get("/tools/winning_losing_rallies")
def api_get_winning_losing_rallies(match_id: str, player: str, outcome: str) -> Dict[str, Any]:
    return domain_tools.get_winning_losing_rallies(match_id, player, outcome)


@app.get("/tools/sr_patterns")
def api_get_sr_patterns(match_id: str, player: str) -> Dict[str, Any]:
    return domain_tools.get_sr_patterns(match_id, player)


@app.get("/tools/three_shot")
def api_get_three_shot(match_id: str, sequence_contains: Optional[str] = None, player: Optional[str] = None) -> Dict[str, Any]:
    return domain_tools.get_three_shot_sequences(match_id, sequence_contains, player)


@app.get("/tools/zone_effectiveness")
def api_get_zone_effectiveness(match_id: str, player: Optional[str] = None, zone: Optional[str] = None) -> Dict[str, Any]:
    return domain_tools.get_zone_effectiveness(match_id, player, zone)


@app.get("/tools/shot_distribution")
def api_get_shot_distribution(match_id: str, player: Optional[str] = None, group_by: Optional[str] = None) -> Dict[str, Any]:
    return domain_tools.get_shot_distribution(match_id, player, group_by)


@app.get("/tools/rally")
def api_get_rally(match_id: str, rally_id: str) -> Dict[str, Any]:
    return domain_tools.get_rally(match_id, rally_id)


@app.get("/tools/events_by_time")
def api_get_events_by_time(match_id: str, start_s: float, end_s: float) -> Dict[str, Any]:
    return domain_tools.get_events_by_time(match_id, start_s, end_s)


