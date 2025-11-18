
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import math
import re
from pathlib import Path

import pandas as pd


def autodetect_read_csv(path: Path) -> pd.DataFrame:
    """Read CSV or TSV by sniffing the delimiter."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    # crude sniff: prioritize tab if present with headers
    if "\t" in text.splitlines()[0]:
        return pd.read_csv(path, sep="\t")
    # fallback: comma
    return pd.read_csv(path)


def mmss_to_frame(mmss: str, fps: float) -> int:
    mmss = mmss.strip()
    if not mmss or ":" not in mmss:
        return None
    m, s = mmss.split(":")
    try:
        total = int(m) * 60 + int(s)
        return int(round(total * fps))
    except Exception:
        return None


def sec_to_mmss(x: float) -> str:
    x = max(0, int(round(x)))
    return f"{x//60:02d}:{x%60:02d}"


def build_rally_windows(detailed: pd.DataFrame, fps: float) -> pd.DataFrame:
    g = (detailed.groupby("rally_id")
         .agg(start_frame=("FrameNumber", "min"),
              end_frame=("FrameNumber", "max"),
              rally_winner=("rally_winner", "max"),
              rally_loser=("rally_loser", "max"))
         .reset_index())
    g["start_time_s"] = g["start_frame"] / fps
    g["end_time_s"] = g["end_frame"] / fps
    g["start_time"] = g["start_time_s"].apply(sec_to_mmss)
    g["end_time"] = g["end_time_s"].apply(sec_to_mmss)
    g["duration_s"] = (g["end_time_s"] - g["start_time_s"]).round(2)
    g["result_for_P0"] = g.apply(
        lambda r: "WIN" if r["rally_winner"] == "P0"
        else ("LOSS" if r["rally_loser"] == "P0" else ""),
        axis=1
    )
    return g


def add_anchor(anchors, **kwargs):
    # ensure consistent keys
    rec = {
        "rally_id": kwargs.get("rally_id"),
        "anchor_type": kwargs.get("anchor_type"),
        "player": kwargs.get("player", ""),
        "stroke": kwargs.get("stroke", ""),
        "frame": int(kwargs.get("frame")) if pd.notna(kwargs.get("frame")) else None,
        "phase_label": kwargs.get("phase_label", ""),
        "delta": kwargs.get("delta", ""),
        "tech_label": kwargs.get("tech_label", ""),
        "cue": kwargs.get("cue", "")
    }
    anchors.append(rec)


def extract_phase_starts_from_p0(p0_phases_text: str, rally_df: pd.DataFrame, anchors):
    """
    P0_phases example: "Net Battle(2-2) → Placement(4-6) → Reset/Baseline(8-8)"
    We take the *first shot index* for each phase and map to its frame.
    """
    if not isinstance(p0_phases_text, str) or not p0_phases_text.strip():
        return
    # allow spaces and slashes in label; capture (a-b)
    for m in re.finditer(r"([A-Za-z/ ]+)\((\d+)-(\d+)\)", p0_phases_text):
        label = m.group(1).strip()
        first_shot = int(m.group(2))
        row = rally_df[rally_df["StrokeNumber"] == first_shot]
        if len(row):
            add_anchor(
                anchors,
                rally_id=row.iloc[0]["rally_id"],
                anchor_type="phase_start",
                phase_label=label,
                frame=int(row.iloc[0]["FrameNumber"])
            )


def parse_turning_points(narrative_text: str):
    """
    Extract turning point shot numbers and (optionally) stroke labels from narrative text:
    e.g., "TURNING POINT Shot 6: backhand_defense_cross ..."
    Returns list of {"shot": int, "stroke_hint": str or ""}.
    """
    tps = []
    if not isinstance(narrative_text, str) or not narrative_text.strip():
        return tps
    for m in re.finditer(r"TURNING POINT Shot\s+(\d+):\s*([A-Za-z_]+)?", narrative_text):
        shot_num = int(m.group(1))
        stroke_hint = (m.group(2) or "").strip()
        tps.append({"shot": shot_num, "stroke_hint": stroke_hint})
    return tps


def main():
    ap = argparse.ArgumentParser(
        description="Build master_anchors.csv and rally_summary.csv from detailed, narratives, and technical error inputs."
    )
    ap.add_argument("--detailed", required=True, type=Path, help="Path to detailed.csv (CSV or TSV).")
    ap.add_argument("--narratives", required=True, type=Path, help="Path to rally_narratives_enriched.csv (CSV or TSV).")
    ap.add_argument("--technical_errors", required=True, type=Path, help="Path to technical_errors.json.")
    ap.add_argument("--fps", required=True, type=float, help="Video frames per second (e.g., 30).")
    ap.add_argument("--out_dir", required=True, type=Path, help="Directory to write outputs.")
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read inputs
    detailed = autodetect_read_csv(args.detailed)
    narratives = autodetect_read_csv(args.narratives)
    tech = json.loads(args.technical_errors.read_text(encoding="utf-8"))

    # Normalize column types
    # FrameNumber numeric
    detailed["FrameNumber"] = pd.to_numeric(detailed["FrameNumber"], errors="coerce")
    detailed["StrokeNumber"] = pd.to_numeric(detailed["StrokeNumber"], errors="coerce")
    # effectiveness to float (empty -> NaN)
    detailed["effectiveness"] = pd.to_numeric(detailed["effectiveness"], errors="coerce")
    # is_serve, is_winning_shot, is_losing_shot to bool
    for col in ["is_serve", "is_winning_shot", "is_losing_shot"]:
        if col in detailed.columns:
            detailed[col] = detailed[col].astype(str).str.upper().isin(["TRUE", "1", "T", "YES"])

    # Build rally summary
    rally_windows = build_rally_windows(detailed, args.fps)

    # Index narratives by rally_id for easy access
    narratives = narratives.copy()
    if "rally_id" not in narratives.columns:
        raise ValueError("rally_narratives_enriched is missing 'rally_id' column.")
    narratives_idx = narratives.set_index("rally_id")

    anchors = []

    # Per-rally processing
    for rid, g in detailed.groupby("rally_id"):
        g = g.sort_values("FrameNumber").reset_index(drop=True)

        # Serve anchors (kept; narration may later ignore unless pattern threshold is met)
        serve_rows = g[g["is_serve"] == True]
        for _, sr in serve_rows.iterrows():
            add_anchor(anchors,
                       rally_id=rid,
                       anchor_type="serve",
                       player=sr.get("Player", ""),
                       stroke=sr.get("Stroke", ""),
                       frame=sr["FrameNumber"])

        # Receive: only when P1 serves and the 2nd shot is P0
        if len(serve_rows):
            server = serve_rows.iloc[0].get("Player", "")
            if server == "P1":
                rec = g[(g["StrokeNumber"] == 2) & (g["Player"] == "P0")]
                if len(rec):
                    row = rec.iloc[0]
                    add_anchor(anchors,
                               rally_id=rid,
                               anchor_type="receive",
                               player=row.get("Player", ""),
                               stroke=row.get("Stroke", ""),
                               frame=row["FrameNumber"])

        # Momentum swings: abs delta >= 30 between consecutive effectiveness values
        eff = g["effectiveness"]
        for i in range(1, len(g)):
            curr = eff.iloc[i]
            prev = eff.iloc[i - 1]
            if pd.notna(curr) and pd.notna(prev):
                delta = float(curr) - float(prev)
                if abs(delta) >= 30.0:
                    row = g.iloc[i]
                    add_anchor(anchors,
                               rally_id=rid,
                               anchor_type="momentum_swing",
                               player=row.get("Player", ""),
                               stroke=row.get("Stroke", ""),
                               delta=round(delta, 1),
                               frame=row["FrameNumber"])

        # Turning points parsed from narratives (P0 and P1)
        if rid in narratives_idx.index:
            n_row = narratives_idx.loc[rid]
            for who_col, who in [("P0_narrative", "P0"), ("P1_narrative", "P1")]:
                text = str(n_row.get(who_col, ""))
                for tp in parse_turning_points(text):
                    shot = tp["shot"]
                    row = g[g["StrokeNumber"] == shot]
                    if len(row):
                        r0 = row.iloc[0]
                        add_anchor(anchors,
                                   rally_id=rid,
                                   anchor_type="turning_point",
                                   player=who,
                                   stroke=r0.get("Stroke", ""),
                                   frame=r0["FrameNumber"])

            # Phase starts from P0_phases
            extract_phase_starts_from_p0(str(n_row.get("P0_phases", "")), g, anchors)

        # Winning shot / error anchors
        win_rows = g[g["is_winning_shot"] == True]
        if len(win_rows):
            row = win_rows.iloc[-1]
            add_anchor(anchors,
                       rally_id=rid,
                       anchor_type="winning_shot",
                       player=row.get("Player", ""),
                       stroke=row.get("Stroke", ""),
                       frame=row["FrameNumber"])

        lose_rows = g[g["is_losing_shot"] == True]
        if len(lose_rows):
            row = lose_rows.iloc[-1]
            add_anchor(anchors,
                       rally_id=rid,
                       anchor_type="error",
                       player=row.get("Player", ""),
                       stroke=row.get("Stroke", ""),
                       frame=row["FrameNumber"])

    # Technical errors: map each MM:SS to frame and then to rally window
    # Build fast lookup for rally windows
    rw = rally_windows[["rally_id", "start_frame", "end_frame"]].copy()

    for issue in tech.get("data", []):
        label = issue.get("issue_text", "").strip()
        cue = issue.get("recommended_feedback", "").strip()
        for kf in issue.get("issue_keyframe", []):
            ts = kf.get("timestamp", "").strip()
            f = mmss_to_frame(ts, args.fps)
            if f is None:
                continue
            hit = rw[(rw["start_frame"] <= f) & (rw["end_frame"] >= f)]
            if len(hit):
                rid = hit.iloc[0]["rally_id"]
                add_anchor(anchors,
                           rally_id=rid,
                           anchor_type="tech_error",
                           tech_label=label,
                           cue=cue,
                           frame=f)

    # Build anchors dataframe and add time columns
    anchors_df = pd.DataFrame(anchors)
    # Drop any incomplete (no frame)
    anchors_df = anchors_df[pd.notna(anchors_df["frame"])].copy()
    anchors_df["frame"] = anchors_df["frame"].astype(int)
    anchors_df = anchors_df.sort_values(["rally_id", "frame"]).reset_index(drop=True)

    anchors_df["time_s"] = anchors_df["frame"] / args.fps
    anchors_df["time_mmss"] = anchors_df["time_s"].apply(sec_to_mmss)

    # Write outputs
    master_out = out_dir / "master_anchors.csv"
    summary_out = out_dir / "rally_summary.csv"

    anchors_df.to_csv(master_out, index=False)
    rally_windows[["rally_id", "start_time", "end_time", "duration_s",
                   "result_for_P0", "rally_winner", "rally_loser"]].to_csv(summary_out, index=False)

    print(f"✅ Wrote {master_out}")
    print(f"✅ Wrote {summary_out}")


if __name__ == "__main__":
    main()
