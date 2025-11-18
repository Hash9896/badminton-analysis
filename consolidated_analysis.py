import argparse
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import pandas as pd


ROWTYPE_RALLY_OUTCOME = "rally_outcome"
ROWTYPE_SR_PATTERN_AGG = "sr_pattern_agg"
ROWTYPE_THREE_SHOT_SEQUENCE = "three_shot_sequence"
ROWTYPE_THREE_SHOT_SUMMARY = "three_shot_summary"
ROWTYPE_SHOT_TIMELINE = "shot_timeline"
ROWTYPE_SHOT_VARIATION_AGG = "shot_variation_agg"


def _fixed_columns() -> List[str]:
    return [
        # Core
        "RowType",
        "GameNumber",
        "RallyNumber",
        "Player",  # used by shot_variation_agg
        # Phase (with explicit context)
        "Phase",
        "PhaseContext",  # Service | TargetShot | RallyEnd
        # Rally-level summary (only for rally_outcome rows)
        "StartFrame",
        "EndFrame",
        "RallyDurationFrames",
        "StrokeCount",
        "Winner",
        "Loser",
        "ScoreP0_Before",
        "ScoreP1_Before",
        "ScoreP0_After",
        "ScoreP1_After",
        "OutcomeType",
        "OutcomeReason",
        # Rally narratives enrichment (optional)
        "RallyNarrativePhase",
        "RallyNarrativeTotalShots",
        "P0_Narrative",
        "P1_Narrative",
        "P0_Phases",
        "P1_Phases",
        "P0_TurningPoints",
        "P1_TurningPoints",
        # Anchor shot fields (meaning depends on RowType)
        "AnchorShotNumber",
        "AnchorPlayer",
        "AnchorStroke",
        "AnchorFrameNumber",
        "AnchorFrameId",
        # Anchor shot variation
        "AnchorHittingZone",
        "AnchorDirection",
        "AnchorLandingPosition",
        # Classification flags (for rally_outcome)
        "IsWinnerShot",
        "IsErrorShot",
        # Anchor shot effectiveness/context (merged from effectiveness CSV if provided)
        "AnchorIsServe",
        "AnchorScore",
        "AnchorBand",
        "AnchorRallyPosition",
        "AnchorRallyId",
        "AnchorRallyWinner",
        "AnchorRallyLoser",
        "AnchorIsWinningShot",
        "AnchorIsLosingShot",
        "AnchorColor",
        "AnchorEffectiveness",
        "AnchorEffectivenessLabel",
        "AnchorReason",
        # Service–receive aggregated pattern fields
        "Server",
        "PatternServeShot",
        "PatternReceiveShot",
        "PatternServeFrameExample1",
        "PatternReceiveFrameExample1",
        "PatternServeFrameExample2",
        "PatternReceiveFrameExample2",
        "PatternServeFrameExample3",
        "PatternReceiveFrameExample3",
        "Count",
        # Three-shot sequence fields
        "SequenceType",
        "SequenceLength",
        "SequenceShots",
        "SequenceFrameNumbers",
        "FirstFrame",
        "TargetFrame",
        # Shot variation aggregate fields
        "HittingZone",
        "ShotType",
        "Direction",
        "LandingPosition",
    ]


def _empty_row(row_type: str) -> Dict:
    row = {col: pd.NA for col in _fixed_columns()}
    row["RowType"] = row_type
    return row


