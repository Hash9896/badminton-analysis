#!/usr/bin/env python3
"""
Compute tempo metrics from *_detailed.csv without touching rally_timeseries.json.

Core outputs (written next to the input CSV by default):
- <name>_tempo_events.csv           : per-shot response metrics and classifications
- <name>_tempo_thresholds.json      : per-combo thresholds and baselines
- <name>_tempo_rally_summary.csv    : per-rally, per-player aggregates (median, fast/slow counts)
- <name>_tempo_combo_stats.csv      : per-combo stats in a flat CSV

Definitions:
- response_time_sec: time between the opponent's previous shot and the current shot.
  For event k by player X with previous opponent event j: (FrameNumber[k] - FrameNumber[j]) / fps
- combo key: (responder_player, opponent_prev_stroke, responder_stroke)

Thresholding:
- Prefer per-combo percentiles (p10/p90). If insufficient samples, fallback to
  opponent-stroke-only (responder, opponent_prev_stroke, "*"). If still insufficient,
  fallback to player baseline (responder, "*", "*").
- Robust stats: report median and MAD alongside percentiles.

Usage:
  python3 build_tempo_analysis.py PATH/your_detailed.csv \
    --fps 30 --min-combo-n 30 --min-opp-stroke-n 30 \
    --lower-cap 0.15 --upper-cap 4.0
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Compute tempo metrics and classifications from *_detailed.csv")
    ap.add_argument("detailed_csv", type=str, help="Path to *_detailed.csv")
    ap.add_argument("--effectiveness-csv", type=str, default=None, help="Optional path to *_detailed_effectiveness.csv to enrich with shot effectiveness")
    ap.add_argument("--fps", type=float, default=30.0, help="Video FPS; used to convert frames to seconds (default: 30)")
    ap.add_argument("--lower-cap", type=float, default=0.15, help="Lower clamp for response times in seconds before stats (default: 0.15)")
    ap.add_argument("--upper-cap", type=float, default=4.0, help="Upper clamp for response times in seconds before stats (default: 4.0)")
    ap.add_argument("--min-combo-n", type=int, default=30, help="Min events to trust a specific combo (default: 30)")
    ap.add_argument("--min-opp-stroke-n", type=int, default=30, help="Min events to trust opponent-stroke-only fallback (default: 30)")
    ap.add_argument("--no-stroke-filter", action="store_true", help="Do not filter non-stroke annotation rows")
    # Effectiveness binning
    ap.add_argument("--eff-bin1", type=float, default=50.0, help="Lower split for effectiveness bins: low < bin1 (default: 50)")
    ap.add_argument("--eff-bin2", type=float, default=75.0, help="Upper split for effectiveness bins: mid < bin2 <= high (default: 75)")
    # Ineffective + slow mapping
    ap.add_argument("--ineff-threshold", type=float, default=50.0, help="Numeric effectiveness threshold for 'ineffective' when no color (default: 50)")
    ap.add_argument("--ineff-colors", type=str, default="darkred,red", help="CSV list of colors considered 'ineffective' (default: darkred,red)")
    ap.add_argument("--map-min-count", type=int, default=3, help="Minimum count to include a stroke/combo in maps (default: 3)")
    ap.add_argument("--include-serves", action="store_true", help="Include serve shots themselves (default: exclude serves; receives are always included)")
    # Standout & patterns tuning
    ap.add_argument("--standout-z", type=float, default=2.0, help="|z| threshold using baseline MAD to flag standout events (default: 2.0)")
    ap.add_argument("--pattern-min-n", type=int, default=30, help="Minimum count to consider a combo pattern (default: 30)")
    ap.add_argument("--pattern-rate", type=float, default=0.35, help="Fast/Slow rate threshold to flag combo patterns (default: 0.35)")
    ap.add_argument("--pattern-delta", type=float, default=0.15, help="Absolute delta vs player median (seconds) to flag combo patterns (default: 0.15)")
    ap.add_argument("--out-prefix", type=str, default=None, help="Custom output prefix (default: <csv_path_without_ext>)")
    return ap.parse_args()


def is_valid_stroke(stroke: Any) -> bool:
    """
    Heuristic: valid strokes in these CSVs usually use underscore tokens (e.g., 'forehand_smash').
    We treat spacey annotations like 'Lift height'/'feet position parallel' as invalid.
    Allow underscore presence OR select known service tokens.
    """
    try:
        s = str(stroke).strip()
    except Exception:
        return False
    if not s or s.lower() in ("nan", "none"):
        return False
    if "_" in s:
        return True
    # accept minimal known tokens if appear without underscores
    allow = {"serve", "smash", "clear", "drop", "defense", "net", "lift"}
    toks = s.lower().split()
    return any(tok in allow for tok in toks)


def safe_int(x: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        v = int(x)
        return v
    except Exception:
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


def mad(values: List[float], med: Optional[float] = None) -> Optional[float]:
    """Median absolute deviation."""
    if not values:
        return None
    m = med if med is not None else median(values)
    if m is None:
        return None
    abs_dev = [abs(v - m) for v in values]
    return median(abs_dev)


def percentile(values: List[float], q: float) -> Optional[float]:
    """q in [0,100]."""
    if not values:
        return None
    if q <= 0:
        return float(min(values))
    if q >= 100:
        return float(max(values))
    s = sorted(values)
    rank = (q / 100.0) * (len(s) - 1)
    low = int(rank)
    high = min(low + 1, len(s) - 1)
    weight = rank - low
    return float(s[low] * (1.0 - weight) + s[high] * weight)


@dataclass
class ComboStats:
    count: int
    median: Optional[float]
    p10: Optional[float]
    p90: Optional[float]
    mad: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "median": self.median,
            "p10": self.p10,
            "p90": self.p90,
            "mad": self.mad,
        }


def compute_stats(values: List[float]) -> ComboStats:
    med = median(values)
    return ComboStats(
        count=len(values),
        median=med,
        p10=percentile(values, 10.0),
        p90=percentile(values, 90.0),
        mad=mad(values, med),
    )


def build_rally_id(df: pd.DataFrame) -> pd.Series:
    if "rally_id" in df.columns:
        return df["rally_id"].astype(str)
    return df["GameNumber"].astype(str) + "_" + df["RallyNumber"].astype(str) + "_seg1"


def extract_events_with_response_times(
    df: pd.DataFrame,
    fps: float,
    filter_strokes: bool,
    eff_map: Optional[Dict[Tuple[int, int, int, str], Optional[float]]] = None,
    eff_bin1: float = 50.0,
    eff_bin2: float = 75.0,
    eff_color_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None,
    eff_label_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None,
    eff_reason_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None,
    is_serve_map: Optional[Dict[Tuple[int, int, int, str], Optional[bool]]] = None,
    eff_zone_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None,
) -> pd.DataFrame:
    """
    Returns a DataFrame with one row per original shot event and columns:
      GameNumber, RallyNumber, StrokeNumber, FrameNumber, Player, Stroke, rally_id,
      opp_prev_frame, opp_prev_stroke, response_time_sec_raw, response_time_sec,
      self_prev_frame, self_cycle_time_sec
    """
    required = ["GameNumber", "RallyNumber", "StrokeNumber", "FrameNumber", "Player", "Stroke"]
    for col in required:
        if col not in df.columns:
            raise RuntimeError(f"Missing required column: {col}")
    df = df.copy()
    df["rally_id"] = build_rally_id(df)
    df = df.sort_values(["GameNumber", "RallyNumber", "StrokeNumber"])
    if filter_strokes:
        df = df[df["Stroke"].map(is_valid_stroke)]
    # Keep only rows with numeric FrameNumber
    df = df[pd.to_numeric(df["FrameNumber"], errors="coerce").notna()].copy()
    df["FrameNumber"] = df["FrameNumber"].astype(int)

    def bin_eff(val: Optional[float]) -> Optional[str]:
        if val is None:
            return None
        try:
            v = float(val)
        except Exception:
            return None
        if v < eff_bin1:
            return "low"
        if v <= eff_bin2:
            return "mid"
        return "high"

    records: List[Dict[str, Any]] = []
    for rid, g in df.groupby("rally_id", sort=False):
        g = g.sort_values("StrokeNumber")
        last_frame: Dict[str, Optional[int]] = {"P0": None, "P1": None}
        last_stroke: Dict[str, Optional[str]] = {"P0": None, "P1": None}
        last_eff: Dict[str, Optional[float]] = {"P0": None, "P1": None}
        last_color: Dict[str, Optional[str]] = {"P0": None, "P1": None}
        last_zone: Dict[str, Optional[str]] = {"P0": None, "P1": None}
        for _, r in g.iterrows():
            player = str(r["Player"])
            if player not in ("P0", "P1"):
                # Skip unknown players
                continue
            opponent = "P1" if player == "P0" else "P0"
            frame = safe_int(r["FrameNumber"])
            if frame is None:
                continue
            opp_prev_frame = last_frame[opponent]
            opp_prev_stroke = last_stroke[opponent]
            opp_prev_eff = last_eff[opponent]
            self_prev_frame = last_frame[player]

            response_time_sec_raw: Optional[float] = None
            if opp_prev_frame is not None:
                response_time_sec_raw = (frame - opp_prev_frame) / (fps if fps > 0 else 30.0)
            self_cycle_time_sec: Optional[float] = None
            if self_prev_frame is not None:
                self_cycle_time_sec = (frame - self_prev_frame) / (fps if fps > 0 else 30.0)

            # Current shot effectiveness from map, if provided
            key = (int(r["GameNumber"]), int(r["RallyNumber"]), int(r["StrokeNumber"]), player)
            eff_cur = eff_map.get(key) if eff_map else None
            eff_color = eff_color_map.get(key) if eff_color_map else None
            eff_label = eff_label_map.get(key) if eff_label_map else None
            eff_reason = eff_reason_map.get(key) if eff_reason_map else None
            is_serve_flag = is_serve_map.get(key) if is_serve_map else None
            eff_zone = eff_zone_map.get(key) if eff_zone_map else None

            rec = {
                "GameNumber": int(r["GameNumber"]),
                "RallyNumber": int(r["RallyNumber"]),
                "StrokeNumber": int(r["StrokeNumber"]),
                "FrameNumber": int(r["FrameNumber"]),
                "time_sec": (int(r["FrameNumber"]) / (fps if fps > 0 else 30.0)),
                "Player": player,
                "Stroke": str(r["Stroke"]),
                "rally_id": str(rid),
                "opp_prev_frame": opp_prev_frame,
                "opp_prev_stroke": opp_prev_stroke,
                "incoming_eff": opp_prev_eff,
                "incoming_eff_bin": bin_eff(opp_prev_eff),
                "incoming_color": (last_color[opponent].lower() if last_color[opponent] else None),
                "opp_prev_zone": last_zone[opponent],
                "resp_zone": eff_zone,
                "effectiveness": eff_cur,
                "effectiveness_color": (str(eff_color).lower() if eff_color is not None else None),
                "effectiveness_label": (str(eff_label) if eff_label is not None else None),
                "effectiveness_reason": (str(eff_reason) if eff_reason is not None else None),
                "is_serve": bool(is_serve_flag) if is_serve_flag is not None else (("serve" in str(r["Stroke"]).lower())),
                "response_time_sec_raw": response_time_sec_raw,
                "self_prev_frame": self_prev_frame,
                "self_cycle_time_sec": self_cycle_time_sec,
            }
            records.append(rec)

            last_frame[player] = frame
            last_stroke[player] = str(r["Stroke"])
            last_eff[player] = eff_cur
            last_color[player] = (str(eff_color).lower() if eff_color is not None else None)
            last_zone[player] = eff_zone

    return pd.DataFrame.from_records(records)


def build_combo_keys(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds columns:
      combo_key: 'P0|opp:<opp_stroke>|resp:<stroke>' for events with response_time defined, else None
      opp_only_key: 'P0|opp:<opp_stroke>|resp:*' if opp_prev_stroke defined
      combo_key_q: same as combo_key but suffixed with '|q:<bin>' if incoming_eff_bin exists
      opp_only_key_q: same with '|q:<bin>'
    """
    df = df.copy()
    keys: List[Optional[str]] = []
    opp_only: List[Optional[str]] = []
    keys_q: List[Optional[str]] = []
    opp_only_q: List[Optional[str]] = []
    for _, r in df.iterrows():
        player = r["Player"]
        opp_stroke = r.get("opp_prev_stroke")
        resp_stroke = r.get("Stroke")
        qbin = r.get("incoming_eff_bin")
        if pd.isna(player) or pd.isna(resp_stroke) or player not in ("P0", "P1"):
            keys.append(None)
            opp_only.append(None)
            keys_q.append(None)
            opp_only_q.append(None)
            continue
        if pd.isna(opp_stroke):
            keys.append(None)
            opp_only.append(None)
            keys_q.append(None)
            opp_only_q.append(None)
            continue
        k = f"{player}|opp:{opp_stroke}|resp:{resp_stroke}"
        keys.append(k)
        opp_only.append(f"{player}|opp:{opp_stroke}|resp:*")
        if pd.notna(qbin):
            kq = f"{k}|q:{qbin}"
            oq = f"{player}|opp:{opp_stroke}|q:{qbin}"
            keys_q.append(kq)
            opp_only_q.append(oq)
        else:
            keys_q.append(None)
            opp_only_q.append(None)
    df["combo_key"] = keys
    df["opp_only_key"] = opp_only
    df["combo_key_q"] = keys_q
    df["opp_only_key_q"] = opp_only_q
    return df


