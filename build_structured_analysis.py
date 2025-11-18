import argparse
import os
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np


SECTION_1 = "1. Openings"
SECTION_2 = "2. Rally Dominance"
SECTION_3 = "3. Conversions"
SECTION_4 = "4. Crucial Point Conversions"
SECTION_5 = "5. Winning/Losing Patterns"
SECTION_6 = "6. Positive Swing Momentum"
SECTION_7 = "7. Negative Swing Momentum"


def parse_bool_like(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"true", "1", "t", "yes", "y"}


def to_float(value) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


def pick_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def add_rally_number(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    def _parse_rally_num(rid: str) -> Optional[int]:
        try:
            parts = str(rid).split("_")
            return int(parts[1]) if len(parts) > 1 else None
        except Exception:
            return None
    if "rally_number" not in df.columns and "rally_id" in df.columns:
        df["rally_number"] = df["rally_id"].apply(_parse_rally_num)
    return df


def ensure_rally_id(eff_df: pd.DataFrame) -> pd.DataFrame:
    if "rally_id" in eff_df.columns:
        return eff_df
    game_col = pick_col(eff_df, "GameNumber", "game_number", "Game")
    rally_col = pick_col(eff_df, "RallyNumber", "rally_number", "Rally")
    if game_col and rally_col:
        eff_df = eff_df.copy()
        eff_df["rally_id"] = eff_df[game_col].astype(str) + "_" + eff_df[rally_col].astype(str)
        return eff_df
    raise ValueError("Effectiveness CSV must have 'rally_id' or both GameNumber and RallyNumber.")


def compute_start_end_frames(eff_df: pd.DataFrame) -> pd.DataFrame:
    frame_col = pick_col(eff_df, "FrameNumber", "Frame")
    if frame_col is None:
        return pd.DataFrame(columns=["rally_id", "start_frame", "end_frame"])  # fallback empty
    agg = eff_df.groupby("rally_id")[frame_col].agg(["min", "max"]).reset_index()
    agg = agg.rename(columns={"min": "start_frame", "max": "end_frame"})
    return agg


# ===== Section 1a: Most common serve -> receive, per server, weighted score =====
def section_1a_most_common_serve_receive(eff_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    order_col = pick_col(eff_df, "StrokeNumber", "rally_position")
    stroke_col = pick_col(eff_df, "Stroke")
    player_col = pick_col(eff_df, "Player")
    eff_col = pick_col(eff_df, "effectiveness")
    frame_col = pick_col(eff_df, "FrameNumber", "Frame")
    if order_col is None or stroke_col is None or player_col is None or eff_col is None:
        return pd.DataFrame(columns=[
            "section","sub_section","actor","rally_id","game_number","rally_number","start_frame",
            "trigger_shot_number","trigger_shot","pattern_key","evidence_shots","metric_name","metric_value","frequency","weighted_score","notes"
        ])

    # Prepare base
    eff_df_local = eff_df.copy()
    eff_df_local[eff_col] = pd.to_numeric(eff_df_local[eff_col], errors="coerce")

    # For each rally, take first two shots
    top2 = (
        eff_df_local.sort_values(["rally_id", order_col])
        .groupby("rally_id")
        .head(2)
        .reset_index(drop=True)
    )

    # Keep rallies with exactly 2 rows (serve + receive)
    counts = top2.groupby("rally_id").size().reset_index(name="n")
    valid_ids = set(counts[counts["n"] == 2]["rally_id"].tolist())
    top2 = top2[top2["rally_id"].isin(valid_ids)].copy()

    # Pivot: first shot (serve), second shot (receive)
    def _pair_rows(g: pd.DataFrame) -> Optional[Dict[str, object]]:
        g2 = g.sort_values(order_col)
        r1 = g2.iloc[0]
        r2 = g2.iloc[1]
        recv_eff = to_float(r2[eff_col])
        if recv_eff is None:
            return None
        return {
            "rally_id": r1["rally_id"],
            "server": str(r1[player_col]),
            "serve_stroke": str(r1[stroke_col]),
            "receive_stroke": str(r2[stroke_col]),
            "receive_effectiveness": recv_eff,
            "start_frame": r1.get(frame_col, None),
        }

    records: List[Dict[str, object]] = []
    for rid, g in top2.groupby("rally_id"):
        rec = _pair_rows(g)
        if rec is not None:
            records.append(rec)
    df_pairs = pd.DataFrame(records)
    if df_pairs.empty:
        return pd.DataFrame(columns=[
            "section","sub_section","actor","rally_id","game_number","rally_number","start_frame",
            "trigger_shot_number","trigger_shot","pattern_key","evidence_shots","metric_name","metric_value","frequency","weighted_score","notes"
        ])

    # Aggregate by (server, serve_stroke, receive_stroke)
    agg = df_pairs.groupby(["server", "serve_stroke", "receive_stroke"]).agg(
        frequency=("rally_id", "count"),
        avg_receive_effectiveness=("receive_effectiveness", "mean"),
    ).reset_index()
    agg["weighted_score"] = agg["avg_receive_effectiveness"] * agg["frequency"]

    # Rank per server (P0, P1)
    results: List[Dict[str, object]] = []
    for actor in ["P0", "P1"]:
        sub = agg[agg["server"] == actor].copy()
        if sub.empty:
            continue
        sub = sub.sort_values(["weighted_score", "frequency"], ascending=[False, False]).head(4)
        # choose up to 5 exemplar rallies for each pattern (highest receive_effectiveness instances)
        for _, row in sub.iterrows():
            samples = df_pairs[
                (df_pairs["server"] == actor)
                & (df_pairs["serve_stroke"] == row["serve_stroke"]) 
                & (df_pairs["receive_stroke"] == row["receive_stroke"]) 
            ].sort_values("receive_effectiveness", ascending=False).head(5)
            if samples.empty:
                continue
            pattern_key = f"{row['serve_stroke']} → {row['receive_stroke']}"
            evidence_shots = f"{row['serve_stroke']} → {row['receive_stroke']}"
            for _, samp in samples.iterrows():
                results.append({
                    "section": SECTION_1,
                    "sub_section": "Most common serve → receive (weighted)",
                    "actor": actor,
                    "rally_id": samp["rally_id"],
                    "game_number": None,
                    "rally_number": None,
                    "trigger_shot_number": None,
                    "trigger_shot": None,
                    "pattern_key": pattern_key,
                    "evidence_shots": evidence_shots,
                    "metric_name": "avg_receive_effectiveness",
                    "metric_value": float(row["avg_receive_effectiveness"]),
                    "frequency": int(row["frequency"]),
                    "weighted_score": float(row["weighted_score"]),
                    "notes": "Top pattern exemplars",
                })

    out_df = pd.DataFrame(results)
    if not out_df.empty:
        out_df = add_rally_number(out_df)
        out_df = out_df.merge(start_frames, on="rally_id", how="left")
        # normalize any stray control arrows
        out_df["evidence_shots"] = out_df["evidence_shots"].str.replace("\u0001", "→")
        out_df["pattern_key"] = out_df["pattern_key"].str.replace("\u0001", "→")
    return out_df


# ===== Section 1b/1c: Effective and Ineffective receives per actor (shot-2 effectiveness only) =====
def section_1bc_receive_quality(eff_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    order_col = pick_col(eff_df, "StrokeNumber", "rally_position")
    stroke_col = pick_col(eff_df, "Stroke")
    player_col = pick_col(eff_df, "Player")
    eff_col = pick_col(eff_df, "effectiveness")
    frame_col = pick_col(eff_df, "FrameNumber", "Frame")
    if order_col is None or stroke_col is None or player_col is None or eff_col is None:
        return pd.DataFrame()

    eff_df_local = eff_df.copy()
    eff_df_local[eff_col] = pd.to_numeric(eff_df_local[eff_col], errors="coerce")
    # Get first two shots per rally
    top2 = (
        eff_df_local.sort_values(["rally_id", order_col])
        .groupby("rally_id")
        .head(2)
        .reset_index(drop=True)
    )
    counts = top2.groupby("rally_id").size().reset_index(name="n")
    valid_ids = set(counts[counts["n"] == 2]["rally_id"].tolist())
    top2 = top2[top2["rally_id"].isin(valid_ids)].copy()

    # Build receive-only table (shot2)
    def _receive_row(g: pd.DataFrame) -> Optional[Dict[str, object]]:
        g2 = g.sort_values(order_col)
        r2 = g2.iloc[1]
        recv_eff = to_float(r2[eff_col])
        if recv_eff is None:
            return None
        r1 = g2.iloc[0]
        return {
            "rally_id": r2["rally_id"],
            "receiver": str(r2[player_col]),
            "serve_stroke": str(r1[stroke_col]),
            "receive_stroke": str(r2[stroke_col]),
            "receive_effectiveness": recv_eff,
            "start_frame": r1.get(frame_col, None),
        }

    records: List[Dict[str, object]] = []
    for rid, g in top2.groupby("rally_id"):
        rec = _receive_row(g)
        if rec is not None:
            records.append(rec)
    df_recv = pd.DataFrame(records)
    if df_recv.empty:
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    for actor in ["P0", "P1"]:
        sub = df_recv[df_recv["receiver"] == actor].copy()
        if sub.empty:
            continue
        # Effective receives (top 4)
        eff_top = sub.sort_values("receive_effectiveness", ascending=False).head(4)
        for _, r in eff_top.iterrows():
            rows.append({
                "section": SECTION_1,
                "sub_section": "Effective receives (by receive effectiveness)",
                "actor": actor,
                "rally_id": r["rally_id"],
                "game_number": None,
                "rally_number": None,
                # start_frame merged later
                "trigger_shot_number": 2,
                "trigger_shot": r["receive_stroke"],
                "pattern_key": f"{r['serve_stroke']} → {r['receive_stroke']}",
                "evidence_shots": f"{r['serve_stroke']} → {r['receive_stroke']}",
                "metric_name": "receive_effectiveness",
                "metric_value": float(r["receive_effectiveness"]),
                "frequency": 1,
                "weighted_score": None,
                "notes": "Top-4 highest receive effectiveness per actor",
            })
        # Ineffective receives (bottom 4)
        eff_bot = sub.sort_values("receive_effectiveness", ascending=True).head(4)
        for _, r in eff_bot.iterrows():
            rows.append({
                "section": SECTION_1,
                "sub_section": "Ineffective receives (by receive effectiveness)",
                "actor": actor,
                "rally_id": r["rally_id"],
                "game_number": None,
                "rally_number": None,
                # start_frame merged later
                "trigger_shot_number": 2,
                "trigger_shot": r["receive_stroke"],
                "pattern_key": f"{r['serve_stroke']} → {r['receive_stroke']}",
                "evidence_shots": f"{r['serve_stroke']} → {r['receive_stroke']}",
                "metric_name": "receive_effectiveness",
                "metric_value": float(r["receive_effectiveness"]),
                "frequency": 1,
                "weighted_score": None,
                "notes": "Top-4 lowest receive effectiveness per actor",
            })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = add_rally_number(out)
        out = out.merge(start_frames, on="rally_id", how="left")
    return out


def merge_outputs(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [d for d in dfs if d is not None and not d.empty]
    if not non_empty:
        return pd.DataFrame(columns=[
            "section","sub_section","actor","rally_id","game_number","rally_number","start_frame",
            "trigger_shot_number","trigger_shot","pattern_key","evidence_shots","metric_name","metric_value","frequency","weighted_score","notes"
        ])
    out = pd.concat(non_empty, ignore_index=True)
    # Normalize actor labels to "you" / "opponent" if desired; keep P0/P1 in CSV per request
    return out


# ===== Helpers for phases and turning points =====
PHASE_ARROW = "→"

def simplify_phase_sequence(phases_text: Optional[str]) -> Optional[str]:
    if phases_text is None or not isinstance(phases_text, str) or not phases_text.strip():
        return None
    parts = [p.strip() for p in phases_text.split("→")]
    labels: List[str] = []
    for p in parts:
        if not p:
            continue
        label = p.split("(")[0].strip()
        if not label:
            continue
        if len(labels) == 0 or labels[-1] != label:
            labels.append(label)
    if not labels:
        return None
    return f" {PHASE_ARROW} ".join(labels)


TP_RE = re.compile(r"TURNING POINT Shot\s+(\d+):\s*([^()]+)\(.*?([+-]?\d+)\s*swing\)")

def parse_turning_points_from_text(text: Optional[str]) -> List[Dict[str, object]]:
    if text is None or not isinstance(text, str):
        return []
    results: List[Dict[str, object]] = []
    for m in TP_RE.finditer(text):
        try:
            shot_num = int(m.group(1))
            shot_type = m.group(2).strip().rstrip(",")
            swing = float(m.group(3))
            results.append({
                "shot_position": shot_num,
                "shot_type": shot_type,
                "swing": swing,
            })
        except Exception:
            continue
    return results


# Parse phase windows like "Serve(1-1) → Net Battle(3-5)"
SEG_RE = re.compile(r"\s*([^()]+?)\s*\((\d+)-(\d+)\)\s*")

def parse_phase_ranges(phases_text: Optional[str]) -> List[Dict[str, object]]:
    if phases_text is None or not isinstance(phases_text, str) or not phases_text.strip():
        return []
    parts = [p.strip() for p in phases_text.split("→")]
    out: List[Dict[str, object]] = []
    for p in parts:
        m = SEG_RE.match(p)
        if not m:
            continue
        label = m.group(1).strip()
        try:
            start = int(m.group(2))
            end = int(m.group(3))
        except Exception:
            continue
        if start > 0 and end >= start:
            out.append({"label": label, "start": start, "end": end})
    return out

# Winner map helper
def build_winner_map(eff_df: pd.DataFrame) -> pd.DataFrame:
    win_col = pick_col(eff_df, "RallyWinner", "rally_winner")
    if win_col is not None and win_col in eff_df.columns:
        winners = eff_df.groupby("rally_id").agg({win_col: "first"}).reset_index().rename(columns={win_col: "rally_winner"})
        if not winners.empty:
            return winners
    # Fallback from winning/losing shot flags
    win_flag_col = pick_col(eff_df, "IsWinningShot", "is_winning_shot")
    lose_flag_col = pick_col(eff_df, "IsLosingShot", "is_losing_shot")
    player_col = pick_col(eff_df, "Player")
    rows: List[Dict[str, object]] = []
    for rid, g in eff_df.groupby("rally_id"):
        g2 = g.reset_index(drop=True)
        winner = None
        if win_flag_col and player_col:
            hits = g2[g2[win_flag_col].astype(str).str.upper().isin(["TRUE", "1", "T", "YES"]) if g2[win_flag_col].dtype != bool else g2[win_flag_col]]
            if not hits.empty:
                winner = str(hits.iloc[-1][player_col])
        if winner is None and lose_flag_col and player_col:
            loses = g2[g2[lose_flag_col].astype(str).str.upper().isin(["TRUE", "1", "T", "YES"]) if g2[lose_flag_col].dtype != bool else g2[lose_flag_col]]
            if not loses.empty:
                loser = str(loses.iloc[-1][player_col])
                winner = "P0" if loser == "P1" else "P1"
        if winner is not None:
            rows.append({"rally_id": rid, "rally_winner": winner})
    return pd.DataFrame(rows)

# ===== Section 2: Rally Dominance (pick highest stage per rally, per actor) =====
def section_2_rally_dominance(eff_df: pd.DataFrame, narratives_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    order_col = pick_col(eff_df, "StrokeNumber", "rally_position")
    eff_col = pick_col(eff_df, "effectiveness")
    stroke_col = pick_col(eff_df, "Stroke")
    player_col = pick_col(eff_df, "Player")
    if order_col is None or eff_col is None or stroke_col is None or player_col is None:
        return pd.DataFrame()

    eff_local = eff_df.copy()
    eff_local[eff_col] = pd.to_numeric(eff_local[eff_col], errors="coerce")
    eff_local = eff_local.sort_values(["rally_id", order_col])

    # Map rally_id -> phases for both actors
    narr_idx = narratives_df.set_index("rally_id") if "rally_id" in narratives_df.columns else None

    def _phase_windows_for_actor(rid: str, actor: str) -> List[Dict[str, object]]:
        if narr_idx is None:
            return []
        col = "P0_phases" if actor == "P0" else "P1_phases"
        if col not in narr_idx.columns:
            return []
        try:
            text = narr_idx.at[rid, col]
        except Exception:
            return []
        return parse_phase_ranges(text)

    rows: List[Dict[str, object]] = []
    for rid, g in eff_local.groupby("rally_id", sort=False):
        g2 = g.reset_index(drop=True)
        for actor in ["P0", "P1"]:
            phase_windows = _phase_windows_for_actor(rid, actor)
            if not phase_windows:
                continue
            best_label = None
            best_range: Tuple[int, int] = (0, 0)
            best_adv = None
            for seg in phase_windows:
                a = int(seg["start"])
                b = int(seg["end"])
                seg_df = g2[(g2[order_col] >= a) & (g2[order_col] <= b)]
                if seg_df.empty:
                    continue
                p_actor = seg_df[seg_df[player_col] == actor][eff_col].dropna()
                p_opp = seg_df[seg_df[player_col] != actor][eff_col].dropna()
                if len(p_actor) == 0 and len(p_opp) == 0:
                    continue
                act_mean = float(p_actor.mean()) if len(p_actor) else np.nan
                opp_mean = float(p_opp.mean()) if len(p_opp) else np.nan
                if np.isnan(act_mean) and np.isnan(opp_mean):
                    continue
                if np.isnan(opp_mean):
                    adv = act_mean
                elif np.isnan(act_mean):
                    adv = -opp_mean
                else:
                    adv = act_mean - opp_mean
                if (best_adv is None) or (adv > best_adv):
                    best_adv = adv
                    best_label = str(seg["label"])
                    best_range = (a, b)
            if best_adv is None:
                continue
            a, b = best_range
            # evidence shots from best phase window (cap 6)
            ev_seg = g2[(g2[order_col] >= a) & (g2[order_col] <= b)]
            ev_strokes = ev_seg[stroke_col].astype(str).tolist()[:6]
            rows.append({
                "section": SECTION_2,
                "sub_section": f"Dominant phase: {best_label}",
                "actor": actor,
                "rally_id": rid,
                "game_number": None,
                "rally_number": None,
                "start_frame": None,
                "trigger_shot_number": None,
                "trigger_shot": None,
                "pattern_key": best_label,
                "evidence_shots": " → ".join(ev_strokes),
                "metric_name": "phase_advantage",
                "metric_value": float(best_adv),
                "frequency": 1,
                "weighted_score": None,
                "notes": "Highest-advantage phase window",
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = add_rally_number(out)
    out = out.merge(start_frames, on="rally_id", how="left")
    final_rows: List[pd.DataFrame] = []
    for actor in ["P0", "P1"]:
        sub = out[out["actor"] == actor].sort_values(["metric_value"], ascending=False).head(4)
        final_rows.append(sub)
    return pd.concat(final_rows, ignore_index=True)


# ===== Section 3: Conversions based on overall avg effectiveness =====
def section_3_conversions(eff_df: pd.DataFrame, narratives_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    eff_col = pick_col(eff_df, "effectiveness")
    player_col = pick_col(eff_df, "Player")
    if eff_col is None or player_col is None:
        return pd.DataFrame()
    win_col = pick_col(eff_df, "RallyWinner", "rally_winner")
    if win_col is None:
        return pd.DataFrame()

    eff_local = eff_df.copy()
    eff_local[eff_col] = pd.to_numeric(eff_local[eff_col], errors="coerce")
    avg_eff = eff_local.groupby(["rally_id", player_col])[eff_col].mean().reset_index().rename(columns={eff_col: "avg_effectiveness"})
    winners = build_winner_map(eff_local)
    df = avg_eff.merge(winners, on="rally_id", how="left")
    # shot counts per rally
    shots_count = eff_local.groupby("rally_id").size().reset_index(name="shots_count")
    df = df.merge(shots_count, on="rally_id", how="left")

    shots_map = narratives_df.set_index("rally_id").to_dict().get("shot_sequence", {}) if "shot_sequence" in narratives_df.columns else {}

    rows: List[Dict[str, object]] = []
    for actor in ["P0", "P1"]:
        sub = df[df[player_col] == actor].copy()
        if sub.empty:
            continue
        conv = sub[sub["rally_winner"].astype(str) == actor].sort_values("avg_effectiveness", ascending=False).head(4)
        for _, r in conv.iterrows():
            rows.append({
                "section": SECTION_3,
                "sub_section": "Converted (high avg eff → win)",
                "actor": actor,
                "rally_id": r["rally_id"],
                "game_number": None,
                "rally_number": None,
                "start_frame": None,
                "trigger_shot_number": None,
                "trigger_shot": None,
                "pattern_key": None,
                "evidence_shots": str(shots_map.get(r["rally_id"], ""))[:200],
                "metric_name": "avg_effectiveness",
                "metric_value": float(r["avg_effectiveness"]),
                "frequency": 1,
                "weighted_score": None,
                "notes": "Top-4 by average effectiveness (actor won)",
            })
        # Failed to convert
        fail = sub[(sub["rally_winner"].astype(str) != actor) & (sub.get("shots_count", 0) > 5)].sort_values("avg_effectiveness", ascending=False).head(4)
        for _, r in fail.iterrows():
            rows.append({
                "section": SECTION_3,
                "sub_section": "Failed to convert (high avg eff → loss)",
                "actor": actor,
                "rally_id": r["rally_id"],
                "game_number": None,
                "rally_number": None,
                "start_frame": None,
                "trigger_shot_number": None,
                "trigger_shot": None,
                "pattern_key": None,
                "evidence_shots": str(shots_map.get(r["rally_id"], ""))[:200],
                "metric_name": "avg_effectiveness",
                "metric_value": float(r["avg_effectiveness"]),
                "frequency": 1,
                "weighted_score": None,
                "notes": ">5 shots; Top-4 by average effectiveness (actor lost)",
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = add_rally_number(out)
    out = out.merge(start_frames, on="rally_id", how="left")
    return out


# ===== Section 4: Crucial point conversions (high-level strategy) =====
def section_4_crucial_patterns(eff_df: pd.DataFrame, narratives_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    if "IsCrucial" in eff_df.columns:
        mask_crucial = eff_df["IsCrucial"].astype(str).str.upper().isin(["TRUE", "1", "T", "YES"])
        is_crucial_eff = set(eff_df[mask_crucial]["rally_id"].astype(str).tolist())
    else:
        is_crucial_eff = set()
    is_crucial_narr = set(narratives_df[narratives_df.get("phase", "").astype(str).str.contains("crucial", case=False, na=False)]["rally_id"].astype(str).tolist()) if "phase" in narratives_df.columns else set()
    crucial_ids = is_crucial_eff.union(is_crucial_narr)
    if not crucial_ids:
        return pd.DataFrame()

    df = narratives_df.copy()
    df = df[df["rally_id"].astype(str).isin(crucial_ids)]
    if df.empty:
        return pd.DataFrame()
    # Use existing rally_winner from narratives if available, otherwise build from eff_df
    if "rally_winner" not in df.columns:
        winners = build_winner_map(eff_df)
        df = df.merge(winners, on="rally_id", how="left", suffixes=("", "_y"))
        # If merge created _y suffix, use it; otherwise use existing
        if "rally_winner_y" in df.columns:
            df["rally_winner"] = df["rally_winner"].fillna(df["rally_winner_y"])
            df = df.drop(columns=["rally_winner_y"])
    if "rally_winner" not in df.columns:
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    # Emit ALL crucial instances per actor: converted vs not converted (no aggregation)
    for actor, col in [("P0", "P0_phases"), ("P1", "P1_phases")]:
        if col not in df.columns:
            continue
        df_actor = df.copy()
        # Build simplified pattern if available; allow missing patterns
        if col in df_actor.columns:
            df_actor["pattern"] = df_actor[col].apply(simplify_phase_sequence)
        if df_actor.empty:
            continue
        df_actor["converted"] = df_actor["rally_winner"].astype(str) == actor
        for _, samp in df_actor.iterrows():
            rows.append({
                "section": SECTION_4,
                "sub_section": "Crucial converted" if bool(samp["converted"]) else "Crucial not converted",
                "actor": actor,
                "rally_id": samp["rally_id"],
                "game_number": samp.get("game_number"),
                "rally_number": None,
                "start_frame": None,
                "trigger_shot_number": None,
                "trigger_shot": None,
                "pattern_key": samp.get("pattern") if "pattern" in samp else None,
                "evidence_shots": str(narratives_df.set_index("rally_id").get("shot_sequence", {}).get(samp["rally_id"], ""))[:200],
                "metric_name": "converted",
                "metric_value": 1 if bool(samp["converted"]) else 0,
                "frequency": 1,
                "weighted_score": None,
                "notes": None,
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = add_rally_number(out)
    out = out.merge(start_frames, on="rally_id", how="left")
    return out


# ===== Section 5: Winning & Losing rally patterns =====
def section_5_patterns(eff_df: pd.DataFrame, narratives_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    win_col = pick_col(eff_df, "RallyWinner", "rally_winner")
    eff_col = pick_col(eff_df, "effectiveness")
    player_col = pick_col(eff_df, "Player")
    if win_col is None or eff_col is None or player_col is None:
        return pd.DataFrame()
    eff_local = eff_df.copy()
    eff_local[eff_col] = pd.to_numeric(eff_local[eff_col], errors="coerce")
    actor_avg = eff_local.groupby(["rally_id", player_col])[eff_col].mean().reset_index().rename(columns={eff_col: "avg_effectiveness"})

    df = narratives_df.copy()
    # Use existing rally_winner from narratives if available, otherwise build from eff_local
    if "rally_winner" not in df.columns:
        winners = build_winner_map(eff_local)
        df = df.merge(winners, on="rally_id", how="left", suffixes=("", "_y"))
        # If merge created _y suffix, use it; otherwise use existing
        if "rally_winner_y" in df.columns:
            df["rally_winner"] = df["rally_winner"].fillna(df["rally_winner_y"])
            df = df.drop(columns=["rally_winner_y"])
    if "rally_winner" not in df.columns:
        return pd.DataFrame()
    rows: List[Dict[str, object]] = []
    for actor, col in [("P0", "P0_phases"), ("P1", "P1_phases")]:
        if col not in df.columns:
            continue
        df_actor = df.copy()
        df_actor["pattern"] = df_actor[col].apply(simplify_phase_sequence)
        df_actor = df_actor.dropna(subset=["pattern"])
        if df_actor.empty:
            continue
        avg_map = actor_avg[actor_avg[player_col] == actor][["rally_id", "avg_effectiveness"]]
        df_actor = df_actor.merge(avg_map, on="rally_id", how="left")

        for outcome, label in [(True, "Winning patterns"), (False, "Losing patterns")]:
            subset = df_actor[(df_actor["rally_winner"].astype(str) == actor) == outcome]
            if subset.empty:
                continue
            agg = subset.groupby("pattern").agg(
                frequency=("rally_id", "count"),
                avg_eff_over_examples=("avg_effectiveness", "mean"),
            ).reset_index().sort_values(["frequency", "avg_eff_over_examples"], ascending=[False, False]).head(4)
            for _, arow in agg.iterrows():
                exemplars = subset[subset["pattern"] == arow["pattern"]].head(5)
                for _, samp in exemplars.iterrows():
                    rows.append({
                        "section": SECTION_5,
                        "sub_section": label,
                        "actor": actor,
                        "rally_id": samp["rally_id"],
                        "game_number": samp.get("game_number"),
                        "rally_number": None,
                        "start_frame": None,
                        "trigger_shot_number": None,
                        "trigger_shot": None,
                        "pattern_key": arow["pattern"],
                        "evidence_shots": str(narratives_df.set_index("rally_id").get("shot_sequence", {}).get(samp["rally_id"], ""))[:200],
                        "metric_name": "frequency",
                        "metric_value": int(arow["frequency"]),
                        "frequency": int(arow["frequency"]),
                        "weighted_score": None,
                        "notes": "Phase pattern exemplars; tie-break avg effectiveness",
                    })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = add_rally_number(out)
    out = out.merge(start_frames, on="rally_id", how="left")
    return out


# ===== Section 6 and 7: Swing momentum rallies =====
def _map_shot_to_frame_and_context(eff_df: pd.DataFrame, rid: str, shot_num: int, order_col: str, stroke_col: str, frame_col: Optional[str]) -> Tuple[Optional[int], str]:
    g = eff_df[eff_df["rally_id"].astype(str) == str(rid)].copy()
    if g.empty:
        return None, ""
    g = g.sort_values(order_col)
    if frame_col is not None:
        frame = g[g[order_col] == shot_num].get(frame_col)
        frame_val = int(frame.iloc[0]) if frame is not None and len(frame) > 0 else None
    else:
        frame_val = None
    context = g[(g[order_col] >= shot_num - 1) & (g[order_col] <= shot_num + 1)][stroke_col].astype(str).tolist()
    context_str = " → ".join(context)
    return frame_val, context_str


def section_6_7_swings(eff_df: pd.DataFrame, narratives_df: pd.DataFrame, start_frames: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    order_col = pick_col(eff_df, "StrokeNumber", "rally_position")
    stroke_col = pick_col(eff_df, "Stroke")
    frame_col = pick_col(eff_df, "FrameNumber", "Frame")
    if order_col is None or stroke_col is None:
        return pd.DataFrame(), pd.DataFrame()

    records: List[Dict[str, object]] = []
    for _, r in narratives_df.iterrows():
        rid = r.get("rally_id")
        for actor, narr_col in [("P0", "P0_narrative"), ("P1", "P1_narrative")]:
            if narr_col not in narratives_df.columns:
                continue
            text = r.get(narr_col)
            tps = parse_turning_points_from_text(text)
            for tp in tps:
                frame_val, context_str = _map_shot_to_frame_and_context(eff_df, rid, int(tp["shot_position"]), order_col, stroke_col, frame_col)
                records.append({
                    "actor": actor,
                    "rally_id": rid,
                    "shot_position": int(tp["shot_position"]),
                    "shot_type": tp["shot_type"],
                    "swing": float(tp["swing"]),
                    "trigger_frame": frame_val,
                    "context": context_str,
                })

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Build ranking by trigger shot type using weighted_score = frequency * abs(mean swing)
    def _rank_and_emit(df_in: pd.DataFrame, positive: bool) -> pd.DataFrame:
        if positive:
            df_sign = df_in[df_in["swing"] > 0]
            section = SECTION_6
            sub_section = "+ve swing momentum"
        else:
            df_sign = df_in[df_in["swing"] < 0]
            section = SECTION_7
            sub_section = "-ve swing momentum"
        if df_sign.empty:
            return pd.DataFrame()
        agg = df_sign.groupby(["actor", "shot_type"]).agg(
            frequency=("rally_id", "count"),
            mean_swing=("swing", "mean"),
        ).reset_index()
        agg["weighted_score"] = agg["frequency"] * agg["mean_swing"].abs()
        rows: List[Dict[str, object]] = []
        for actor in ["P0", "P1"]:
            top = agg[agg["actor"] == actor].sort_values(["weighted_score", "frequency"], ascending=[False, False]).head(4)
            for _, trig in top.iterrows():
                exemplars = df_sign[(df_sign["actor"] == actor) & (df_sign["shot_type"] == trig["shot_type"])].sort_values("swing", ascending=not positive).head(4)
                for _, x in exemplars.iterrows():
                    rows.append({
                        "section": section,
                        "sub_section": sub_section,
                        "actor": actor,
                        "rally_id": x["rally_id"],
                        "game_number": None,
                        "rally_number": None,
                        "start_frame": None,
                        "trigger_shot_number": int(x["shot_position"]),
                        "trigger_shot": str(trig["shot_type"]),
                        "pattern_key": str(trig["shot_type"]),
                        "evidence_shots": x["context"],
                        "metric_name": "weighted_score",
                        "metric_value": float(trig["weighted_score"]),
                        "frequency": int(trig["frequency"]),
                        "weighted_score": float(trig["weighted_score"]),
                        "notes": f"mean_swing={trig['mean_swing']:.1f}",
                        "trigger_frame": x.get("trigger_frame"),
                    })
        return pd.DataFrame(rows)

    pos_df = _rank_and_emit(df, True)
    neg_df = _rank_and_emit(df, False)
    if not pos_df.empty:
        pos_df = add_rally_number(pos_df).merge(start_frames, on="rally_id", how="left")
    if not neg_df.empty:
        neg_df = add_rally_number(neg_df).merge(start_frames, on="rally_id", how="left")
    return pos_df, neg_df


# ===== Section 8: Winners and Errors with rally lengths =====
def section_8_outcomes(eff_df: pd.DataFrame, start_frames: pd.DataFrame) -> pd.DataFrame:
    order_col = pick_col(eff_df, "StrokeNumber", "rally_position")
    eff_col = pick_col(eff_df, "effectiveness")
    player_col = pick_col(eff_df, "Player")
    if order_col is None or player_col is None:
        return pd.DataFrame()

    df = eff_df.copy().sort_values(["rally_id", order_col])
    winners = build_winner_map(df)
    # rally lengths
    lengths = df.groupby("rally_id").size().reset_index(name="rally_length")
    # last-shot per rally to detect error type and erroring player
    last_shots = df.groupby("rally_id").tail(1).copy()
    label_col = pick_col(last_shots, "effectiveness_label")
    reason_col = pick_col(last_shots, "reason")
    lose_flag_col = pick_col(last_shots, "IsLosingShot", "is_losing_shot")

    rows: List[Dict[str, object]] = []

    # Winner rows summary only (no per-rally rows)
    win_rows = winners.merge(lengths, on="rally_id", how="left").merge(start_frames, on="rally_id", how="left")

    # Totals per winner
    totals = win_rows.groupby("rally_winner").size().reset_index(name="count")
    for _, r in totals.iterrows():
        rows.append({
            "section": "8. Outcomes",
            "sub_section": "Total winners",
            "actor": str(r["rally_winner"]),
            "rally_id": None,
            "game_number": None,
            "rally_number": None,
            "trigger_shot_number": None,
            "trigger_shot": None,
            "pattern_key": None,
            "evidence_shots": None,
            "metric_name": "count",
            "metric_value": int(r["count"]),
            "frequency": int(r["count"]),
            "weighted_score": None,
            "notes": None,
            "start_frame": None,
        })

    # Error totals (Unforced/Forced) per actor only (no per-rally rows)
    err_rows = last_shots.merge(lengths, on="rally_id", how="left")
    error_records: List[Dict[str, str]] = []
    for _, r in err_rows.iterrows():
        losing = False
        if lose_flag_col and lose_flag_col in err_rows.columns:
            val = r.get(lose_flag_col)
            losing = bool(val) if isinstance(val, bool) else str(val).upper() in ["TRUE", "1", "T", "YES"]
        if not losing:
            continue
        actor = str(r.get(player_col))
        label = str(r.get(label_col)) if label_col else ""
        reason = str(r.get(reason_col)) if reason_col else ""
        if "unforced" in label.lower() or "unforced" in reason.lower():
            typ = "Unforced errors"
        elif "forced" in label.lower() or "forced" in reason.lower():
            typ = "Forced errors"
        else:
            continue
        error_records.append({"actor": actor, "typ": typ})

    if error_records:
        err_df = pd.DataFrame(error_records)
        totals_err = err_df.groupby(["actor", "typ"]).size().reset_index(name="count")
        for _, r in totals_err.iterrows():
            rows.append({
                "section": "8. Outcomes",
                "sub_section": f"Total {r['typ']}",
                "actor": str(r["actor"]),
                "rally_id": None,
                "game_number": None,
                "rally_number": None,
                "trigger_shot_number": None,
                "trigger_shot": None,
                "pattern_key": None,
                "evidence_shots": None,
                "metric_name": "count",
                "metric_value": int(r["count"]),
                "frequency": int(r["count"]),
                "weighted_score": None,
                "notes": None,
                "start_frame": None,
            })

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = add_rally_number(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build structured analysis CSV from narratives+shots and effectiveness CSVs.")
    ap.add_argument("narratives_with_shots", type=str, help="Path to rally_narratives_enriched_with_shots.csv")
    ap.add_argument("effectiveness_csv", type=str, help="Path to *_detailed_effectiveness.csv")
    ap.add_argument("output_csv", type=str, nargs="?", default=None, help="Output CSV path (default: structured_analysis.csv next to narratives)")
    args = ap.parse_args()

    narratives_csv = args.narratives_with_shots
    eff_csv = args.effectiveness_csv
    out_csv = args.output_csv
    if out_csv is None:
        out_csv = os.path.join(os.path.dirname(os.path.abspath(narratives_csv)), "structured_analysis.csv")

    # Load
    narr = pd.read_csv(narratives_csv)
    eff = pd.read_csv(eff_csv)
    eff = ensure_rally_id(eff)

    # Frames summary for joins
    start_end = compute_start_end_frames(eff)

    # Sections
    sec_1a = section_1a_most_common_serve_receive(eff, start_end[["rally_id", "start_frame"]])
    sec_1bc = section_1bc_receive_quality(eff, start_end[["rally_id", "start_frame"]])
    sec_2 = section_2_rally_dominance(eff, narr, start_end[["rally_id", "start_frame"]])
    sec_3 = section_3_conversions(eff, narr, start_end[["rally_id", "start_frame"]])
    sec_4 = section_4_crucial_patterns(eff, narr, start_end[["rally_id", "start_frame"]])
    sec_5 = section_5_patterns(eff, narr, start_end[["rally_id", "start_frame"]])
    sec_6, sec_7 = section_6_7_swings(eff, narr, start_end[["rally_id", "start_frame"]])
    sec_8 = section_8_outcomes(eff, start_end[["rally_id", "start_frame"]])

    final_df = merge_outputs([sec_1a, sec_1bc, sec_2, sec_3, sec_4, sec_5, sec_6, sec_7, sec_8])
    # Coalesce start_frame columns
    if "start_frame" not in final_df.columns:
        final_df["start_frame"] = np.nan
    for col in ["start_frame_x", "start_frame_y"]:
        if col in final_df.columns:
            final_df["start_frame"] = final_df["start_frame"].fillna(final_df[col])
            final_df = final_df.drop(columns=[col])
    final_df.to_csv(out_csv, index=False)
    print(f"Wrote: {out_csv}  (rows={len(final_df)})")


if __name__ == "__main__":
    main()