def _infer_winners(df: pd.DataFrame) -> Dict[Tuple[int, int], str]:
    """Return mapping (GameNumber, RallyNumber) -> Winner ('P0'|'P1')."""
    winners: Dict[Tuple[int, int], str] = {}

    # Ensure sorted
    df_sorted = df.sort_values(["GameNumber", "RallyNumber", "StrokeNumber"])  # type: ignore[arg-type]
    # Distinct rallies ordered
    rally_keys = (
        df_sorted[["GameNumber", "RallyNumber"]]
        .drop_duplicates()
        .sort_values(["GameNumber", "RallyNumber"])  # type: ignore[arg-type]
        .values
        .tolist()
    )

    # Winner for all but last rally in a game -> server of next rally
    for i in range(len(rally_keys) - 1):
        cur_game, cur_rally = rally_keys[i]
        next_game, next_rally = rally_keys[i + 1]
        if cur_game != next_game:
            continue
        next_first = df_sorted[
            (df_sorted["GameNumber"] == next_game)
            & (df_sorted["RallyNumber"] == next_rally)
            & (df_sorted["StrokeNumber"] == 1)
        ]
        if next_first.empty:
            continue
        winners[(cur_game, cur_rally)] = str(next_first.iloc[0]["Player"])  # winner serves next

    # For last rally in each game, infer from final scores
    for game in sorted(df_sorted["GameNumber"].unique().tolist()):  # type: ignore[call-arg]
        last_rally = int(df_sorted[df_sorted["GameNumber"] == game]["RallyNumber"].max())
        last_rally_df = df_sorted[(df_sorted["GameNumber"] == game) & (df_sorted["RallyNumber"] == last_rally)]
        if last_rally_df.empty:
            continue
        last_shot = last_rally_df.iloc[-1]
        if int(last_shot["ScoreP0"]) > int(last_shot["ScoreP1"]):
            winners[(game, last_rally)] = "P0"
        else:
            winners[(game, last_rally)] = "P1"

    return winners


def _build_rally_outcome_rows(df: pd.DataFrame, winners: Dict[Tuple[int, int], str]) -> List[Dict]:
    rows: List[Dict] = []
    grouped = df.groupby(["GameNumber", "RallyNumber"], sort=False)
    for (game, rally), r in grouped:
        r_sorted = r.sort_values(["StrokeNumber"])  # type: ignore[arg-type]
        if r_sorted.empty:
            continue
        last = r_sorted.iloc[-1]
        winner = winners.get((int(game), int(rally)))
        if winner is None:
            continue
        last_player = str(last["Player"])
        outcome_is_winner_shot = winner == last_player
        is_error_shot = not outcome_is_winner_shot
        outcome_type = f"{winner}_winning_shot" if outcome_is_winner_shot else f"{last_player}_error"
        reason = (
            f"{winner} won with {last['Stroke']}" if outcome_is_winner_shot else f"{winner} won due to {last_player}'s error on {last['Stroke']}"
        )

        start_frame = int(r_sorted["FrameNumber"].min())
        end_frame = int(r_sorted["FrameNumber"].max())
        stroke_count = int(len(r_sorted))

        first = r_sorted.iloc[0]

        row = _empty_row(ROWTYPE_RALLY_OUTCOME)
        # derive anchor shot variation
        anchor_hz, anchor_dir, anchor_land = _categorize_shot_variation(str(last["Stroke"]))

        row.update(
            {
                "GameNumber": int(game),
                "RallyNumber": int(rally),
                "Phase": str(last["Phase"]),
                "PhaseContext": "RallyEnd",
                "StartFrame": start_frame,
                "EndFrame": end_frame,
                "RallyDurationFrames": int(end_frame - start_frame + 1),
                "StrokeCount": stroke_count,
                "Winner": winner,
                "Loser": "P1" if winner == "P0" else "P0",
                "ScoreP0_Before": int(first["ScoreP0"]),
                "ScoreP1_Before": int(first["ScoreP1"]),
                "ScoreP0_After": int(last["ScoreP0"]),
                "ScoreP1_After": int(last["ScoreP1"]),
                "OutcomeType": outcome_type,
                "OutcomeReason": reason,
                # Anchor fields (last shot)
                "AnchorShotNumber": int(last["StrokeNumber"]),
                "AnchorPlayer": last_player,
                "AnchorStroke": str(last["Stroke"]),
                "AnchorFrameNumber": int(last["FrameNumber"]),
                "AnchorFrameId": pd.NA,
                "AnchorHittingZone": anchor_hz,
                "AnchorDirection": anchor_dir,
                "AnchorLandingPosition": anchor_land,
                "IsWinnerShot": bool(outcome_is_winner_shot),
                "IsErrorShot": bool(is_error_shot),
            }
        )
        rows.append(row)
    return rows