def build_thresholds(
    df_events: pd.DataFrame,
    lower_cap: float,
    upper_cap: float,
    min_combo_n: int,
    min_opp_stroke_n: int,
) -> Tuple[Dict[str, ComboStats], Dict[str, ComboStats], Dict[str, ComboStats], Dict[str, ComboStats], Dict[str, ComboStats], Dict[str, ComboStats]]:
    """
    Returns:
      combo_stats: map of combo_key -> ComboStats
      opp_only_stats: map of opp_only_key -> ComboStats
      baseline_stats: map of player ('P0'/'P1') -> ComboStats
    """
    # Prepare series of clamped response times
    df_valid = df_events[pd.to_numeric(df_events["response_time_sec_raw"], errors="coerce").notna()].copy()
    df_valid["rt_clamped"] = df_valid["response_time_sec_raw"].astype(float).clip(lower=lower_cap, upper=upper_cap)

    # per-combo
    combo_stats: Dict[str, ComboStats] = {}
    for k, g in df_valid.groupby("combo_key"):
        if k is None:
            continue
        vals = g["rt_clamped"].tolist()
        combo_stats[k] = compute_stats(vals)

    # quality-conditioned per-combo (if bin exists)
    combo_stats_q: Dict[str, ComboStats] = {}
    if "combo_key_q" in df_valid.columns:
        for k, g in df_valid.groupby("combo_key_q"):
            if k is None:
                continue
            vals = g["rt_clamped"].tolist()
            combo_stats_q[k] = compute_stats(vals)

    # opponent-only
    opp_only_stats: Dict[str, ComboStats] = {}
    for k, g in df_valid.groupby("opp_only_key"):
        if k is None:
            continue
        vals = g["rt_clamped"].tolist()
        opp_only_stats[k] = compute_stats(vals)

    # quality-conditioned opponent-only
    opp_only_stats_q: Dict[str, ComboStats] = {}
    if "opp_only_key_q" in df_valid.columns:
        for k, g in df_valid.groupby("opp_only_key_q"):
            if k is None:
                continue
            vals = g["rt_clamped"].tolist()
            opp_only_stats_q[k] = compute_stats(vals)

    # baselines per player
    baseline_stats: Dict[str, ComboStats] = {}
    for player, g in df_valid.groupby("Player"):
        vals = g["rt_clamped"].tolist()
        baseline_stats[player] = compute_stats(vals)

    # baselines per player per quality bin
    baseline_stats_q: Dict[str, ComboStats] = {}
    if "incoming_eff_bin" in df_valid.columns:
        for (player, q), g in df_valid.groupby(["Player", "incoming_eff_bin"]):
            if pd.isna(q):
                continue
            vals = g["rt_clamped"].tolist()
            baseline_stats_q[f"{player}|q:{q}"] = compute_stats(vals)

    # Enforce minimum counts by nulling out thresholds below sample sizes
    def null_if_insufficient(stats_map: Dict[str, ComboStats], min_count: int) -> None:
        for key, st in stats_map.items():
            if st.count < min_count:
                # keep count for transparency, but null thresholds
                stats_map[key] = ComboStats(count=st.count, median=st.median, p10=None, p90=None, mad=st.mad)

    null_if_insufficient(combo_stats, min_combo_n)
    null_if_insufficient(combo_stats_q, min_combo_n)
    null_if_insufficient(opp_only_stats, min_opp_stroke_n)
    null_if_insufficient(opp_only_stats_q, min_opp_stroke_n)
    # baseline no minimum required
    return combo_stats, opp_only_stats, baseline_stats, combo_stats_q, opp_only_stats_q, baseline_stats_q


