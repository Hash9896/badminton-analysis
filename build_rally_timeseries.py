#!/usr/bin/env python3
"""
Generate rally_timeseries.json for video-synced effectiveness charts.

Key behavior:
- Includes ALL rallies with at least 4 strokes (N >= 4); no swing-based filtering.
- Computes turning points where per-player effectiveness swing >= threshold (abs).
- Adds score-at-rally-start labels (e.g., G2 18–19) and index by score.
- Adds slope-based rally dynamics per player (incline/decline/flat) and summaries
  consolidated by P0's winning vs losing rallies.

Usage:
  python3 build_rally_timeseries.py <detailed_effectiveness_csv>
    [--fps 30]
    [--swing 40]
    [--trend-eps-slope 1.0]
    [--trend-eps-delta 8.0]
    [--out rally_timeseries.json]

Output JSON schema (selected):
{
  "fps": 30,
  "threshold": 40,
  "indices": {
    "by_score": { "G1_12-10": ["<rally_id>", ...], ... }
  },
  "rallies": {
    "<rally_id>": {
      "frame_start": int,
      "frame_end": int,
      "winner": "P0"|"P1"|null,
      "score_label": "G1 12–10",
      "score_key": "G1_12-10",
      "shot_sequence": "stroke1 → stroke2 → ...",
      "points": [
        {"frame": int, "time_sec": float, "stroke_no": int, "player": "P0"|"P1", "stroke": str, "effectiveness": float|null}
      ],
      "turning_points": [
        {"player": str, "stroke_no": int, "frame": int, "time_sec": float, "swing": float, "stroke": str}
      ],
      "rally_dynamics": {
        "P0": {"slope": float, "delta": float, "category": "incline"|"decline"|"flat"},
        "P1": {"slope": float, "delta": float, "category": "incline"|"decline"|"flat"},
        "combined_category": "both_incline"|"both_decline"|"mixed"|"flat"
      }
    }
  },
  "summaries": { "p0_won": {...}, "p0_lost": {...} }
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd


def to_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if pd.isna(v):
            return None
        return v
    except Exception:
        return None


def compute_swing_points(rally_df: pd.DataFrame, threshold: float) -> List[Dict[str, Any]]:
    """Compute turning points per-actor based on effectiveness swings >= threshold.
    Returns list of dicts with player, stroke_no, frame, swing, stroke.
    """
    swings: List[Dict[str, Any]] = []
    for actor in ["P0", "P1"]:
        df_actor = rally_df[rally_df["Player"] == actor].copy()
        if df_actor.empty:
            continue
        df_actor = df_actor.sort_values("StrokeNumber")
        prev_eff: Optional[float] = None
        for _, r in df_actor.iterrows():
            eff = to_float(r.get("effectiveness"))
            if eff is None:
                # skip this stroke from swing calc; do not update prev_eff
                continue
            if prev_eff is not None:
                swing = eff - prev_eff
                if abs(swing) >= threshold:
                    swings.append({
                        "player": actor,
                        "stroke_no": int(r.get("StrokeNumber")),
                        "frame": int(r.get("FrameNumber")),
                        "swing": float(swing),
                        "stroke": str(r.get("Stroke", "")),
                    })
            prev_eff = eff
    return swings


def build_timeseries_for_rally(rally_df: pd.DataFrame, fps: float) -> Dict[str, Any]:
    rally_df = rally_df.sort_values("StrokeNumber")
    frame_start = int(rally_df["FrameNumber"].min())
    frame_end = int(rally_df["FrameNumber"].max())
    winner = None
    # Prefer last non-null RallyWinner in the rally
    cand = rally_df["RallyWinner"].dropna().astype(str)
    if not cand.empty:
        winner = cand.iloc[-1]
    # shot sequence
    shots = rally_df["Stroke"].astype(str).tolist()
    shot_sequence = " → ".join(shots)
    # points
    points: List[Dict[str, Any]] = []
    for _, r in rally_df.iterrows():
        frame = int(r.get("FrameNumber"))
        points.append({
            "frame": frame,
            "time_sec": frame / fps if fps > 0 else frame / 30.0,
            "stroke_no": int(r.get("StrokeNumber")),
            "player": str(r.get("Player")),
            "stroke": str(r.get("Stroke", "")),
            "effectiveness": to_float(r.get("effectiveness")),
        })
    return {
        "frame_start": frame_start,
        "frame_end": frame_end,
        "winner": winner,
        "shot_sequence": shot_sequence,
        "points": points,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build rally timeseries JSON for all rallies (N >= 4) with turning points, score labels, and dynamics.")
    ap.add_argument("detailed_csv", type=str, help="Path to *_detailed_effectiveness.csv")
    ap.add_argument("--fps", type=float, default=30.0, help="Video FPS (default: 30)")
    ap.add_argument("--swing", type=float, default=40.0, help="Swing threshold (abs) to classify turning points (default: 40)")
    ap.add_argument("--trend-eps-slope", dest="trend_eps_slope", type=float, default=1.0, help="Slope deadband for trend classification (effectiveness per stroke). |slope| < eps => flat")
    ap.add_argument("--trend-eps-delta", dest="trend_eps_delta", type=float, default=8.0, help="Delta deadband for trend classification. |delta| < eps => flat")
    ap.add_argument("--out", type=str, default=None, help="Output JSON path (default: rally_timeseries.json next to input)")
    args = ap.parse_args()

    csv_path = Path(args.detailed_csv)
    out_path = Path(args.out) if args.out else csv_path.parent / "rally_timeseries.json"

    df = pd.read_csv(csv_path)
    # Ensure required columns
    required = ["GameNumber", "RallyNumber", "StrokeNumber", "FrameNumber", "Player", "Stroke", "RallyWinner"]
    for col in required:
        if col not in df.columns:
            raise RuntimeError(f"Missing required column: {col}")
    if "rally_id" not in df.columns:
        df["rally_id"] = df["GameNumber"].astype(str) + "_" + df["RallyNumber"].astype(str) + "_seg1"

    # Sort globally by game/rally/stroke to support score-at-start computation
    df = df.sort_values(["GameNumber", "RallyNumber", "StrokeNumber"])  # do not rely solely on rally_id

    # Build rally metadata ordered by (game, rally) to compute scores at rally start
    rally_meta: List[Tuple[str, int, int, Optional[str]]] = []  # (rally_id, game, rally_no, winner)
    for rid, g in df.groupby("rally_id"):
        game = int(g["GameNumber"].iloc[0])
        rally_no = int(g["RallyNumber"].iloc[0])
        cand = g["RallyWinner"].dropna().astype(str)
        winner: Optional[str] = cand.iloc[-1] if not cand.empty else None
        rally_meta.append((str(rid), game, rally_no, winner))
    rally_meta.sort(key=lambda x: (x[1], x[2]))

    # Compute score at rally start per rally_id
    rid_to_score: Dict[str, Tuple[int, int, int]] = {}  # rid -> (game, p0, p1)
    current_game: Optional[int] = None
    p0_score = 0
    p1_score = 0
    for rid, game, rally_no, winner in rally_meta:
        if current_game is None or game != current_game:
            current_game = game
            p0_score = 0
            p1_score = 0
        rid_to_score[rid] = (game, p0_score, p1_score)
        if winner == "P0":
            p0_score += 1
        elif winner == "P1":
            p1_score += 1

    def score_strings(rid: str) -> Tuple[str, str]:
        game, p0, p1 = rid_to_score.get(rid, (0, 0, 0))
        score_label = f"G{game} {p0}\u2013{p1}"
        score_key = f"G{game}_{p0}-{p1}"
        return score_label, score_key

    # Helpers to compute trend metrics per player within a rally
    def compute_trend_for_player(rally_df: pd.DataFrame, player: str, eps_slope: float, eps_delta: float) -> Dict[str, Any]:
        dfp = rally_df[rally_df["Player"] == player].sort_values("StrokeNumber").copy()
        eff_vals: List[float] = []
        for _, r in dfp.iterrows():
            eff = to_float(r.get("effectiveness"))
            if eff is not None:
                eff_vals.append(eff)
        n = len(eff_vals)
        if n < 2:
            return {"slope": 0.0, "delta": 0.0, "category": "flat"}
        # x as 0..n-1
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(eff_vals) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom == 0:
            slope = 0.0
        else:
            slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, eff_vals)) / denom
        delta = eff_vals[-1] - eff_vals[0]
        is_flat = abs(slope) < args.trend_eps_slope or abs(delta) < args.trend_eps_delta
        if is_flat:
            cat = "flat"
        else:
            cat = "incline" if slope > 0 else "decline"
        return {"slope": float(slope), "delta": float(delta), "category": cat}

    def combined_category(p0_cat: str, p1_cat: str) -> str:
        if p0_cat == "flat" and p1_cat == "flat":
            return "flat"
        if p0_cat == p1_cat and p0_cat in ("incline", "decline"):
            return "both_incline" if p0_cat == "incline" else "both_decline"
        return "mixed"

    rallies: Dict[str, Any] = {}
    indices_by_score: Dict[str, List[str]] = {}
    # For summaries
    agg = {
        "p0_won": {
            "categories": [],
            "p0_slopes": [], "p0_deltas": [],
            "p1_slopes": [], "p1_deltas": [],
            "tp_counts": [], "tp_abs_swings": [],
        },
        "p0_lost": {
            "categories": [],
            "p0_slopes": [], "p0_deltas": [],
            "p1_slopes": [], "p1_deltas": [],
            "tp_counts": [], "tp_abs_swings": [],
        },
    }

    total = 0
    kept = 0
    for rid, g in df.groupby("rally_id"):
        total += 1
        # Exclude short rallies
        if len(g) < 4:
            continue
        # build base rally series
        base = build_timeseries_for_rally(g, args.fps)
        # compute turning points (can be empty)
        swings = compute_swing_points(g, args.swing)
        tps: List[Dict[str, Any]] = []
        tp_abs_swings: List[float] = []
        for tp in swings:
            frame = tp["frame"]
            tps.append({
                **tp,
                "time_sec": frame / args.fps if args.fps > 0 else frame / 30.0,
            })
            tp_abs_swings.append(abs(float(tp["swing"])))
        base["turning_points"] = sorted(tps, key=lambda x: x["stroke_no"]) if tps else []

        # score labels
        score_label, score_key = score_strings(str(rid))
        base["score_label"] = score_label
        base["score_key"] = score_key
        indices_by_score.setdefault(score_key, []).append(str(rid))

        # rally dynamics
        p0_dyn = compute_trend_for_player(g, "P0", args.trend_eps_slope, args.trend_eps_delta)
        p1_dyn = compute_trend_for_player(g, "P1", args.trend_eps_slope, args.trend_eps_delta)
        base["rally_dynamics"] = {
            "P0": p0_dyn,
            "P1": p1_dyn,
            "combined_category": combined_category(p0_dyn["category"], p1_dyn["category"]),
        }

        rallies[str(rid)] = base
        kept += 1

        # aggregate for summaries by outcome
        winner = base.get("winner")
        bucket = None
        if winner == "P0":
            bucket = agg["p0_won"]
        elif winner == "P1":
            bucket = agg["p0_lost"]
        if bucket is not None:
            bucket["categories"].append(base["rally_dynamics"]["combined_category"])
            bucket["p0_slopes"].append(p0_dyn["slope"])  # type: ignore[arg-type]
            bucket["p0_deltas"].append(p0_dyn["delta"])  # type: ignore[arg-type]
            bucket["p1_slopes"].append(p1_dyn["slope"])  # type: ignore[arg-type]
            bucket["p1_deltas"].append(p1_dyn["delta"])  # type: ignore[arg-type]
            bucket["tp_counts"].append(len(tps))
            bucket["tp_abs_swings"].extend(tp_abs_swings)

    def counts(items: List[str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for it in items:
            out[it] = out.get(it, 0) + 1
        return out

    def avg(values: List[float]) -> Optional[float]:
        if not values:
            return None
        return float(sum(values) / len(values))

    summaries = {}
    for key in ("p0_won", "p0_lost"):
        b = agg[key]
        summaries[key] = {
            "counts_by_category": counts(b["categories"]),
            "p0": {"avg_slope": avg(b["p0_slopes"]), "avg_delta": avg(b["p0_deltas"])},
            "p1": {"avg_slope": avg(b["p1_slopes"]), "avg_delta": avg(b["p1_deltas"])},
            "turning_points": {"avg_count": avg([float(x) for x in b["tp_counts"]]) if b["tp_counts"] else None, "avg_abs_swing": avg(b["tp_abs_swings"])},
            "num_rallies": len(b["p0_slopes"]),
        }

    payload = {
        "fps": args.fps,
        "threshold": args.swing,
        "indices": {"by_score": indices_by_score},
        "rallies": rallies,
        "summaries": summaries,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}  (included_rallies={kept}/{total}, min_strokes=4)")


if __name__ == "__main__":
    main()