def _build_sr_pattern_rows(df: pd.DataFrame) -> List[Dict]:
    # key: (server, phase_at_service, serve_shot, receive_shot) -> list[(serve_frame, receive_frame)]
    agg: Dict[Tuple[str, str, str, str], List[Tuple[int, int]]] = defaultdict(list)
    grouped = df.groupby(["GameNumber", "RallyNumber"], sort=False)
    for _, r in grouped:
        r_sorted = r.sort_values(["StrokeNumber"])  # type: ignore[arg-type]
        if len(r_sorted) < 2:
            continue
        service = r_sorted.iloc[0]
        receive = r_sorted.iloc[1]
        server = str(service["Player"])
        phase_at_service = str(service["Phase"])
        serve_shot = str(service["Stroke"])
        receive_shot = str(receive["Stroke"])
        serve_frame = int(service["FrameNumber"])
        receive_frame = int(receive["FrameNumber"])
        agg[(server, phase_at_service, serve_shot, receive_shot)].append((serve_frame, receive_frame))

    rows: List[Dict] = []
    for (server, phase_at_service, serve_shot, receive_shot), frames in agg.items():
        row = _empty_row(ROWTYPE_SR_PATTERN_AGG)
        # up to 3 examples
        ex = frames[:3]
        ex += [(pd.NA, pd.NA)] * (3 - len(ex))
        row.update(
            {
                "Phase": phase_at_service,
                "PhaseContext": "Service",
                "Server": server,
                "PatternServeShot": serve_shot,
                "PatternReceiveShot": receive_shot,
                "PatternServeFrameExample1": ex[0][0],
                "PatternReceiveFrameExample1": ex[0][1],
                "PatternServeFrameExample2": ex[1][0],
                "PatternReceiveFrameExample2": ex[1][1],
                "PatternServeFrameExample3": ex[2][0],
                "PatternReceiveFrameExample3": ex[2][1],
                "Count": int(len(frames)),
            }
        )
        rows.append(row)
    # Sort by Phase, Server, Count desc
    rows.sort(key=lambda x: (str(x.get("Phase") or ""), str(x.get("Server") or ""), -int(x.get("Count") or 0)))
    return rows


def _is_serve(stroke: str) -> bool:
    stroke_l = stroke.lower()
    return any(k in stroke_l for k in ["serve_middle", "serve_corner", "flick_serve", "high_serve"]) or stroke_l == "high_serve"


def _is_target_shot(stroke: str) -> bool:
    stroke_l = stroke.lower()
    targets = [
        "forehand_lift",
        "backhand_lift",
        "forehand_pulldrop",
        "backhand_pulldrop",
        "forehand_clear",
        "backhand_clear",
        "forehand_defense",
        "backhand_defense",
    ]
    return any(t in stroke_l for t in targets)


