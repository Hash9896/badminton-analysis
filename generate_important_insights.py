import argparse
import os
from typing import Dict, List, Optional

import pandas as pd


OUTPUT_COLUMNS = [
    "InsightType",
    "Player",
    "GameNumber",
    "Phase",
    "Label",
    "Value1",
    "Value2",
    "Value3",
    "Frames",
    "Source",
    "SourceKeys",
]


def read_csv_safe(path: str) -> pd.DataFrame:
    try:
        if os.path.exists(path):
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def cap_frames(frames: List[str], cap: int = 20) -> str:
    if not frames:
        return ""
    if len(frames) <= cap:
        return "|".join(frames)
    return "|".join(frames[:cap])


def serve_patterns(sr_summary: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    if sr_summary.empty:
        return rows
    # Normalize
    for _, r in sr_summary.iterrows():
        try:
            server = str(r.get("Server"))
            recv = str(r.get("PatternReceiveShot"))
            serve = str(r.get("PatternServeShot"))
            count = int(r.get("Count")) if pd.notna(r.get("Count")) else 0
            rec_eff = float(r.get("ReceiveAvgEffectiveness")) if pd.notna(r.get("ReceiveAvgEffectiveness")) else None
            phase = r.get("Phase") if pd.notna(r.get("Phase")) else "ALL"
            if count < 3:
                continue
            label = f"Server {server}: {serve} → {recv} (n={count}, RecEff={rec_eff if rec_eff is not None else 'NA'}%)"
            frames = []
            for a, b in [
                ("PatternServeFrameExample1", "PatternReceiveFrameExample1"),
                ("PatternServeFrameExample2", "PatternReceiveFrameExample2"),
                ("PatternServeFrameExample3", "PatternReceiveFrameExample3"),
            ]:
                sf = r.get(a)
                rf = r.get(b)
                if pd.notna(sf) and pd.notna(rf):
                    frames.append(f"{int(sf)}-{int(rf)}")
            rows.append(
                {
                    "InsightType": "serve_pattern",
                    "Player": server,
                    "GameNumber": "ALL",
                    "Phase": phase,
                    "Label": label,
                    "Value1": count,
                    "Value2": rec_eff,
                    "Value3": None,
                    "Frames": cap_frames(frames),
                    "Source": "sr_summary",
                    "SourceKeys": f"serve={serve};receive={recv}",
                }
            )
        except Exception:
            continue
    return rows


def receive_hotspots(sr_top_receives: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    if sr_top_receives.empty:
        return rows
    for _, r in sr_top_receives.iterrows():
        try:
            server = str(r.get("Server"))
            recv = str(r.get("PatternReceiveShot"))
            count = int(r.get("Count")) if pd.notna(r.get("Count")) else 0
            rec_eff = float(r.get("ReceiveAvgEffectiveness")) if pd.notna(r.get("ReceiveAvgEffectiveness")) else None
            label = f"Top receive vs {server} serve: {recv} (n={count}, RecEff={rec_eff if rec_eff is not None else 'NA'}%)"
            rows.append(
                {
                    "InsightType": "receive_hotspot",
                    "Player": server,
                    "GameNumber": "ALL",
                    "Phase": "ALL",
                    "Label": label,
                    "Value1": count,
                    "Value2": rec_eff,
                    "Value3": None,
                    "Frames": "",
                    "Source": "sr_top_receives",
                    "SourceKeys": f"receive={recv}",
                }
            )
        except Exception:
            continue
    return rows


def phase_balances(winloss: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    if winloss.empty:
        return rows
    # Compute win/loss per phase per winner
    grouped = winloss.groupby(["Phase", "Winner"], dropna=False).size().reset_index(name="Wins")
    losses = winloss.groupby(["Phase", "Loser"], dropna=False).size().reset_index(name="Losses")
    merged = grouped.merge(losses, left_on=["Phase", "Winner"], right_on=["Phase", "Loser"], how="left")
    merged["Losses"] = merged["Losses"].fillna(0).astype(int)
    for _, r in merged.iterrows():
        try:
            phase = r.get("Phase") if pd.notna(r.get("Phase")) else "ALL"
            player = str(r.get("Winner"))
            wins = int(r.get("Wins"))
            los = int(r.get("Losses"))
            total = wins + los
            if total < 3:
                continue
            wr = round(100.0 * wins / total, 1) if total > 0 else None
            label = f"{player} in {phase}: {wins}W–{los}L ({wr}%)"
            # Select a few frames from this player's wins in this phase
            frames_df = winloss[(winloss["Phase"] == r.get("Phase")) & (winloss["Winner"] == player)]
            frames = []
            for _, rr in frames_df.head(4).iterrows():
                sf = rr.get("StartFrame")
                ef = rr.get("EndFrame")
                if pd.notna(sf) and pd.notna(ef):
                    frames.append(f"{int(sf)}-{int(ef)}")
            rows.append(
                {
                    "InsightType": "phase_balance",
                    "Player": player,
                    "GameNumber": "ALL",
                    "Phase": phase,
                    "Label": label,
                    "Value1": wins,
                    "Value2": los,
                    "Value3": wr,
                    "Frames": cap_frames(frames, 8),
                    "Source": "phase_winloss_narratives",
                    "SourceKeys": "",
                }
            )
        except Exception:
            continue
    # Turning points
    if set(["P0_TurningPoints", "P1_TurningPoints"]).issubset(winloss.columns):
        for _, r in winloss.iterrows():
            try:
                for pl, col in [("P0", "P0_TurningPoints"), ("P1", "P1_TurningPoints")]:
                    tp = r.get(col)
                    if isinstance(tp, str) and tp.strip():
                        phase = r.get("Phase") if pd.notna(r.get("Phase")) else "ALL"
                        label = f"Turning points ({pl}, {phase})"
                        frames = []
                        sf = r.get("StartFrame")
                        ef = r.get("EndFrame")
                        if pd.notna(sf) and pd.notna(ef):
                            frames = [f"{int(sf)}-{int(ef)}"]
                        rows.append(
                            {
                                "InsightType": "turning_point",
                                "Player": pl,
                                "GameNumber": "ALL",
                                "Phase": phase,
                                "Label": label,
                                "Value1": 1,
                                "Value2": None,
                                "Value3": None,
                                "Frames": cap_frames(frames, 8),
                                "Source": "phase_winloss_narratives",
                                "SourceKeys": "",
                            }
                        )
            except Exception:
                continue
    return rows


def final_shot_insights(final3: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    if final3.empty:
        return rows
    # Totals first
    totals = final3[(final3["AnchorStroke"] == "ALL")]
    for _, r in totals.iterrows():
        player = str(r.get("Player"))
        cat = str(r.get("Category"))
        occ = int(r.get("Occurrences")) if pd.notna(r.get("Occurrences")) else 0
        label = f"{player} {cat.replace('_', ' ')}: {occ}"
        rows.append(
            {
                "InsightType": "finisher_preference" if "winner" in cat else "error_hotspot",
                "Player": player,
                "GameNumber": "ALL",
                "Phase": "ALL",
                "Label": label,
                "Value1": occ,
                "Value2": None,
                "Value3": None,
                "Frames": "",
                "Source": "final_shot_top3",
                "SourceKeys": "",
            }
        )
    # Top 3s
    tops = final3[(final3["AnchorStroke"] != "ALL")]
    for _, r in tops.iterrows():
        try:
            player = str(r.get("Player"))
            cat = str(r.get("Category"))
            stroke = str(r.get("AnchorStroke"))
            occ = int(r.get("Occurrences")) if pd.notna(r.get("Occurrences")) else 0
            frames = str(r.get("ExampleFrames") or "").split("|") if pd.notna(r.get("ExampleFrames")) else []
            label = f"{player} {('finishes with' if cat=='winner' else 'errors on')} {stroke} (n={occ})"
            rows.append(
                {
                    "InsightType": "finisher_preference" if cat == "winner" else "error_hotspot",
                    "Player": player,
                    "GameNumber": "ALL",
                    "Phase": "ALL",
                    "Label": label,
                    "Value1": occ,
                    "Value2": None,
                    "Value3": None,
                    "Frames": cap_frames(frames),
                    "Source": "final_shot_top3",
                    "SourceKeys": f"stroke={stroke}",
                }
            )
        except Exception:
            continue
    return rows


def zone_insights(zones: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    if zones.empty:
        return rows
    for _, r in zones.iterrows():
        try:
            player = str(r.get("Player"))
            ztype = str(r.get("ZoneType"))
            zone = str(r.get("AnchorHittingZone"))
            land = r.get("AnchorLandingPosition")
            pts = int(r.get("Points")) if pd.notna(r.get("Points")) else 0
            shots = str(r.get("Shots")) if pd.notna(r.get("Shots")) else ""
            frames = str(r.get("AllFrames") or "").split("|") if pd.notna(r.get("AllFrames")) else []
            label = f"{player} {'hotspot' if ztype=='most_successful' else 'liability'}: {zone} (land={land}; shots={shots})"
            rows.append(
                {
                    "InsightType": "zone_hotspot" if ztype == "most_successful" else "zone_liability",
                    "Player": player,
                    "GameNumber": "ALL",
                    "Phase": "ALL",
                    "Label": label,
                    "Value1": pts,
                    "Value2": None,
                    "Value3": None,
                    "Frames": cap_frames(frames),
                    "Source": "zone_success_frames",
                    "SourceKeys": f"zone={zone}",
                }
            )
        except Exception:
            continue
    return rows


def three_shot_insights(t3: pd.DataFrame) -> List[Dict]:
    rows: List[Dict] = []
    if t3.empty:
        return rows
    for _, r in t3.iterrows():
        try:
            seq = str(r.get("SequenceShots"))
            count = int(r.get("Count")) if pd.notna(r.get("Count")) else 0
            if count < 3:
                continue
            frames = str(r.get("InstancesFrames") or "").split("|") if pd.notna(r.get("InstancesFrames")) else []
            label = f"3‑shot motif: {seq} (n={count})"
            rows.append(
                {
                    "InsightType": "three_shot_hotspot",
                    "Player": "ALL",
                    "GameNumber": "ALL",
                    "Phase": "ALL",
                    "Label": label,
                    "Value1": count,
                    "Value2": None,
                    "Value3": None,
                    "Frames": cap_frames(frames),
                    "Source": "three_shot_top",
                    "SourceKeys": f"seq={seq}",
                }
            )
        except Exception:
            continue
    return rows


def main():
    parser = argparse.ArgumentParser(description="Aggregate topic CSVs into important_insights.csv")
    parser.add_argument("--indir", required=True, help="Directory containing topic CSVs")
    parser.add_argument("--output", required=True, help="Path to write important_insights.csv")
    args = parser.parse_args()

    sr_summary = read_csv_safe(os.path.join(args.indir, "sr_summary.csv"))
    sr_top = read_csv_safe(os.path.join(args.indir, "sr_top_receives.csv"))
    winloss = read_csv_safe(os.path.join(args.indir, "phase_winloss_narratives.csv"))
    final3 = read_csv_safe(os.path.join(args.indir, "final_shot_top3.csv"))
    zones = read_csv_safe(os.path.join(args.indir, "zone_success_frames.csv"))
    t3 = read_csv_safe(os.path.join(args.indir, "three_shot_top.csv"))

    insights: List[Dict] = []
    insights += serve_patterns(sr_summary)
    insights += receive_hotspots(sr_top)
    insights += phase_balances(winloss)
    insights += final_shot_insights(final3)
    insights += zone_insights(zones)
    insights += three_shot_insights(t3)

    out_df = pd.DataFrame(insights, columns=OUTPUT_COLUMNS)
    out_df.to_csv(args.output, index=False)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
