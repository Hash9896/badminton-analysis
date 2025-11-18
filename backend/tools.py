from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd  # type: ignore

from .config import settings


def _resolve_match_dir(match_id: str, override_dir: Optional[str] = None) -> str:
    if override_dir:
        return override_dir
    return os.path.join(settings.data_root_dir, match_id)


def _read_csv_safe(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _read_json_safe(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def _filter_contains(df: pd.DataFrame, column_candidates: List[str], value_substring: str) -> pd.DataFrame:
    if df.empty or not value_substring:
        return df
    value = str(value_substring).strip().lower()
    for col in df.columns:
        lc = col.lower()
        if any(key in lc for key in column_candidates):
            try:
                mask = df[col].astype(str).str.lower().str.contains(value, na=False)
                df = df[mask]
            except Exception:
                pass
    return df


def _filter_equals(df: pd.DataFrame, column_candidates: List[str], value: Any) -> pd.DataFrame:
    if df.empty:
        return df
    for col in df.columns:
        lc = col.lower()
        if any(key in lc for key in column_candidates):
            try:
                df = df[df[col].astype(str).str.lower() == str(value).lower()]
            except Exception:
                pass
    return df


def _filter_between_int(df: pd.DataFrame, column_candidates: List[str], start: Optional[int], end: Optional[int]) -> pd.DataFrame:
    if df.empty or (start is None and end is None):
        return df
    for col in df.columns:
        lc = col.lower()
        if any(key in lc for key in column_candidates):
            try:
                s = pd.to_numeric(df[col], errors="coerce")
                if start is not None:
                    df = df[s >= start]
                if end is not None:
                    df = df[s <= end]
            except Exception:
                pass
    return df


# -------------------- Tool Implementations --------------------

def get_errors(match_id: str, player: str, zone: Optional[str] = None, stroke: Optional[str] = None,
               rally_start: Optional[int] = None, rally_end: Optional[int] = None,
               match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    player = (player or "").strip().upper()
    fname = "P0_errors.csv" if player == "P0" else "P1_errors.csv"
    path = os.path.join(base, fname)
    df = _read_csv_safe(path)
    if df.empty:
        return {"rows": [], "source": path}
    if zone:
        df = _filter_contains(df, ["zone", "hittingzone"], zone)
    if stroke:
        df = _filter_contains(df, ["stroke", "shot", "shotcategory"], stroke)
    df = _filter_between_int(df, ["rally"], rally_start, rally_end)
    rows = df.head(200).to_dict(orient="records")
    return {"rows": rows, "source": path}


def get_winners(match_id: str, player: str, zone: Optional[str] = None, stroke: Optional[str] = None,
                rally_start: Optional[int] = None, rally_end: Optional[int] = None,
                match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    player = (player or "").strip().upper()
    fname = "P0_winners.csv" if player == "P0" else "P1_winners.csv"
    path = os.path.join(base, fname)
    df = _read_csv_safe(path)
    if df.empty:
        return {"rows": [], "source": path}
    if zone:
        df = _filter_contains(df, ["zone", "hittingzone", "landing"], zone)
    if stroke:
        df = _filter_contains(df, ["stroke", "shot", "shotcategory"], stroke)
    df = _filter_between_int(df, ["rally"], rally_start, rally_end)
    rows = df.head(200).to_dict(orient="records")
    return {"rows": rows, "source": path}


def get_winning_losing_rallies(match_id: str, player: str, outcome: str,
                               match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    player = (player or "").strip().upper()
    outcome = (outcome or "").strip().lower()
    if outcome not in {"winning", "losing"}:
        return {"rows": [], "source": None, "error": "outcome must be 'winning' or 'losing'"}
    fname = f"{player}_{'winning' if outcome=='winning' else 'losing'}_rallies.csv"
    path = os.path.join(base, fname)
    df = _read_csv_safe(path)
    rows = df.head(400).to_dict(orient="records") if not df.empty else []
    return {"rows": rows, "source": path}


def get_sr_patterns(match_id: str, player: str, match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    player = (player or "").strip().upper()
    fname = f"{player}_SR_Patterns.csv"
    path = os.path.join(base, fname)
    df = _read_csv_safe(path)
    rows = df.to_dict(orient="records") if not df.empty else []
    return {"rows": rows, "source": path}


def get_three_shot_sequences(match_id: str, sequence_contains: Optional[str] = None, player: Optional[str] = None,
                             match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    path = os.path.join(base, "Aikya1_clip1_3shot.csv")
    df = _read_csv_safe(path)
    if df.empty:
        return {"rows": [], "source": path}
    if sequence_contains:
        df = _filter_contains(df, ["sequence"], sequence_contains)
    if player:
        df = _filter_contains(df, ["player"], player)
    rows = df.head(200).to_dict(orient="records")
    return {"rows": rows, "source": path}


def get_zone_effectiveness(match_id: str, player: Optional[str] = None, zone: Optional[str] = None,
                           match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    path = os.path.join(base, "Aikya1_clip1_detailed_effectiveness.csv")
    df = _read_csv_safe(path)
    if df.empty:
        return {"rows": [], "source": path}
    if player:
        df = _filter_equals(df, ["player"], player)
    if zone:
        df = _filter_contains(df, ["zone", "hittingzone", "anchorhittingzone"], zone)
    rows = df.head(400).to_dict(orient="records")
    return {"rows": rows, "source": path}


def get_shot_distribution(match_id: str, player: Optional[str] = None, group_by: Optional[str] = None,
                          match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    # Prefer explicit distribution file; otherwise fallback enriched shots
    path_primary = os.path.join(base, "Aikya1_clip1_shot_distribution.csv")
    path_fallback = os.path.join(base, "rally_narratives_enriched_with_shots.csv")
    df = _read_csv_safe(path_primary)
    source = path_primary
    if df.empty:
        df = _read_csv_safe(path_fallback)
        source = path_fallback
    if df.empty:
        return {"rows": [], "source": None}
    if player:
        df = _filter_equals(df, ["player"], player)
    # group_by: best-effort; user may pass 'zone', 'shot', 'direction'
    if group_by:
        # Find first column that matches group_by
        target_col = None
        for col in df.columns:
            if group_by.lower() in col.lower():
                target_col = col
                break
        if target_col:
            agg = df.groupby(target_col, dropna=False).size().reset_index(name="count")
            rows = agg.sort_values("count", ascending=False).to_dict(orient="records")
            return {"rows": rows, "source": source, "group_by": target_col}
    rows = df.head(400).to_dict(orient="records")
    return {"rows": rows, "source": source}


def get_rally(match_id: str, rally_id: str, match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    # Try frame map first
    fm_path = os.path.join(base, "rally_narratives_frame_map.csv")
    fm = _read_csv_safe(fm_path)
    fm_rows: List[Dict[str, Any]] = []
    if not fm.empty:
        for col in fm.columns:
            if "rally" in col.lower():
                fm_rows = fm[fm[col].astype(str) == str(rally_id)].to_dict(orient="records")
                break
    # Pull narrative
    rn_path = os.path.join(base, "rally_narratives.csv")
    rn = _read_csv_safe(rn_path)
    rn_rows: List[Dict[str, Any]] = []
    if not rn.empty:
        for col in rn.columns:
            if "rally" in col.lower():
                rn_rows = rn[rn[col].astype(str) == str(rally_id)].to_dict(orient="records")
                break
    # Detailed csv for last shot/outcome if possible
    det_path = os.path.join(base, "Aikya1_clip1_detailed.csv")
    det = _read_csv_safe(det_path)
    det_rows: List[Dict[str, Any]] = []
    if not det.empty:
        # Best-effort: find rally column
        rcol = None
        for col in det.columns:
            if "rally" in col.lower():
                rcol = col
                break
        if rcol:
            det_rows = det[det[rcol].astype(str) == str(rally_id)].to_dict(orient="records")
    # Attempt to infer start/end frames from frame-map-like columns
    start_frame = None
    end_frame = None
    if fm_rows:
        cand = fm_rows[0]
        for k, v in cand.items():
            lk = str(k).lower()
            if "startframe" in lk or "start_frame" in lk or "firstframe" in lk:
                start_frame = v
            if "endframe" in lk or "end_frame" in lk or "lastframe" in lk:
                end_frame = v
    return {
        "rally_id": rally_id,
        "summary_rows": rn_rows,
        "frame_map_rows": fm_rows,
        "detailed_rows": det_rows[:200],
        "start_frame": start_frame,
        "end_frame": end_frame,
        "sources": [p for p in [rn_path, fm_path, det_path] if os.path.exists(p)],
    }


def get_events_by_time(match_id: str, start_s: float, end_s: float,
                       match_dir_override: Optional[str] = None) -> Dict[str, Any]:
    base = _resolve_match_dir(match_id, match_dir_override)
    eff_path = os.path.join(base, "Aikya1_clip1_detailed_effectiveness.csv")
    df = _read_csv_safe(eff_path)
    if df.empty:
        return {"rows": [], "source": eff_path}
    # Find a time-like column
    time_col = None
    for col in df.columns:
        lc = col.lower()
        if "time" in lc or "timestamp" in lc or lc.endswith("_s"):
            time_col = col
            break
    if not time_col:
        return {"rows": [], "source": eff_path, "warning": "no time column detected"}
    ts = pd.to_numeric(df[time_col], errors="coerce")
    window = df[(ts >= float(start_s)) & (ts <= float(end_s))]
    rows = window.head(400).to_dict(orient="records")
    return {"rows": rows, "source": eff_path, "time_column": time_col}