def _build_three_shot_rows(df: pd.DataFrame) -> Tuple[List[Dict], List[Dict]]:
    seq_rows: List[Dict] = []
    grouped = df.groupby(["GameNumber", "RallyNumber"], sort=False)
    for (game, rally), r in grouped:
        r_sorted = r.sort_values(["StrokeNumber"]).reset_index(drop=True)  # type: ignore[arg-type]
        if len(r_sorted) < 2:
            continue
        first = r_sorted.iloc[0]
        if not _is_serve(str(first["Stroke"])):
            continue
        server = str(first["Player"])  # P0 or P1
        if server == "P0":
            target_idx = 2  # 3rd shot
            seq_len = 3
            seq_type = "P0_Serve_3_Shots"
        else:
            target_idx = 3  # 4th shot
            seq_len = 4
            seq_type = "P1_Serve_4_Shots"
        if target_idx >= len(r_sorted):
            continue
        target = r_sorted.iloc[target_idx]
        if not _is_target_shot(str(target["Stroke"])):
            continue
        seq_slice = r_sorted.iloc[:seq_len]
        shots = " -> ".join([str(s) for s in seq_slice["Stroke"].tolist()])
        frames_list = [int(x) for x in seq_slice["FrameNumber"].tolist()]
        frames_str = ", ".join([str(x) for x in frames_list])
        # derive anchor shot variation
        anchor_hz, anchor_dir, anchor_land = _categorize_shot_variation(str(target["Stroke"]))

        row = _empty_row(ROWTYPE_THREE_SHOT_SEQUENCE)
        row.update(
            {
                "GameNumber": int(game),
                "RallyNumber": int(rally),
                "Phase": str(target["Phase"]),
                "PhaseContext": "TargetShot",
                # Anchor = target shot
                "AnchorShotNumber": int(target["StrokeNumber"]),
                "AnchorPlayer": str(target["Player"]),
                "AnchorStroke": str(target["Stroke"]),
                "AnchorFrameNumber": int(target["FrameNumber"]),
                "AnchorFrameId": pd.NA,
                "AnchorHittingZone": anchor_hz,
                "AnchorDirection": anchor_dir,
                "AnchorLandingPosition": anchor_land,
                # Sequence fields
                "SequenceType": seq_type,
                "SequenceLength": int(seq_len),
                "SequenceShots": shots,
                "SequenceFrameNumbers": frames_str,
                "FirstFrame": int(frames_list[0]),
                "TargetFrame": int(frames_list[target_idx if target_idx < len(frames_list) else -1]),
            }
        )
        seq_rows.append(row)

    # Build summary rows
    summary_rows: List[Dict] = []
    if seq_rows:
        seq_df = pd.DataFrame(seq_rows)
        counts = (
            seq_df["Phase"].value_counts().sort_index()  # type: ignore[call-arg]
        )
        total = int(len(seq_df))
        for phase, count in counts.items():
            srow = _empty_row(ROWTYPE_THREE_SHOT_SUMMARY)
            srow.update(
                {
                    "Phase": str(phase),
                    "PhaseContext": "TargetShot",
                    "Count": int(count),
                }
            )
            summary_rows.append(srow)
        total_row = _empty_row(ROWTYPE_THREE_SHOT_SUMMARY)
        total_row.update({"Phase": "ALL", "PhaseContext": "TargetShot", "Count": total})
        summary_rows.append(total_row)

    return seq_rows, summary_rows


def _merge_anchor_effectiveness(
    base_rows: List[Dict], eff_map: Dict[Tuple[int, int, int], Dict]
) -> None:
    """In-place enrich rows that have an AnchorShotNumber using effectiveness mapping."""
    for row in base_rows:
        try:
            if pd.isna(row.get("AnchorShotNumber")):
                continue
            game = int(row.get("GameNumber")) if not pd.isna(row.get("GameNumber")) else None
            rally = int(row.get("RallyNumber")) if not pd.isna(row.get("RallyNumber")) else None
            shot = int(row.get("AnchorShotNumber")) if not pd.isna(row.get("AnchorShotNumber")) else None
            if game is None or rally is None or shot is None:
                continue
            eff = eff_map.get((game, rally, shot))
            if not eff:
                continue
            row.update(
                {
                    "AnchorFrameId": eff.get("Frame"),
                    "AnchorIsServe": eff.get("is_serve"),
                    "AnchorScore": eff.get("score"),
                    "AnchorBand": eff.get("band"),
                    "AnchorRallyPosition": eff.get("rally_position"),
                    "AnchorRallyId": eff.get("rally_id"),
                    "AnchorRallyWinner": eff.get("rally_winner"),
                    "AnchorRallyLoser": eff.get("rally_loser"),
                    "AnchorIsWinningShot": eff.get("is_winning_shot"),
                    "AnchorIsLosingShot": eff.get("is_losing_shot"),
                    "AnchorColor": eff.get("color"),
                    "AnchorEffectiveness": eff.get("effectiveness"),
                    "AnchorEffectivenessLabel": eff.get("effectiveness_label"),
                    "AnchorReason": eff.get("reason"),
                }
            )
        except Exception:
            continue