def choose_threshold_for_event(
    player: str,
    combo_key: Optional[str],
    opp_only_key: Optional[str],
    incoming_eff_bin: Optional[str],
    combo_stats: Dict[str, ComboStats],
    opp_only_stats: Dict[str, ComboStats],
    baseline_stats: Dict[str, ComboStats],
    combo_stats_q: Optional[Dict[str, ComboStats]] = None,
    opp_only_stats_q: Optional[Dict[str, ComboStats]] = None,
    baseline_stats_q: Optional[Dict[str, ComboStats]] = None,
) -> Tuple[Optional[float], Optional[float], str]:
    """
    Returns (fast_threshold, slow_threshold, source)
    source in {"combo", "opp_only", "baseline", "none"}
    """
    # prefer combo with quality bin
    if incoming_eff_bin and combo_stats_q is not None and combo_key is not None:
        st = combo_stats_q.get(f"{combo_key}|q:{incoming_eff_bin}")
        if st and st.p10 is not None and st.p90 is not None:
            return st.p10, st.p90, "combo_q"
    # fallback: opponent-only with quality bin
    if incoming_eff_bin and opp_only_stats_q is not None and opp_only_key is not None:
        st = opp_only_stats_q.get(f"{opp_only_key}|q:{incoming_eff_bin}")
        if st and st.p10 is not None and st.p90 is not None:
            return st.p10, st.p90, "opp_only_q"
    # fallback: baseline with quality bin
    if incoming_eff_bin and baseline_stats_q is not None:
        st = baseline_stats_q.get(f"{player}|q:{incoming_eff_bin}")
        if st and st.p10 is not None and st.p90 is not None:
            return st.p10, st.p90, "baseline_q"
    # prefer combo
    if combo_key is not None:
        st = combo_stats.get(combo_key)
        if st and st.p10 is not None and st.p90 is not None:
            return st.p10, st.p90, "combo"
    # fallback to opponent-only
    if opp_only_key is not None:
        st = opp_only_stats.get(opp_only_key)
        if st and st.p10 is not None and st.p90 is not None:
            return st.p10, st.p90, "opp_only"
    # fallback to baseline
    st = baseline_stats.get(player)
    if st and st.p10 is not None and st.p90 is not None:
        return st.p10, st.p90, "baseline"
    return None, None, "none"


def classify_event(
    value: Optional[float],
    fast_th: Optional[float],
    slow_th: Optional[float],
) -> Optional[str]:
    if value is None or fast_th is None or slow_th is None:
        return None
    if value <= fast_th:
        return "fast"
    if value >= slow_th:
        return "slow"
    return "normal"


def compute_zscore(value: Optional[float], base: Optional[ComboStats]) -> Optional[float]:
    if value is None or base is None or base.median is None or base.mad is None or base.mad == 0:
        return None
    return (value - base.median) / base.mad


