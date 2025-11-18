import argparse
from typing import Dict, List, Tuple, Optional

import pandas as pd


def read_consolidated(path: str) -> Dict[str, pd.DataFrame]:
    df = pd.read_csv(path)
    by_type: Dict[str, pd.DataFrame] = {k: g.copy() for k, g in df.groupby("RowType", dropna=False)}
    return by_type


def to_num(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def load_narratives(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path:
        return None
    try:
        rn = pd.read_csv(path)
        return rn
    except Exception:
        return None


def build_rally_maps(rally: pd.DataFrame) -> Tuple[Dict[Tuple[int, int], str], Dict[Tuple[int, int], Dict]]:
    winners: Dict[Tuple[int, int], str] = {}
    meta: Dict[Tuple[int, int], Dict] = {}
    for _, r in rally.iterrows():
        try:
            g = int(r.get("GameNumber"))
            rn = int(r.get("RallyNumber"))
            winners[(g, rn)] = str(r.get("Winner"))
            meta[(g, rn)] = {
                "Phase": str(r.get("Phase")),
                "StartFrame": int(r.get("StartFrame")) if pd.notna(r.get("StartFrame")) else None,
                "EndFrame": int(r.get("EndFrame")) if pd.notna(r.get("EndFrame")) else None,
            }
        except Exception:
            continue
    return winners, meta


def write_sr_summary(by_type: Dict[str, pd.DataFrame], shots: pd.DataFrame, out_dir: str) -> None:
    sr = by_type.get("sr_pattern_agg", pd.DataFrame())
    if sr.empty:
        pd.DataFrame().to_csv(f"{out_dir}/sr_summary.csv", index=False)
        pd.DataFrame().to_csv(f"{out_dir}/sr_top_receives.csv", index=False)
        return

    # Effectiveness for RECEIVE shots only: average effectiveness where AnchorShotNumber == 2
    recv_eff_map: Dict[str, float] = {}
    if not shots.empty and "AnchorEffectiveness" in shots.columns:
        try:
            recv_only = shots[(shots.get("AnchorShotNumber") == 2)].copy()
            eff = (
                recv_only.groupby("AnchorStroke")["AnchorEffectiveness"].mean().round(1).dropna()
                if not recv_only.empty
                else pd.Series(dtype=float)
            )
            recv_eff_map = eff.to_dict()
        except Exception:
            recv_eff_map = {}

    # Summarize SR pairs
    cols = [
        "Phase",
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
    ]
    keep = [c for c in cols if c in sr.columns]
    sr_out = sr[keep].copy()
    sr_out["ReceiveAvgEffectiveness"] = sr_out["PatternReceiveShot"].map(recv_eff_map)
    sr_out.to_csv(f"{out_dir}/sr_summary.csv", index=False)

    # Top 3 most common receives per server
    tmp = sr.groupby(["Server", "PatternReceiveShot"], dropna=False)["Count"].sum().reset_index()
    tmp = tmp.sort_values(["Server", "Count"], ascending=[True, False])
    top_rows: List[Dict] = []
    for server, grp in tmp.groupby("Server"):
        top = grp.head(3).copy()
        top["ReceiveAvgEffectiveness"] = top["PatternReceiveShot"].map(recv_eff_map)
        top_rows.append(top)
    if top_rows:
        pd.concat(top_rows, ignore_index=True).to_csv(f"{out_dir}/sr_top_receives.csv", index=False)
    else:
        pd.DataFrame().to_csv(f"{out_dir}/sr_top_receives.csv", index=False)


def write_phase_winloss(by_type: Dict[str, pd.DataFrame], narratives: Optional[pd.DataFrame], out_dir: str) -> None:
    rally = by_type.get("rally_outcome", pd.DataFrame())
    if rally.empty:
        pd.DataFrame().to_csv(f"{out_dir}/phase_winloss_narratives.csv", index=False)
        return

    to_num(rally, ["GameNumber", "RallyNumber", "StartFrame", "EndFrame"]) 
    merged = rally.copy()
    # Attach narratives if provided
    if narratives is not None and not narratives.empty:
        # Parse rally_id (e.g., 1_2) to game and rally
        tmp = narratives.copy()
        if "rally_id" in tmp.columns:
            tmp["_game"] = tmp["rally_id"].astype(str).str.split("_").str[0].astype(int)
            tmp["_rally"] = tmp["rally_id"].astype(str).str.split("_").str[1].astype(int)
            keep_cols = [
                "_game",
                "_rally",
                "P0_narrative",
                "P1_narrative",
                "P0_phases",
                "P1_phases",
                "P0_turning_points",
                "P1_turning_points",
            ]
            keep_cols = [c for c in keep_cols if c in tmp.columns]
            tmp = tmp[keep_cols]
            merged = merged.merge(
                tmp,
                left_on=["GameNumber", "RallyNumber"],
                right_on=["_game", "_rally"],
                how="left",
            )
            for c in ["_game", "_rally"]:
                if c in merged.columns:
                    merged.drop(columns=[c], inplace=True)

    # Build rows grouped as requested
    rows: List[Dict] = []
    for _, r in merged.iterrows():
        try:
            g = int(r.get("GameNumber"))
            rn = int(r.get("RallyNumber"))
            phase = str(r.get("Phase"))
            winner = str(r.get("Winner"))
            loser = "P0" if winner == "P1" else "P1"
            group = "P0_win_P1_loss" if winner == "P0" else "P1_win_P0_loss"
            # derive turning points if missing by scanning narrative strings for segments starting with "TURNING POINT"
            p0_tp = r.get("P0_turning_points")
            p1_tp = r.get("P1_turning_points")
            def _derive_tp(txt: Optional[str]) -> Optional[str]:
                if not isinstance(txt, str):
                    return None
                parts = [seg.strip() for seg in txt.split(" | ") if seg.strip().upper().startswith("TURNING POINT")]
                return " | ".join(parts) if parts else None
            if p0_tp is None:
                p0_tp = _derive_tp(r.get("P0_narrative"))
            if p1_tp is None:
                p1_tp = _derive_tp(r.get("P1_narrative"))

            rows.append(
                {
                    "Group": group,
                    "GameNumber": g,
                    "RallyNumber": rn,
                    "Phase": phase,
                    "Winner": winner,
                    "Loser": loser,
                    "StartFrame": int(r.get("StartFrame")) if pd.notna(r.get("StartFrame")) else None,
                    "EndFrame": int(r.get("EndFrame")) if pd.notna(r.get("EndFrame")) else None,
                    "P0_Narrative": r.get("P0_narrative"),
                    "P1_Narrative": r.get("P1_narrative"),
                    "P0_Phases": r.get("P0_phases"),
                    "P1_Phases": r.get("P1_phases"),
                    "P0_TurningPoints": p0_tp,
                    "P1_TurningPoints": p1_tp,
                }
            )
        except Exception:
            continue

    out_df = pd.DataFrame(rows)
    out_df = out_df.sort_values(["Group", "GameNumber", "RallyNumber"], kind="stable")
    out_df.to_csv(f"{out_dir}/phase_winloss_narratives.csv", index=False)


def write_top_winners_errors(by_type: Dict[str, pd.DataFrame], out_dir: str, top_k: int = 3) -> None:
    rally = by_type.get("rally_outcome", pd.DataFrame())
    if rally.empty:
        pd.DataFrame().to_csv(f"{out_dir}/final_shot_top3.csv", index=False)
        return

    to_num(rally, ["GameNumber", "RallyNumber", "AnchorFrameNumber"]) 
    rows: List[Dict] = []
    for player in ["P0", "P1"]:
        winners = rally[(rally["Winner"] == player) & (rally["OutcomeType"].astype(str).str.contains("winning_shot"))]
        errors = rally[(rally["Loser"] == player) & (rally["OutcomeType"].astype(str).str.endswith("_error"))]
        for cat, df_cat in [("winner", winners), ("error", errors)]:
            counts = df_cat["AnchorStroke"].value_counts().head(top_k)
            for stroke, occ in counts.items():
                # Collect example frames (all instances might be too many; provide up to 25)
                examples = (
                    df_cat[df_cat["AnchorStroke"] == stroke]
                    .sort_values(["GameNumber", "RallyNumber"])
                    .head(25)
                )
                frame_list = [
                    f"G{int(g)}-R{int(r)}-F{int(f)}"
                    for g, r, f in examples[["GameNumber", "RallyNumber", "AnchorFrameNumber"]].dropna().itertuples(index=False, name=None)
                ]
                rows.append(
                    {
                        "Player": player,
                        "Category": cat,
                        "AnchorStroke": str(stroke),
                        "Occurrences": int(occ),
                        "ExampleFrames": "|".join(frame_list),
                    }
                )

    out = pd.DataFrame(rows)
    # Append totals rows into the same CSV (AnchorStroke = ALL)
    totals_rows: List[Dict] = []
    for player in ["P0", "P1"]:
        total_winners = int(((rally["Winner"] == player) & (rally["OutcomeType"].astype(str).str.contains("winning_shot"))).sum())
        total_errors = int(((rally["Loser"] == player) & (rally["OutcomeType"].astype(str).str.endswith("_error"))).sum())
        totals_rows.append({"Player": player, "Category": "winners_total", "AnchorStroke": "ALL", "Occurrences": total_winners, "ExampleFrames": ""})
        totals_rows.append({"Player": player, "Category": "errors_total", "AnchorStroke": "ALL", "Occurrences": total_errors, "ExampleFrames": ""})
    out = pd.concat([out, pd.DataFrame(totals_rows)], ignore_index=True)
    out.to_csv(f"{out_dir}/final_shot_top3.csv", index=False)


def write_zone_success(by_type: Dict[str, pd.DataFrame], out_dir: str, min_uses_effective: int = 5, frames_cap: int = 20) -> None:
    rally = by_type.get("rally_outcome", pd.DataFrame())
    shots = by_type.get("shot_timeline", pd.DataFrame())
    if rally.empty or shots.empty:
        pd.DataFrame().to_csv(f"{out_dir}/zone_success_frames.csv", index=False)
        return

    to_num(rally, ["GameNumber", "RallyNumber"]) 
    to_num(shots, ["GameNumber", "RallyNumber", "AnchorFrameNumber"]) 

    # Use final shots from shot_timeline to get reliable zones/landing positions
    finals = shots[(shots.get("AnchorIsWinningShot") == True) | (shots.get("AnchorIsLosingShot") == True)].copy()
    finals["Player"] = finals["AnchorPlayer"].astype(str)
    finals["Outcome"] = finals.apply(lambda r: "win" if bool(r.get("AnchorIsWinningShot")) else ("loss" if bool(r.get("AnchorIsLosingShot")) else "mid"), axis=1)

    # Derive zones/landing per row if missing/blanks
    # Normalize blanks to NA first
    if "AnchorHittingZone" in finals.columns:
        finals["AnchorHittingZone"] = finals["AnchorHittingZone"].replace({"": pd.NA, "nan": pd.NA})
    else:
        finals["AnchorHittingZone"] = pd.NA
    if "AnchorLandingPosition" in finals.columns:
        finals["AnchorLandingPosition"] = finals["AnchorLandingPosition"].replace({"": pd.NA, "nan": pd.NA})
    else:
        finals["AnchorLandingPosition"] = pd.NA

    def derive_zone(stroke: str) -> str:
        s = str(stroke)
        raw = s.lower()
        # Extract hand prefix and shot name if present
        hand = None
        shot = raw
        if raw.startswith("forehand_"):
            hand = "forehand"
            shot = raw[len("forehand_"):]
        elif raw.startswith("backhand_"):
            hand = "backhand"
            shot = raw[len("backhand_"):]
        elif raw.startswith("overhead_"):
            hand = "overhead"
            shot = raw[len("overhead_"):]

        # Front corners
        if hand == "backhand" and shot in ["dribble", "lift", "netkeep", "nettap", "push", "netkill"]:
            return "front_left"
        if hand == "forehand" and shot in ["dribble", "lift", "netkeep", "nettap", "push", "netkill"]:
            return "front_right"

        # Back corners
        if hand == "forehand" and shot in ["smash", "halfsmash", "clear", "drop", "pulldrop", "drive"]:
            return "back_right"
        if (hand == "backhand" and shot in ["smash", "halfsmash", "clear", "drop", "pulldrop", "drive"]) or (
            hand == "overhead" and shot in ["smash", "halfsmash", "clear", "drop"]
        ):
            return "back_left"

        # Middle lanes
        if hand == "forehand" and shot == "defense":
            return "middle_right"
        if hand == "backhand" and shot == "defense":
            return "middle_left"

        # Flat game center
        if shot == "flat_game" or raw == "flat_game":
            return "middle_center"

        return "other"

    def derive_land(stroke: str) -> str:
        s = str(stroke).lower()
        if any(k in s for k in ["dribble", "netkeep", "nettap", "netkill", "drop", "pulldrop", "defense"]):
            return "front court"
        if any(k in s for k in ["smash", "halfsmash"]):
            return "mid court"
        if any(k in s for k in ["clear", "lift", "drive", "push"]):
            return "back court"
        if "flat_game" in s:
            return "mid court"
        return "other"

    mask_zone = finals["AnchorHittingZone"].isna() | (finals["AnchorHittingZone"].astype(str).str.strip() == "")
    finals.loc[mask_zone, "AnchorHittingZone"] = finals.loc[mask_zone, "AnchorStroke"].apply(derive_zone)
    mask_land = finals["AnchorLandingPosition"].isna() | (finals["AnchorLandingPosition"].astype(str).str.strip() == "")
    finals.loc[mask_land, "AnchorLandingPosition"] = finals.loc[mask_land, "AnchorStroke"].apply(derive_land)
    finals["AnchorHittingZone"].fillna("other", inplace=True)

    win_rows = finals[finals["Outcome"] == "win"].copy()
    lose_rows = finals[finals["Outcome"] == "loss"].copy()

    winners_g = (
        win_rows.groupby(["Player", "AnchorHittingZone"], dropna=False).size().reset_index(name="PointsWon")
    )
    losers_g = (
        lose_rows.groupby(["Player", "AnchorHittingZone"], dropna=False).size().reset_index(name="PointsLost")
    )

    # For each player, pick most successful and most unsuccessful zone; list ALL frames and shots, and most common landing position
    rows: List[Dict] = []
    for player in ["P0", "P1"]:
        best_zone = (
            winners_g[winners_g["Player"] == player]
            .sort_values("PointsWon", ascending=False)
            .head(1)
        )
        worst_zone = (
            losers_g[losers_g["Player"] == player]
            .sort_values("PointsLost", ascending=False)
            .head(1)
        )

        if not best_zone.empty:
            zone = best_zone.iloc[0]["AnchorHittingZone"]
            inst = win_rows[(win_rows["Player"] == player) & (win_rows["AnchorHittingZone"] == zone)]
            frames = [
                f"G{int(g)}-R{int(r)}-F{int(f)}"
                for g, r, f in inst[["GameNumber", "RallyNumber", "AnchorFrameNumber"]].dropna().itertuples(index=False, name=None)
            ]
            shots_list = ", ".join(sorted(inst["AnchorStroke"].astype(str).unique()))
            land = inst["AnchorLandingPosition"].astype(str).replace({"nan": ""})
            land = land[land != ""]
            land_mode = land.mode().iloc[0] if not land.empty else None
            rows.append(
                {
                    "Player": player,
                    "ZoneType": "most_successful",
                    "AnchorHittingZone": zone,
                    "AnchorLandingPosition": land_mode,
                    "Points": int(best_zone.iloc[0]["PointsWon"]),
                    "Shots": shots_list,
                    "AllFrames": "|".join(frames),
                }
            )

        if not worst_zone.empty:
            zone = worst_zone.iloc[0]["AnchorHittingZone"]
            inst = lose_rows[(lose_rows["Player"] == player) & (lose_rows["AnchorHittingZone"] == zone)]
            frames = [
                f"G{int(g)}-R{int(r)}-F{int(f)}"
                for g, r, f in inst[["GameNumber", "RallyNumber", "AnchorFrameNumber"]].dropna().itertuples(index=False, name=None)
            ]
            shots_list = ", ".join(sorted(inst["AnchorStroke"].astype(str).unique()))
            land = inst["AnchorLandingPosition"].astype(str).replace({"nan": ""})
            land = land[land != ""]
            land_mode = land.mode().iloc[0] if not land.empty else None
            rows.append(
                {
                    "Player": player,
                    "ZoneType": "most_unsuccessful",
                    "AnchorHittingZone": zone,
                    "AnchorLandingPosition": land_mode,
                    "Points": int(worst_zone.iloc[0]["PointsLost"]),
                    "Shots": shots_list,
                    "AllFrames": "|".join(frames),
                }
            )

    # Also compute most effective/ineffective zones over ALL shots
    all_shots = shots.copy()
    # normalize blanks
    if "AnchorHittingZone" in all_shots.columns:
        all_shots["AnchorHittingZone"] = all_shots["AnchorHittingZone"].replace({"": pd.NA, "nan": pd.NA})
    else:
        all_shots["AnchorHittingZone"] = pd.NA
    if "AnchorLandingPosition" in all_shots.columns:
        all_shots["AnchorLandingPosition"] = all_shots["AnchorLandingPosition"].replace({"": pd.NA, "nan": pd.NA})
    else:
        all_shots["AnchorLandingPosition"] = pd.NA

    # derive zone/landing per shot when missing
    mask_zone_all = all_shots["AnchorHittingZone"].isna() | (all_shots["AnchorHittingZone"].astype(str).str.strip() == "")
    all_shots.loc[mask_zone_all, "AnchorHittingZone"] = all_shots.loc[mask_zone_all, "AnchorStroke"].apply(derive_zone)
    mask_land_all = all_shots["AnchorLandingPosition"].isna() | (all_shots["AnchorLandingPosition"].astype(str).str.strip() == "")
    all_shots.loc[mask_land_all, "AnchorLandingPosition"] = all_shots.loc[mask_land_all, "AnchorStroke"].apply(derive_land)

    # per player, per zone effectiveness
    eff_rows: List[Dict] = []
    for player, pg in all_shots.groupby("AnchorPlayer"):
        zagg = (
            pg.groupby("AnchorHittingZone")["AnchorEffectiveness"].agg(["count", "mean"]).reset_index()
        )
        zagg.rename(columns={"count": "Uses", "mean": "AvgEffectiveness"}, inplace=True)
        zagg["AvgEffectiveness"] = zagg["AvgEffectiveness"].round(1)
        # attach landing mode for that zone
        land_mode_map: Dict[str, Optional[str]] = {}
        for z, zg in pg.groupby("AnchorHittingZone"):
            land = zg["AnchorLandingPosition"].astype(str).replace({"nan": ""})
            land = land[land != ""]
            land_mode_map[str(z)] = (land.mode().iloc[0] if not land.empty else None)
        zagg["LandingMode"] = zagg["AnchorHittingZone"].astype(str).map(land_mode_map)
        # pick most effective and ineffective with min uses
        cand = zagg[zagg["Uses"] >= min_uses_effective]
        if cand.empty:
            cand = zagg.copy()  # fallback
        if not cand.empty:
            best = cand.sort_values(["AvgEffectiveness", "Uses"], ascending=[False, False]).head(1)
            worst = cand.sort_values(["AvgEffectiveness", "Uses"], ascending=[True, False]).head(1)
            for typ, sel in [("most_effective", best), ("most_ineffective", worst)]:
                if not sel.empty:
                    zone = sel.iloc[0]["AnchorHittingZone"]
                    uses = int(sel.iloc[0]["Uses"])
                    avg_eff = float(sel.iloc[0]["AvgEffectiveness"]) if pd.notna(sel.iloc[0]["AvgEffectiveness"]) else None
                    inst = pg[pg["AnchorHittingZone"] == zone]
                    frames = [
                        f"G{int(g)}-R{int(r)}-F{int(f)}"
                        for g, r, f in inst[["GameNumber", "RallyNumber", "AnchorFrameNumber"]].dropna().itertuples(index=False, name=None)
                    ]
                    rows.append(
                        {
                            "Player": str(player),
                            "ZoneType": typ,
                            "AnchorHittingZone": zone,
                            "AnchorLandingPosition": sel.iloc[0]["LandingMode"],
                            "Points": None,
                            "Shots": ", ".join(sorted(inst["AnchorStroke"].astype(str).unique())),
                            "AllFrames": "|".join(frames[:frames_cap]),
                            "Uses": uses,
                            "AvgEffectiveness": avg_eff,
                        }
                    )

    out = pd.DataFrame(rows)
    out.to_csv(f"{out_dir}/zone_success_frames.csv", index=False)

    # Also write a focused CSV for frontend: top effective vs bottom ineffective zones per player
    try:
        eff_only = out[out["ZoneType"].isin(["most_effective", "most_ineffective"])].copy()
        cols = [
            "Player",
            "ZoneType",
            "AnchorHittingZone",
            "AnchorLandingPosition",
            "Uses",
            "AvgEffectiveness",
            "Shots",
            "AllFrames",
        ]
        # Ensure columns exist
        for c in cols:
            if c not in eff_only.columns:
                eff_only[c] = None
        eff_only = eff_only[cols]
        eff_only.to_csv(f"{out_dir}/zone_effectiveness_top_vs_bottom.csv", index=False)
    except Exception:
        # Non-fatal: skip if columns missing
        pass


def write_three_shot_top(by_type: Dict[str, pd.DataFrame], out_dir: str, top_k: int = 3) -> None:
    seq = by_type.get("three_shot_sequence", pd.DataFrame())
    if seq.empty:
        pd.DataFrame().to_csv(f"{out_dir}/three_shot_top.csv", index=False)
        return

    to_num(seq, ["FirstFrame", "TargetFrame"]) 
    counts = seq["SequenceShots"].value_counts().head(top_k)
    rows: List[Dict] = []
    for seq_shots, occ in counts.items():
        inst = seq[seq["SequenceShots"] == seq_shots]
        frames = [
            f"First{int(ff)}-Target{int(tf)}"
            for ff, tf in inst[["FirstFrame", "TargetFrame"]].dropna().itertuples(index=False, name=None)
        ]
        rows.append(
            {
                "SequenceShots": str(seq_shots),
                "Count": int(occ),
                "InstancesFrames": "|".join(frames),
            }
        )

    pd.DataFrame(rows).to_csv(f"{out_dir}/three_shot_top.csv", index=False)


def write_shot_effectiveness(by_type: Dict[str, pd.DataFrame], out_dir: str, top_k: int = 3) -> None:
    shots = by_type.get("shot_timeline", pd.DataFrame())
    if shots.empty:
        pd.DataFrame().to_csv(f"{out_dir}/shot_effectiveness_top.csv", index=False)
        return

    to_num(shots, ["GameNumber", "RallyNumber", "AnchorFrameNumber", "AnchorEffectiveness"]) 
    mid = shots[(shots.get("AnchorIsWinningShot") != True) & (shots.get("AnchorIsLosingShot") != True)].copy()
    if mid.empty:
        pd.DataFrame().to_csv(f"{out_dir}/shot_effectiveness_top.csv", index=False)
        return

    rows: List[Dict] = []
    for player, pg in mid.groupby("AnchorPlayer"):
        agg = (
            pg.groupby("AnchorStroke")["AnchorEffectiveness"].agg(["count", "mean"]).reset_index()
        )
        agg.rename(columns={"count": "Uses", "mean": "AvgEffectiveness"}, inplace=True)
        agg["AvgEffectiveness"] = agg["AvgEffectiveness"].round(1)
        # Top effective
        top_eff = agg.sort_values(["AvgEffectiveness", "Uses"], ascending=[False, False]).head(top_k)
        for _, r in top_eff.iterrows():
            inst = pg[pg["AnchorStroke"] == r["AnchorStroke"]]
            instances = [
                f"G{int(g)}-R{int(rl)}-F{int(f)}"
                for g, rl, f in inst[["GameNumber", "RallyNumber", "AnchorFrameNumber"]].dropna().itertuples(index=False, name=None)
            ]
            rows.append(
                {
                    "Player": str(player),
                    "Category": "most_effective",
                    "AnchorStroke": str(r["AnchorStroke"]),
                    "Uses": int(r["Uses"]),
                    "AvgEffectiveness": float(r["AvgEffectiveness"]),
                    "AllFrames": "|".join(instances),
                }
            )
        # Top ineffective
        top_ineff = agg.sort_values(["AvgEffectiveness", "Uses"], ascending=[True, False]).head(top_k)
        for _, r in top_ineff.iterrows():
            inst = pg[pg["AnchorStroke"] == r["AnchorStroke"]]
            instances = [
                f"G{int(g)}-R{int(rl)}-F{int(f)}"
                for g, rl, f in inst[["GameNumber", "RallyNumber", "AnchorFrameNumber"]].dropna().itertuples(index=False, name=None)
            ]
            rows.append(
                {
                    "Player": str(player),
                    "Category": "most_ineffective",
                    "AnchorStroke": str(r["AnchorStroke"]),
                    "Uses": int(r["Uses"]),
                    "AvgEffectiveness": float(r["AvgEffectiveness"]),
                    "AllFrames": "|".join(instances),
                }
            )

    pd.DataFrame(rows).to_csv(f"{out_dir}/shot_effectiveness_top.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate topic CSVs from consolidated_with_eff.csv")
    parser.add_argument("--input", required=True, help="Path to consolidated_with_eff.csv")
    parser.add_argument("--outdir", required=True, help="Output directory for topic CSVs")
    parser.add_argument(
        "--rally-narratives",
        required=False,
        help="Optional path to rally_narratives CSV for narratives attachment",
    )
    args = parser.parse_args()

    by_type = read_consolidated(args.input)
    shots = by_type.get("shot_timeline", pd.DataFrame())
    narratives = load_narratives(args.rally_narratives)

    # 1) SR summary with receive effectiveness only
    write_sr_summary(by_type, shots, args.outdir)

    # 2) Phase win/loss narratives grouped
    write_phase_winloss(by_type, narratives, args.outdir)

    # 3) Top 3 winners/errors per player
    write_top_winners_errors(by_type, args.outdir)

    # 4) Zones with all frames for most successful/unsuccessful
    write_zone_success(by_type, args.outdir)

    # 5) Most common three-shot sequence
    write_three_shot_top(by_type, args.outdir)

    # 6) Top/Bottom shots with all instance frames
    write_shot_effectiveness(by_type, args.outdir)

    print(f"Wrote topic CSVs to {args.outdir}")


if __name__ == "__main__":
    main()