def _merge_rally_narratives(
    base_rows: List[Dict], narratives_map: Dict[Tuple[int, int], Dict]
) -> None:
    """In-place enrich rows with rally-level narratives using (GameNumber, RallyNumber)."""
    for row in base_rows:
        try:
            if pd.isna(row.get("GameNumber")) or pd.isna(row.get("RallyNumber")):
                continue
            game = int(row.get("GameNumber"))
            rally = int(row.get("RallyNumber"))
            payload = narratives_map.get((game, rally))
            if not payload:
                continue
            # Assign fields; keep types simple (strings/ints) and tolerate missing values
            row.update(
                {
                    "RallyNarrativePhase": payload.get("phase"),
                    "RallyNarrativeTotalShots": int(payload.get("total_shots")) if not pd.isna(payload.get("total_shots")) else pd.NA,
                    "P0_Narrative": payload.get("P0_narrative"),
                    "P1_Narrative": payload.get("P1_narrative"),
                    "P0_Phases": payload.get("P0_phases"),
                    "P1_Phases": payload.get("P1_phases"),
                    "P0_TurningPoints": payload.get("P0_turning_points"),
                    "P1_TurningPoints": payload.get("P1_turning_points"),
                }
            )
        except Exception:
            continue


def _build_shot_timeline_rows(eff_df: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    for _, s in eff_df.iterrows():
        try:
            hz, dr, land = _categorize_shot_variation(str(s.get("Stroke")))
            # Build explicit narration for final shots in the rally
            anchor_reason = s.get("reason")
            try:
                is_final = bool(s.get("is_winning_shot") or s.get("is_losing_shot"))
            except Exception:
                is_final = False
            if is_final:
                winner = str(s.get("rally_winner") or "")
                loser = str(s.get("rally_loser") or "")
                stroke = str(s.get("Stroke") or "")
                anchor_reason = f"Rally result: {winner} won; {loser} lost. Final shot: {stroke}"
            row = _empty_row(ROWTYPE_SHOT_TIMELINE)
            row.update(
                {
                    "GameNumber": int(s.get("GameNumber")),
                    "RallyNumber": int(s.get("RallyNumber")),
                    "Phase": str(s.get("Phase")),
                    "PhaseContext": "Shot",
                    # Use shot as anchor
                    "AnchorShotNumber": int(s.get("StrokeNumber")),
                    "AnchorPlayer": str(s.get("Player")),
                    "AnchorStroke": str(s.get("Stroke")),
                    "AnchorFrameNumber": int(s.get("FrameNumber")),
                    "AnchorFrameId": s.get("Frame"),
                    "AnchorHittingZone": hz,
                    "AnchorDirection": dr,
                    "AnchorLandingPosition": land,
                    "AnchorIsServe": s.get("is_serve"),
                    "AnchorScore": s.get("score"),
                    "AnchorBand": s.get("band"),
                    "AnchorRallyPosition": s.get("rally_position"),
                    "AnchorRallyId": s.get("rally_id"),
                    "AnchorRallyWinner": s.get("rally_winner"),
                    "AnchorRallyLoser": s.get("rally_loser"),
                    "AnchorIsWinningShot": s.get("is_winning_shot"),
                    "AnchorIsLosingShot": s.get("is_losing_shot"),
                    "AnchorColor": s.get("color"),
                    "AnchorEffectiveness": s.get("effectiveness"),
                    "AnchorEffectivenessLabel": s.get("effectiveness_label"),
                    "AnchorReason": anchor_reason,
                }
            )
            rows.append(row)
        except Exception:
            continue
    return rows


# Shot variation classification utilities
_HITTING_ZONES = {
    "front_left": {
        "backhand": ["dribble", "lift", "netkeep", "nettap", "push", "netkill"],
    },
    "front_right": {
        "forehand": ["dribble", "lift", "netkeep", "nettap", "push", "netkill"],
    },
    "back_right": {
        "forehand": ["smash", "halfsmash", "clear", "drop", "pulldrop", "drive"],
    },
    "back_left": {
        "backhand": ["smash", "halfsmash", "clear", "drop", "pulldrop", "drive"],
        "overhead": ["smash", "halfsmash", "clear", "drop"],
    },
    "middle_right": {
        "forehand": ["defense"],
    },
    "middle_left": {
        "backhand": ["defense"],
    },
    "middle_center": {
        "other": ["flat_game"],
    },
}

_LANDING_POSITIONS = {
    "dribble": "front court",
    "netkeep": "front court",
    "nettap": "mid court",
    "push": "back court",
    "lift": "back court",
    "defense": "front court",
    "drive": "back court",
    "smash": "mid court",
    "clear": "back court",
    "drop": "front court",
    "pulldrop": "front court",
    "halfsmash": "mid court",
    "netkill": "mid court",
    "flat_game": "mid court",
}


def _categorize_shot_variation(stroke: str) -> Tuple[str, str, str]:
    s = str(stroke)
    direction = "cross" if s.endswith("_cross") else "straight"
    base = s.replace("_cross", "")
    parts = base.split("_")
    shot_keyword = parts[-1] if len(parts) > 1 else base
    landing = _LANDING_POSITIONS.get(shot_keyword, "other")

    hitting_zone = "other"
    for zone, hands in _HITTING_ZONES.items():
        found = False
        for hand, shots in hands.items():
            for shot in shots:
                expected = f"{hand}_{shot}" if hand != "other" else shot
                if base == expected:
                    hitting_zone = zone
                    found = True
                    break
            if found:
                break
        if found:
            break
    return hitting_zone, direction, landing


def _build_shot_variation_agg_rows(df: pd.DataFrame, by_phase: bool = False) -> List[Dict]:
    rows: List[Dict] = []
    # Prepare fields
    work = df[["Player", "Stroke", "Phase"]].copy()
    work["ShotType"] = work["Stroke"].astype(str)
    work[["HittingZone", "Direction", "LandingPosition"]] = work["ShotType"].apply(
        lambda x: pd.Series(_categorize_shot_variation(x))
    )
    group_cols = ["Player", "HittingZone", "ShotType", "Direction", "LandingPosition"]
    if by_phase:
        group_cols = ["Phase"] + group_cols
    grouped = work.groupby(group_cols).size().reset_index(name="Count")

    for _, r in grouped.iterrows():
        row = _empty_row(ROWTYPE_SHOT_VARIATION_AGG if not by_phase else f"{ROWTYPE_SHOT_VARIATION_AGG}_by_phase")
        payload = {
            "Player": r["Player"],
            "HittingZone": r["HittingZone"],
            "ShotType": r["ShotType"],
            "Direction": r["Direction"],
            "LandingPosition": r["LandingPosition"],
            "Count": int(r["Count"]),
        }
        if by_phase:
            payload["Phase"] = r["Phase"]
            payload["PhaseContext"] = "Shot"
        row.update(payload)
        rows.append(row)
    return rows


def generate_consolidated(input_csv: str, output_csv: str, effectiveness_csv: Optional[str] = None, include_shot_timeline: bool = False, add_shot_variation: bool = False, shot_variation_by_phase: bool = False, rally_narratives_csv: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_csv(input_csv)

    required_cols = [
        "GameNumber",
        "RallyNumber",
        "StrokeNumber",
        "Player",
        "Stroke",
        "FrameNumber",
        "ScoreP0",
        "ScoreP1",
        "Phase",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in input CSV: {missing}")

    df = df.sort_values(["GameNumber", "RallyNumber", "StrokeNumber"])  # type: ignore[arg-type]

    # Precompute winners per rally
    winners = _infer_winners(df)

    # Build row families (base rows)
    outcome_rows = _build_rally_outcome_rows(df, winners)
    sr_rows = _build_sr_pattern_rows(df)
    three_rows, three_summary_rows = _build_three_shot_rows(df)

    all_rows = outcome_rows + sr_rows + three_rows + three_summary_rows

    # Optional: merge effectiveness context
    shot_timeline_rows: List[Dict] = []
    if effectiveness_csv:
        eff_df = pd.read_csv(effectiveness_csv)
        # Detect required columns from effectiveness file
        eff_required = [
            "GameNumber",
            "RallyNumber",
            "StrokeNumber",
            "FrameNumber",
            "Player",
            "Stroke",
            "Phase",
        ]
        missing_eff = [c for c in eff_required if c not in eff_df.columns]
        if missing_eff:
            raise ValueError(f"Missing required columns in effectiveness CSV: {missing_eff}")

        # Map for quick lookup by (game, rally, shot)
        eff_map: Dict[Tuple[int, int, int], Dict] = {}
        for _, s in eff_df.iterrows():
            try:
                key = (int(s.get("GameNumber")), int(s.get("RallyNumber")), int(s.get("StrokeNumber")))
                eff_map[key] = s.to_dict()
            except Exception:
                continue

        _merge_anchor_effectiveness(all_rows, eff_map)

        if include_shot_timeline:
            shot_timeline_rows = _build_shot_timeline_rows(eff_df)

    # Optional: merge rally narratives
    if rally_narratives_csv:
        rn_df = pd.read_csv(rally_narratives_csv)
        # Expected columns (from narratives files)
        rn_required = [
            "rally_id",
            "game_number",
            "phase",
            "total_shots",
            "P0_narrative",
            "P1_narrative",
            "P0_phases",
            "P1_phases",
            "P0_turning_points",
            "P1_turning_points",
        ]
        missing_rn = [c for c in rn_required if c not in rn_df.columns]
        if missing_rn:
            raise ValueError(f"Missing required columns in rally narratives CSV: {missing_rn}")

        # Derive rally_number from rally_id like "1_2"
        def _parse_rally_number(rid: str) -> int:
            try:
                parts = str(rid).split("_")
                return int(parts[1]) if len(parts) > 1 else pd.NA  # type: ignore[return-value]
            except Exception:
                return pd.NA  # type: ignore[return-value]

        rn_df = rn_df.copy()
        rn_df["rally_number"] = rn_df["rally_id"].apply(_parse_rally_number)
        rn_df = rn_df.dropna(subset=["rally_number"])  # keep rows with parsed rally number
        rn_df["rally_number"] = rn_df["rally_number"].astype(int)

        narratives_map: Dict[Tuple[int, int], Dict] = {}
        for _, r in rn_df.iterrows():
            try:
                key = (int(r.get("game_number")), int(r.get("rally_number")))
                narratives_map[key] = r.to_dict()
            except Exception:
                continue

        _merge_rally_narratives(all_rows, narratives_map)

    # Consolidate with optional shot timeline and narratives
    # Optional: shot variation aggregates
    if add_shot_variation:
        sv_rows = _build_shot_variation_agg_rows(df, by_phase=shot_variation_by_phase)
        all_rows.extend(sv_rows)

    all_rows = all_rows + shot_timeline_rows
    consolidated_df = pd.DataFrame(all_rows, columns=_fixed_columns())

    consolidated_df.to_csv(output_csv, index=False)
    return consolidated_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate consolidated badminton analysis CSV from detailed rally CSV.")
    parser.add_argument("--input", required=True, help="Path to *_detailed.csv input")
    parser.add_argument("--output", required=True, help="Path to output consolidated CSV")
    parser.add_argument("--effectiveness", required=False, help="Path to *_detailed_effectiveness.csv (optional)")
    parser.add_argument("--include-shot-timeline", action="store_true", help="Include full per-shot timeline rows from effectiveness CSV")
    parser.add_argument("--add-shot-variation", action="store_true", help="Add shot variation enrichment and aggregates")
    parser.add_argument("--shot-variation-by-phase", action="store_true", help="Break down shot variation aggregates by phase as well")
    parser.add_argument("--rally-narratives", required=False, help="Path to rally_narratives CSV to enrich consolidated output")
    args = parser.parse_args()

    consolidated_df = generate_consolidated(
        args.input,
        args.output,
        effectiveness_csv=args.effectiveness,
        include_shot_timeline=bool(args.include_shot_timeline),
        add_shot_variation=bool(args.add_shot_variation),
        shot_variation_by_phase=bool(args.shot_variation_by_phase),
        rally_narratives_csv=args.rally_narratives,
    )
    print(f"Wrote consolidated analysis to: {args.output}")
    # Quick counts
    print(consolidated_df["RowType"].value_counts())


if __name__ == "__main__":
    main()


