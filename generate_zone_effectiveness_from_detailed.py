import argparse
import os
from typing import Dict, List, Optional

import pandas as pd


def derive_zone(stroke: str) -> str:
    s = str(stroke)
    raw = s.lower()
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

    if hand == "backhand" and shot in ["dribble", "lift", "netkeep", "nettap", "push", "netkill"]:
        return "front_left"
    if hand == "forehand" and shot in ["dribble", "lift", "netkeep", "nettap", "push", "netkill"]:
        return "front_right"

    if hand == "forehand" and shot in ["smash", "halfsmash", "clear", "drop", "pulldrop", "drive"]:
        return "back_right"
    if (hand == "backhand" and shot in ["smash", "halfsmash", "clear", "drop", "pulldrop", "drive"]) or (
        hand == "overhead" and shot in ["smash", "halfsmash", "clear", "drop"]
    ):
        return "back_left"

    if hand == "forehand" and shot == "defense":
        return "middle_right"
    if hand == "backhand" and shot == "defense":
        return "middle_left"

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


def compute_zone_effectiveness(df: pd.DataFrame, min_uses_effective: int = 5, frames_cap: int = 20) -> pd.DataFrame:
    shots = df.copy()
    # Normalize and filter
    for c in ["GameNumber", "RallyNumber", "FrameNumber", "effectiveness"]:
        if c in shots.columns:
            shots[c] = pd.to_numeric(shots[c], errors="coerce")
    shots["Player"] = shots.get("Player", "").astype(str)
    shots["Stroke"] = shots.get("Stroke", "").astype(str)

    # Drop serves and rows without effectiveness
    shots = shots[~shots["Stroke"].str.contains("serve", case=False, na=False)]
    shots = shots[pd.notna(shots["effectiveness"])]

    # Derive zones and landing positions
    shots["AnchorHittingZone"] = shots["Stroke"].apply(derive_zone)
    shots["AnchorLandingPosition"] = shots["Stroke"].apply(derive_land)

    # Aggregate per player, per zone
    rows: List[Dict] = []
    for player, pg in shots.groupby("Player"):
        zagg = (
            pg.groupby("AnchorHittingZone")["effectiveness"].agg(["count", "mean"]).reset_index()
        )
        if zagg.empty:
            continue
        zagg.rename(columns={"count": "Uses", "mean": "AvgEffectiveness"}, inplace=True)
        zagg["AvgEffectiveness"] = zagg["AvgEffectiveness"].round(1)

        # Modal landing position per zone
        land_mode_map: Dict[str, Optional[str]] = {}
        for z, zg in pg.groupby("AnchorHittingZone"):
            land = zg["AnchorLandingPosition"].astype(str).replace({"nan": ""})
            land = land[land != ""]
            land_mode_map[str(z)] = (land.mode().iloc[0] if not land.empty else None)
        zagg["LandingMode"] = zagg["AnchorHittingZone"].astype(str).map(land_mode_map)

        cand = zagg[zagg["Uses"] >= min_uses_effective]
        if cand.empty:
            cand = zagg.copy()

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
                        for g, r, f in inst[["GameNumber", "RallyNumber", "FrameNumber"]].dropna().itertuples(index=False, name=None)
                    ]
                    rows.append(
                        {
                            "Player": str(player),
                            "ZoneType": typ,
                            "AnchorHittingZone": zone,
                            "AnchorLandingPosition": sel.iloc[0]["LandingMode"],
                            "Uses": uses,
                            "AvgEffectiveness": avg_eff,
                            "Shots": ", ".join(sorted(inst["Stroke"].astype(str).unique())),
                            "AllFrames": "|".join(frames[:frames_cap]),
                        }
                    )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate zone effectiveness from *_detailed_effectiveness.csv")
    parser.add_argument("--input", required=True, help="Path to *_detailed_effectiveness.csv")
    parser.add_argument("--output-dir", required=False, help="Directory to write outputs; defaults to input directory")
    args = parser.parse_args()

    in_path = args.input
    if not os.path.exists(in_path):
        raise FileNotFoundError(f"Input not found: {in_path}")

    df = pd.read_csv(in_path)
    out_df = compute_zone_effectiveness(df)

    out_dir = args.output_dir or os.path.dirname(in_path)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "zone_effectiveness_top_vs_bottom.csv")
    out_df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()