def summarize_by_rally(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates per rally_id and player:
      median_response_time_sec, fast_count, slow_count, normal_count, shots_with_response
    """
    df = df_events.copy()
    df = df[pd.to_numeric(df["response_time_sec"], errors="coerce").notna()].copy()
    summaries: List[Dict[str, Any]] = []
    for (rid, player), g in df.groupby(["rally_id", "Player"]):
        vals = g["response_time_sec"].astype(float).tolist()
        med = median(vals)
        fast_count = int((g["classification"] == "fast").sum())
        slow_count = int((g["classification"] == "slow").sum())
        normal_count = int((g["classification"] == "normal").sum())
        summaries.append({
            "rally_id": rid,
            "Player": player,
            "median_response_time_sec": med,
            "fast_count": fast_count,
            "normal_count": normal_count,
            "slow_count": slow_count,
            "shots_with_response": int(len(vals)),
        })
    return pd.DataFrame.from_records(summaries)


def get_stroke_role(stroke_raw: Any) -> str:
    """
    Classify responder role ('attacking' or 'defensive') based on stroke name.
    User override: net shots and placement drops are attacking.
    """
    s = str(stroke_raw or "").strip().lower().replace("-", "_")
    # Primary attacking sets
    attacking_tokens = (
        "smash", "halfsmash", "drive", "flat_game", "push", "nettap",
        "netkeep", "dribble", "drop"  # overrides: net shots + placement drops as attacking
    )
    for tok in attacking_tokens:
        if tok in s:
            return "attacking"
    return "defensive"


def summarize_zone_buckets(events: pd.DataFrame, min_count: int = 3, exclude_serves: bool = True) -> pd.DataFrame:
    """
    Build zone bucket metrics across defined mappings, split by responder role and player.
    Requires columns: opp_prev_zone, resp_zone, Stroke, Player, response_time_sec, classification.
    """
    df = events.copy()
    if exclude_serves:
        df = df[~(df["is_serve"].astype(bool))].copy()
    # Require zones
    df = df[df["opp_prev_zone"].notna() & df["resp_zone"].notna()].copy()
    # Normalize zones to lower-case
    df["opp_prev_zone"] = df["opp_prev_zone"].astype(str).str.lower()
    df["resp_zone"] = df["resp_zone"].astype(str).str.lower()
    # Role
    df["role"] = df["Stroke"].apply(get_stroke_role)
    # Buckets
    front = {"front_right", "front_left"}
    back = {"back_right", "back_left"}
    def bucket(row: pd.Series) -> Optional[str]:
        oz = row["opp_prev_zone"]; rz = row["resp_zone"]
        if oz in front and rz in back:
            return "front_to_back"
        if oz in back and rz in front:
            return "back_to_front"
        if oz == "middle_left" and rz == "back_right":
            return "midL_to_backR"
        if oz == "middle_right" and rz == "back_left":
            return "midR_to_backL"
        if oz == "middle_left" and rz == "front_right":
            return "midL_to_frontR"
        if oz == "middle_right" and rz == "front_left":
            return "midR_to_frontL"
        return None
    df["bucket"] = df.apply(bucket, axis=1)
    df = df[df["bucket"].notna()].copy()
    # Keep valid response times
    df = df[pd.to_numeric(df["response_time_sec"], errors="coerce").notna()].copy()
    rows: List[Dict[str, Any]] = []
    for (bucket_id, player, role), g in df.groupby(["bucket", "Player", "role"]):
        count = int(len(g))
        if count < min_count:
            continue
        vals = g["response_time_sec"].astype(float).tolist()
        rows.append({
            "bucket": str(bucket_id),
            "player": str(player),
            "role": str(role),
            "count": count,
            "min_rt": float(min(vals)),
            "p10": percentile(vals, 10.0),
            "median": median(vals),
            "p90": percentile(vals, 90.0),
            "max_rt": float(max(vals)),
            "fast_rate": float((g["classification"] == "fast").mean()),
            "slow_rate": float((g["classification"] == "slow").mean()),
            "times_sec": sorted([round(float(t), 3) for t in g["time_sec"].astype(float).tolist()]),
        })
    return pd.DataFrame.from_records(rows)


def summarize_combo_quality_and_instances(events: pd.DataFrame, min_count: int = 3) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build quality-aware combo summary (by color bands) and per-instance mapping.
    Key: player | opp_prev_stroke | opp_band | resp_stroke | resp_band
    """
    df = events.copy()
    # Need colors
    df = df[df["incoming_color"].notna() & df["effectiveness_color"].notna()].copy()
    df["incoming_color"] = df["incoming_color"].astype(str).str.lower()
    df["effectiveness_color"] = df["effectiveness_color"].astype(str).str.lower()
    df = df[pd.to_numeric(df["response_time_sec"], errors="coerce").notna()].copy()
    # Build key
    df["combo_key_band"] = df.apply(lambda r: f"{r['Player']}|opp:{r['opp_prev_stroke']}|opp_col:{r['incoming_color']}|resp:{r['Stroke']}|resp_col:{r['effectiveness_color']}", axis=1)
    # Summary
    summary_rows: List[Dict[str, Any]] = []
    key_to_thresh: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for key, g in df.groupby("combo_key_band"):
        count = int(len(g))
        if count < min_count:
            continue
        vals = g["response_time_sec"].astype(float).tolist()
        p10 = percentile(vals, 10.0)
        p90 = percentile(vals, 90.0)
        summary_rows.append({
            "combo_key_band": key,
            "player": str(g["Player"].iloc[0]),
            "opp_prev_stroke": str(g["opp_prev_stroke"].iloc[0]),
            "opp_band": str(g["incoming_color"].iloc[0]),
            "resp_stroke": str(g["Stroke"].iloc[0]),
            "resp_band": str(g["effectiveness_color"].iloc[0]),
            "count": count,
            "min_rt": float(min(vals)),
            "p10": p10,
            "median": median(vals),
            "p90": p90,
            "max_rt": float(max(vals)),
        })
        key_to_thresh[key] = (p10, p90)
    summary_df = pd.DataFrame.from_records(summary_rows)
    # Instances for kept keys only
    kept_keys = set(summary_df["combo_key_band"].tolist()) if not summary_df.empty else set()
    inst_rows: List[Dict[str, Any]] = []
    for _, r in df[df["combo_key_band"].isin(kept_keys)].iterrows():
        key = str(r["combo_key_band"])
        p10, p90 = key_to_thresh.get(key, (None, None))
        pos = "typical"
        try:
            rt = float(r["response_time_sec"])
            if p10 is not None and rt <= float(p10):
                pos = "near_min"
            elif p90 is not None and rt >= float(p90):
                pos = "near_max"
        except Exception:
            pos = "typical"
        inst_rows.append({
            "combo_key_band": key,
            "rally_id": str(r["rally_id"]),
            "player": str(r["Player"]),
            "time_sec": round(float(r["time_sec"]), 3),
            "opp_prev_stroke": str(r["opp_prev_stroke"]),
            "opp_band": str(r["incoming_color"]),
            "resp_stroke": str(r["Stroke"]),
            "resp_band": str(r["effectiveness_color"]),
            "response_time_sec": float(r["response_time_sec"]),
            "position_band": pos,
        })
    instances_df = pd.DataFrame.from_records(inst_rows)
    return summary_df, instances_df


def summarize_rally_metrics(events: pd.DataFrame, baseline_stats: Dict[str, ComboStats]) -> pd.DataFrame:
    """
    Compute within-rally pace dynamics per player.
    """
    df = events.copy()
    df = df[pd.to_numeric(df["response_time_sec"], errors="coerce").notna()].copy()
    rows: List[Dict[str, Any]] = []
    for (game, rally, rid, player), g in df.groupby(["GameNumber", "RallyNumber", "rally_id", "Player"]):
        g = g.sort_values("time_sec")
        rts = g["response_time_sec"].astype(float).tolist()
        cls = [str(c) for c in g["classification"].tolist()]
        n = len(rts)
        if n == 0:
            continue
        # stats
        mean = sum(rts) / n
        var = sum((x - mean) ** 2 for x in rts) / n
        stdv = var ** 0.5
        p25 = percentile(rts, 25.0) or 0.0
        p75 = percentile(rts, 75.0) or 0.0
        iqr = (p75 - p25) if (p75 is not None and p25 is not None) else 0.0
        rng = (max(rts) - min(rts)) if n > 1 else 0.0
        # transitions and runs
        def cat(x: str) -> str:
            x = (x or "").lower()
            if x in ("fast", "slow", "normal"):
                return x
            return "normal"
        cats = [cat(c) for c in cls]
        transitions = sum(1 for i in range(1, n) if cats[i] != cats[i-1])
        longest_run = 1
        cur = 1
        for i in range(1, n):
            if cats[i] == cats[i-1]:
                cur += 1
                longest_run = max(longest_run, cur)
            else:
                cur = 1
        # early vs late
        mid = n // 2
        early = rts[:mid] if mid > 0 else rts
        late = rts[mid:] if mid > 0 else rts
        early_med = median(early)
        late_med = median(late)
        early_late_delta = (late_med - early_med) if (early_med is not None and late_med is not None) else None
        # slope over index (simple)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(rts) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        slope = (sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, rts)) / denom) if denom != 0 else 0.0
        # delta vs baseline
        base = baseline_stats.get(player)
        delta_vs_base = None
        if base and base.median is not None:
            med = median(rts)
            if med is not None:
                delta_vs_base = float(med - base.median)
        rows.append({
            "game": int(game),
            "rally": int(rally),
            "rally_id": str(rid),
            "player": str(player),
            "shots": n,
            "median_rt": median(rts),
            "stddev_rt": float(stdv),
            "iqr_rt": float(iqr),
            "range_rt": float(rng),
            "transitions": int(transitions),
            "longest_run": int(longest_run),
            "early_late_delta": early_late_delta,
            "slope_rt": float(slope),
            "delta_vs_baseline": delta_vs_base,
        })
    return pd.DataFrame.from_records(rows)

def build_combo_stats_csv(
    combo_stats: Dict[str, ComboStats],
    opp_only_stats: Dict[str, ComboStats],
    baseline_stats: Dict[str, ComboStats],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for key, st in combo_stats.items():
        rows.append({"level": "combo", "key": key, **st.to_dict()})
    for key, st in opp_only_stats.items():
        rows.append({"level": "opp_only", "key": key, **st.to_dict()})
    for key, st in baseline_stats.items():
        rows.append({"level": "baseline", "key": key, **st.to_dict()})
    return pd.DataFrame.from_records(rows)


def detect_standout_events(
    events: pd.DataFrame,
    combo_stats: Dict[str, ComboStats],
    z_abs_threshold: float,
    combo_stats_q: Optional[Dict[str, ComboStats]] = None,
) -> pd.DataFrame:
    """
    Flags events that are standout by any reason:
      - classification fast/slow
      - |z_score_baseline_mad| >= z_abs_threshold
      - combo-specific deviation: rt <= p10 or rt >= p90
    Returns DataFrame with subset of columns and 'reasons' joined by ';'
    """
    cols_keep = ["rally_id", "Player", "FrameNumber", "time_sec", "Stroke", "opp_prev_stroke", "response_time_sec", "classification", "z_score_baseline_mad", "threshold_source", "combo_key"]
    df = events.copy()
    out_rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        rt = r.get("response_time_sec")
        if pd.isna(rt):
            continue
        reasons: List[str] = []
        cls = str(r.get("classification") or "").lower()
        if cls == "fast":
            reasons.append("fast_label")
        elif cls == "slow":
            reasons.append("slow_label")
        z = r.get("z_score_baseline_mad")
        try:
            zf = float(z)
            if pd.notna(zf) and abs(zf) >= z_abs_threshold:
                reasons.append("z_ge_threshold")
        except Exception:
            pass
        # Prefer quality-conditioned combo thresholds for standout check if present
        ck = r.get("combo_key")
        qbin = r.get("incoming_eff_bin")
        used_combo_check = False
        if combo_stats_q is not None and pd.notna(ck) and pd.notna(qbin):
            stq = combo_stats_q.get(f"{str(ck)}|q:{str(qbin)}")
            if stq and stq.p10 is not None and stq.p90 is not None:
                try:
                    rtv = float(rt)
                    if rtv <= float(stq.p10):
                        reasons.append("combo_q_p10")
                    if rtv >= float(stq.p90):
                        reasons.append("combo_q_p90")
                    used_combo_check = True
                except Exception:
                    pass
        if not used_combo_check and pd.notna(ck):
            st = combo_stats.get(str(ck))
            if st and st.p10 is not None and st.p90 is not None:
                try:
                    rtv = float(rt)
                    if rtv <= float(st.p10):
                        reasons.append("combo_p10")
                    if rtv >= float(st.p90):
                        reasons.append("combo_p90")
                except Exception:
                    pass
        if reasons:
            row = {k: r.get(k) for k in cols_keep}
            row["reasons"] = ";".join(sorted(set(reasons)))
            out_rows.append(row)  # type: ignore[arg-type]
    return pd.DataFrame.from_records(out_rows)


def compute_combo_patterns(
    events: pd.DataFrame,
    baseline_stats: Dict[str, ComboStats],
    pattern_min_n: int,
    pattern_rate_threshold: float,
    pattern_delta_threshold: float,
) -> pd.DataFrame:
    """
    Group by (Player, opp_prev_stroke, Stroke) and compute pattern stats.
    """
    df = events.copy()
    df = df[pd.to_numeric(df["response_time_sec"], errors="coerce").notna()].copy()
    rows: List[Dict[str, Any]] = []
    grouped = df.groupby(["Player", "opp_prev_stroke", "Stroke"])
    for (player, opp_stroke, stroke), g in grouped:
        count = int(len(g))
        vals = g["response_time_sec"].astype(float).tolist()
        med = median(vals)
        p10 = percentile(vals, 10.0)
        p90 = percentile(vals, 90.0)
        fast_rate = float((g["classification"] == "fast").mean()) if count > 0 else 0.0  # type: ignore[arg-type]
        slow_rate = float((g["classification"] == "slow").mean()) if count > 0 else 0.0  # type: ignore[arg-type]
        base = baseline_stats.get(str(player))
        delta_vs_base = None
        if base and base.median is not None and med is not None:
            delta_vs_base = float(med - base.median)  # type: ignore[operator]
        flagged = (
            (count >= pattern_min_n) and
            (
                (fast_rate >= pattern_rate_threshold) or
                (slow_rate >= pattern_rate_threshold)
            ) and
            (delta_vs_base is not None and abs(delta_vs_base) >= pattern_delta_threshold)
        )
        rows.append({
            "Player": player,
            "opp_prev_stroke": opp_stroke,
            "responder_stroke": stroke,
            "count": count,
            "fast_rate": fast_rate,
            "slow_rate": slow_rate,
            "median_rt": med,
            "p10": p10,
            "p90": p90,
            "delta_vs_player_median": delta_vs_base,
            "flagged": bool(flagged),
        })
    return pd.DataFrame.from_records(rows)


def analyze_serve_receive(events: pd.DataFrame, baseline_stats: Dict[str, ComboStats]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Identify first response after serve by leveraging opp_prev_stroke contains 'serve'.
    Returns (CSV DataFrame rows per player, JSON summary dict).
    """
    df = events.copy()
    df = df[pd.to_numeric(df["response_time_sec"], errors="coerce").notna()].copy()
    df["is_after_serve"] = df["opp_prev_stroke"].astype(str).str.contains("serve", case=False, na=False)
    srv = df[df["is_after_serve"]].copy()
    out_rows: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    for player in ["P0", "P1"]:
        g_all = df[df["Player"] == player]
        g_srv = srv[srv["Player"] == player]
        count_srv = int(len(g_srv))
        vals_srv = g_srv["response_time_sec"].astype(float).tolist()
        med_srv = median(vals_srv)
        p10_srv = percentile(vals_srv, 10.0)
        p90_srv = percentile(vals_srv, 90.0)
        fast_rate_srv = float((g_srv["classification"] == "fast").mean()) if count_srv > 0 else 0.0  # type: ignore[arg-type]
        slow_rate_srv = float((g_srv["classification"] == "slow").mean()) if count_srv > 0 else 0.0  # type: ignore[arg-type]
        base = baseline_stats.get(player)
        base_median = base.median if base else None  # type: ignore[assignment]
        delta_vs_all = None
        if base_median is not None and med_srv is not None:
            delta_vs_all = float(med_srv - base_median)  # type: ignore[operator]
        out_rows.append({
            "Player": player,
            "count_after_serve": count_srv,
            "median_rt_after_serve": med_srv,
            "p10_after_serve": p10_srv,
            "p90_after_serve": p90_srv,
            "fast_rate_after_serve": fast_rate_srv,
            "slow_rate_after_serve": slow_rate_srv,
            "player_baseline_median": base_median,
            "delta_vs_player_median": delta_vs_all,
        })
        summary[player] = {
            "count": count_srv,
            "median_rt": med_srv,
            "p10": p10_srv,
            "p90": p90_srv,
            "fast_rate": fast_rate_srv,
            "slow_rate": slow_rate_srv,
            "baseline_median": base_median,
            "delta_vs_baseline": delta_vs_all,
        }
    return pd.DataFrame.from_records(out_rows), summary


def summarize_combo_fast_slow(events: pd.DataFrame, min_count: int = 3) -> pd.DataFrame:
    """
    Build per-combo summary with two columns: fast times and slow times (time_sec),
    plus their counts. Filter to combos where at least one of fast_count or slow_count >= min_count.
    Group key: combo_key (Player|opp:<stroke>|resp:<stroke>)
    """
    df = events.copy()
    # Only consider rows with a classification
    df = df[df["classification"].isin(["fast", "slow"])].copy()
    rows: List[Dict[str, Any]] = []
    for combo, g in df.groupby("combo_key"):
        if pd.isna(combo):
            continue
        fast_times = g[g["classification"] == "fast"]["time_sec"].astype(float).round(3).tolist()
        slow_times = g[g["classification"] == "slow"]["time_sec"].astype(float).round(3).tolist()
        fast_count = len(fast_times)
        slow_count = len(slow_times)
        if fast_count >= min_count or slow_count >= min_count:
            # Extract parsed fields
            parts = str(combo).split("|")
            player = parts[0] if len(parts) > 0 else ""
            opp_part = parts[1] if len(parts) > 1 else ""
            resp_part = parts[2] if len(parts) > 2 else ""
            opp_stroke = opp_part.replace("opp:", "") if opp_part.startswith("opp:") else opp_part
            resp_stroke = resp_part.replace("resp:", "") if resp_part.startswith("resp:") else resp_part
            rows.append({
                "combo_key": combo,
                "player": player,
                "opp_prev_stroke": opp_stroke,
                "responder_stroke": resp_stroke,
                "fast_count": fast_count,
                "slow_count": slow_count,
                "fast_times_sec": fast_times,
                "slow_times_sec": slow_times,
            })
    return pd.DataFrame.from_records(rows)


def main() -> None:
    args = parse_args()
    csv_path = Path(args.detailed_csv)
    if not csv_path.exists():
        raise SystemExit(f"Not found: {csv_path}")

    out_prefix = Path(args.out_prefix) if args.out_prefix else csv_path.with_suffix("")
    events_out = Path(f"{out_prefix}_tempo_events.csv")
    thresholds_out = Path(f"{out_prefix}_tempo_thresholds.json")
    rally_summary_out = Path(f"{out_prefix}_tempo_rally_summary.csv")
    combo_stats_out = Path(f"{out_prefix}_tempo_combo_stats.csv")

    df = pd.read_csv(csv_path)
    # Load effectiveness CSV if provided and build mapping
    eff_map: Optional[Dict[Tuple[int, int, int, str], Optional[float]]] = None
    eff_color_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None
    eff_label_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None
    eff_reason_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None
    is_serve_map: Optional[Dict[Tuple[int, int, int, str], Optional[bool]]] = None
    eff_zone_map: Optional[Dict[Tuple[int, int, int, str], Optional[str]]] = None
    if args.effectiveness_csv:
        eff_df = pd.read_csv(Path(args.effectiveness_csv))
        # Normalize effectiveness column name
        eff_col = None
        for c in eff_df.columns:
            cl = str(c).strip().lower()
            if cl == "effectiveness":
                eff_col = c
                break
        if eff_col is None:
            # try a couple of variants
            for c in eff_df.columns:
                cl = str(c).strip().lower()
                if "effectiveness" in cl:
                    eff_col = c
                    break
        if eff_col is None:
            raise RuntimeError("Effectiveness CSV does not contain an 'effectiveness' column")
        # Normalize optional helper columns
        color_col = None
        for c in eff_df.columns:
            if str(c).strip().lower() == "color":
                color_col = c
                break
        label_col = None
        for c in eff_df.columns:
            cl = str(c).strip().lower()
            if cl in ("effectiveness_label", "effectivenesslabel"):
                label_col = c
                break
        reason_col = None
        for c in eff_df.columns:
            cl = str(c).strip().lower()
            if cl in ("reason", "reasons"):
                reason_col = c
                break
        is_serve_col = None
        for c in eff_df.columns:
            cl = str(c).strip().lower()
            if cl in ("is_serve", "isserve"):
                is_serve_col = c
                break
        zone_col = None
        for c in eff_df.columns:
            cl = str(c).strip().lower()
            if cl in ("anchorhittingzone", "hittingzone"):
                zone_col = c
                break

        eff_map = {}
        eff_color_map = {}
        eff_label_map = {}
        eff_reason_map = {}
        is_serve_map = {}
        eff_zone_map = {}
        for _, r in eff_df.iterrows():
            try:
                key = (int(r["GameNumber"]), int(r["RallyNumber"]), int(r["StrokeNumber"]), str(r["Player"]))
                val_raw = r.get(eff_col)
                val = None
                try:
                    v = float(val_raw)
                    if pd.notna(v):
                        val = v
                except Exception:
                    val = None
                eff_map[key] = val
                # extras
                eff_color_map[key] = (str(r.get(color_col)).strip().lower() if color_col and pd.notna(r.get(color_col)) else None)
                # labels/reasons
                lab_raw = r.get(label_col) if label_col else None
                eff_label_map[key] = (str(lab_raw) if lab_raw is not None and pd.notna(lab_raw) else None)
                rea_raw = r.get(reason_col) if reason_col else None
                eff_reason_map[key] = (str(rea_raw) if rea_raw is not None and pd.notna(rea_raw) else None)
                # is_serve flag
                if is_serve_col:
                    try:
                        isv = str(r.get(is_serve_col)).strip().lower()
                        is_serve_map[key] = (isv in ("1", "true", "yes"))
                    except Exception:
                        is_serve_map[key] = None
                else:
                    is_serve_map[key] = None
                # zone
                if zone_col:
                    z = r.get(zone_col)
                    eff_zone_map[key] = (str(z).strip().lower() if pd.notna(z) else None)
                else:
                    eff_zone_map[key] = None
            except Exception:
                continue

    events = extract_events_with_response_times(
        df,
        fps=args.fps,
        filter_strokes=not args.no_stroke_filter,
        eff_map=eff_map,
        eff_bin1=args.eff_bin1,
        eff_bin2=args.eff_bin2,
        eff_color_map=eff_color_map,
        eff_label_map=eff_label_map,
        eff_reason_map=eff_reason_map,
        is_serve_map=is_serve_map,
        eff_zone_map=eff_zone_map,
    )
    # Clamp response times for stats; keep raw separately
    events["response_time_sec"] = events["response_time_sec_raw"]

    # Build keys for combination stats
    events = build_combo_keys(events)

    combo_stats, opp_only_stats, baseline_stats, combo_stats_q, opp_only_stats_q, baseline_stats_q = build_thresholds(
        events, lower_cap=args.lower_cap, upper_cap=args.upper_cap,
        min_combo_n=args.min_combo_n, min_opp_stroke_n=args.min_opp_stroke_n
    )

    # Classify each event with response time
    classifications: List[Optional[str]] = []
    fast_src: List[str] = []
    fast_ths: List[Optional[float]] = []
    slow_ths: List[Optional[float]] = []
    zscores: List[Optional[float]] = []
    for _, r in events.iterrows():
        player = r["Player"]
        rt = r.get("response_time_sec")
        combo_key = r.get("combo_key")
        opp_only_key = r.get("opp_only_key")
        qbin = r.get("incoming_eff_bin")
        fast_th, slow_th, src = choose_threshold_for_event(
            player=player,
            combo_key=combo_key if pd.notna(combo_key) else None,
            opp_only_key=opp_only_key if pd.notna(opp_only_key) else None,
            incoming_eff_bin=(str(qbin) if pd.notna(qbin) else None),
            combo_stats=combo_stats,
            opp_only_stats=opp_only_stats,
            baseline_stats=baseline_stats,
            combo_stats_q=combo_stats_q,
            opp_only_stats_q=opp_only_stats_q,
            baseline_stats_q=baseline_stats_q,
        )
        classifications.append(classify_event(rt if pd.notna(rt) else None, fast_th, slow_th))
        fast_src.append(src)
        fast_ths.append(fast_th)
        slow_ths.append(slow_th)
        zscores.append(compute_zscore(rt if pd.notna(rt) else None, baseline_stats.get(player)))

    events["classification"] = classifications
    events["threshold_source"] = fast_src
    events["fast_threshold"] = fast_ths
    events["slow_threshold"] = slow_ths
    events["z_score_baseline_mad"] = zscores

    # Write outputs
    events.to_csv(events_out, index=False)

    # Rally summaries
    rally_summary = summarize_by_rally(events)
    rally_summary.to_csv(rally_summary_out, index=False)

    # Combo stats CSV
    combo_stats_df = build_combo_stats_csv(combo_stats, opp_only_stats, baseline_stats)
    combo_stats_df.to_csv(combo_stats_out, index=False)

    # Standout events (CSV) and combo patterns (CSV)
    standout_df = detect_standout_events(events, combo_stats, args.standout_z, combo_stats_q=combo_stats_q)
    standout_out = Path(f"{out_prefix}_tempo_highlights_events.csv")
    standout_df.to_csv(standout_out, index=False)

    patterns_df = compute_combo_patterns(
        events,
        baseline_stats=baseline_stats,
        pattern_min_n=args.pattern_min_n,
        pattern_rate_threshold=args.pattern_rate,
        pattern_delta_threshold=args.pattern_delta,
    )
    patterns_out = Path(f"{out_prefix}_tempo_combo_patterns.csv")
    patterns_df.to_csv(patterns_out, index=False)

    # Serve/receive analysis (CSV + JSON)
    serve_df, serve_summary = analyze_serve_receive(events, baseline_stats=baseline_stats)
    serve_csv_out = Path(f"{out_prefix}_tempo_serve_receive.csv")
    serve_json_out = Path(f"{out_prefix}_tempo_serve_receive.json")
    serve_df.to_csv(serve_csv_out, index=False)
    serve_json_out.write_text(json.dumps(serve_summary, indent=2, allow_nan=False), encoding="utf-8")

    # Thresholds JSON (serializable)
    # Replace NaN with None in DataFrames before converting to dict
    combos_df = combo_stats_df[combo_stats_df["level"] == "combo"][["key", "count", "median", "p10", "p90", "mad"]].copy()
    combos_df = combos_df.where(pd.notna(combos_df), None).set_index("key")
    opponly_df = combo_stats_df[combo_stats_df["level"] == "opp_only"][["key", "count", "median", "p10", "p90", "mad"]].copy()
    opponly_df = opponly_df.where(pd.notna(opponly_df), None).set_index("key")

    payload = {
        "fps": args.fps,
        "caps": {"lower": args.lower_cap, "upper": args.upper_cap},
        "min_combo_n": args.min_combo_n,
        "min_opp_stroke_n": args.min_opp_stroke_n,
        "baselines": {player: st.to_dict() for player, st in baseline_stats.items()},
        "combos": combos_df.to_dict(orient="index"),
        "opp_only": opponly_df.to_dict(orient="index"),
    }
    # Ensure strict JSON (no NaN/Inf); if any slipped through, replace with None
    def sanitize(o: Any) -> Any:
        try:
            import math
            if isinstance(o, float) and not math.isfinite(o):
                return None
        except Exception:
            pass
        if isinstance(o, dict):
            return {k: sanitize(v) for k, v in o.items()}
        if isinstance(o, list):
            return [sanitize(v) for v in o]
        return o
    payload = sanitize(payload)
    thresholds_out.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")

    print(f"Wrote {events_out}")
    print(f"Wrote {combo_stats_out}")
    print(f"Wrote {rally_summary_out}")
    print(f"Wrote {thresholds_out}")
    print(f"Wrote {standout_out}")
    print(f"Wrote {patterns_out}")
    print(f"Wrote {serve_csv_out}")
    print(f"Wrote {serve_json_out}")

    # Combo fast/slow summary (CSV + JSON)
    combo_fs_df = summarize_combo_fast_slow(events, min_count=3)
    combo_fs_csv = Path(f"{out_prefix}_tempo_combo_fast_slow.csv")
    combo_fs_json = Path(f"{out_prefix}_tempo_combo_fast_slow.json")
    combo_fs_df.to_csv(combo_fs_csv, index=False)
    combo_fs_json.write_text(json.dumps(combo_fs_df.to_dict(orient="records"), indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote {combo_fs_csv}")
    print(f"Wrote {combo_fs_json}")

    # Ineffective + slow instances and maps
    def is_error_forced(text: Optional[str]) -> bool:
        if not text:
            return False
        t = str(text).lower()
        return ("forced error" in t) or ("forced" in t and "error" in t) or ("fe" == t.strip())

    def is_error_unforced(text: Optional[str]) -> bool:
        if not text:
            return False
        t = str(text).lower()
        return ("unforced error" in t) or ("unforced" in t and "error" in t) or ("ue" == t.strip())

    ineff_colors = [s.strip().lower() for s in str(args.ineff_colors).split(",") if s.strip()]
    ineff_th = float(args.ineff_threshold)
    exclude_serves = not bool(args.include_serves)

    ev = events.copy()
    # Keep only slow
    ev = ev[ev["classification"] == "slow"].copy()
    # Exclude serve shots if requested
    if exclude_serves:
        ev = ev[~(ev["is_serve"].astype(bool))].copy()
    # Ineffective predicate
    col_ok = ev["effectiveness_color"].astype(str).str.lower().isin(ineff_colors)
    eff_ok = pd.to_numeric(ev["effectiveness"], errors="coerce").fillna(9999) <= ineff_th
    ev_filt = ev[(col_ok) | (eff_ok)].copy()
    # Forced/unforced flags (from label or reason fields)
    fu_label = ev_filt["effectiveness_label"].apply(lambda x: "forced" if is_error_forced(x) else ("unforced" if is_error_unforced(x) else None))
    fu_reason = ev_filt["effectiveness_reason"].apply(lambda x: "forced" if is_error_forced(x) else ("unforced" if is_error_unforced(x) else None))
    ev_filt["forced_error"] = (fu_label == "forced") | (fu_reason == "forced")
    ev_filt["unforced_error"] = (fu_label == "unforced") | (fu_reason == "unforced")

    # Instances CSV
    ineff_events_cols = [
        "rally_id", "Player", "time_sec", "Stroke", "opp_prev_stroke",
        "response_time_sec", "classification",
        "effectiveness", "effectiveness_color",
        "incoming_eff", "incoming_eff_bin",
        "forced_error", "unforced_error",
        "threshold_source", "combo_key",
    ]
    ineff_events_out = Path(f"{out_prefix}_tempo_ineffective_slow_events.csv")
    ev_filt[ineff_events_cols].to_csv(ineff_events_out, index=False)
    print(f"Wrote {ineff_events_out}")

    # Stroke map
    rows_map: List[Dict[str, Any]] = []
    for (player, stroke), g in ev_filt.groupby(["Player", "Stroke"]):
        cnt = int(len(g))
        if cnt < args.map_min_count:
            continue
        med_eff = median(pd.to_numeric(g["effectiveness"], errors="coerce").dropna().astype(float).tolist())
        vals_rt = pd.to_numeric(g["response_time_sec"], errors="coerce").dropna().astype(float).tolist()
        med_rt = median(vals_rt)
        avg_rt = float(sum(vals_rt) / len(vals_rt)) if vals_rt else None
        forced_cnt = int(g["forced_error"].sum())  # type: ignore[arg-type]
        unforced_cnt = int(g["unforced_error"].sum())  # type: ignore[arg-type]
        ex_times = sorted(pd.to_numeric(g["time_sec"], errors="coerce").dropna().astype(float).tolist())[:3]
        rows_map.append({
            "player": player,
            "stroke": stroke,
            "count": cnt,
            "median_effectiveness": med_eff,
            "median_response_time_sec": med_rt,
            "avg_response_time_sec": avg_rt,
            "forced_error_count": forced_cnt,
            "unforced_error_count": unforced_cnt,
            "example_times_sec": [round(x, 3) for x in ex_times],
        })
    df_map = pd.DataFrame.from_records(rows_map)
    if not df_map.empty:
        df_map = df_map.sort_values(["count", "median_response_time_sec"], ascending=[False, False])
    ineff_map_out = Path(f"{out_prefix}_tempo_ineffective_slow_map.csv")
    ineff_map_json = Path(f"{out_prefix}_tempo_ineffective_slow_map.json")
    df_map.to_csv(ineff_map_out, index=False)
    ineff_map_json.write_text(json.dumps(df_map.to_dict(orient="records"), indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote {ineff_map_out}")
    print(f"Wrote {ineff_map_json}")

    # Combo map
    rows_cmap: List[Dict[str, Any]] = []
    for (player, opp_prev, stroke), g in ev_filt.groupby(["Player", "opp_prev_stroke", "Stroke"]):
        cnt = int(len(g))
        if cnt < args.map_min_count:
            continue
        med_eff = median(pd.to_numeric(g["effectiveness"], errors="coerce").dropna().astype(float).tolist())
        vals_rt = pd.to_numeric(g["response_time_sec"], errors="coerce").dropna().astype(float).tolist()
        med_rt = median(vals_rt)
        avg_rt = float(sum(vals_rt) / len(vals_rt)) if vals_rt else None
        forced_cnt = int(g["forced_error"].sum())  # type: ignore[arg-type]
        unforced_cnt = int(g["unforced_error"].sum())  # type: ignore[arg-type]
        ex_times = sorted(pd.to_numeric(g["time_sec"], errors="coerce").dropna().astype(float).tolist())[:3]
        # pick a representative combo_key
        ck = None
        try:
            ck = g["combo_key"].dropna().astype(str).iloc[0]
        except Exception:
            ck = None
        rows_cmap.append({
            "player": player,
            "opp_prev_stroke": opp_prev,
            "responder_stroke": stroke,
            "combo_key": ck,
            "count": cnt,
            "median_effectiveness": med_eff,
            "median_response_time_sec": med_rt,
            "avg_response_time_sec": avg_rt,
            "forced_error_count": forced_cnt,
            "unforced_error_count": unforced_cnt,
            "example_times_sec": [round(x, 3) for x in ex_times],
        })
    df_cmap = pd.DataFrame.from_records(rows_cmap)
    if not df_cmap.empty:
        df_cmap = df_cmap.sort_values(["count", "median_response_time_sec"], ascending=[False, False])
    ineff_combo_map_out = Path(f"{out_prefix}_tempo_ineffective_slow_combo_map.csv")
    ineff_combo_map_json = Path(f"{out_prefix}_tempo_ineffective_slow_combo_map.json")
    df_cmap.to_csv(ineff_combo_map_out, index=False)
    ineff_combo_map_json.write_text(json.dumps(df_cmap.to_dict(orient="records"), indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote {ineff_combo_map_out}")
    print(f"Wrote {ineff_combo_map_json}")

    # Zone bucket stats (a–f), split by role, with all times
    zone_df = summarize_zone_buckets(events, min_count=3, exclude_serves=not bool(args.include_serves))
    zone_csv = Path(f"{out_prefix}_tempo_zone_buckets.csv")
    zone_json = Path(f"{out_prefix}_tempo_zone_buckets.json")
    zone_df.to_csv(zone_csv, index=False)
    zone_json.write_text(json.dumps(zone_df.to_dict(orient="records"), indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote {zone_csv}")
    print(f"Wrote {zone_json}")

    # Quality-aware combo summary and instances (count >= 3)
    combo_sum_band_df, combo_inst_band_df = summarize_combo_quality_and_instances(events, min_count=3)
    combo_sum_band_csv = Path(f"{out_prefix}_tempo_combo_summary_band.csv")
    combo_inst_band_csv = Path(f"{out_prefix}_tempo_combo_instances_band.csv")
    combo_sum_band_df.to_csv(combo_sum_band_csv, index=False)
    combo_inst_band_df.to_csv(combo_inst_band_csv, index=False)
    print(f"Wrote {combo_sum_band_csv}")
    print(f"Wrote {combo_inst_band_csv}")

    # Rally-level pace metrics
    rally_metrics_df = summarize_rally_metrics(events, baseline_stats=baseline_stats)
    rally_metrics_csv = Path(f"{out_prefix}_tempo_rally_metrics.csv")
    rally_metrics_df.to_csv(rally_metrics_csv, index=False)
    print(f"Wrote {rally_metrics_csv}")


if __name__ == "__main__":
    main()


