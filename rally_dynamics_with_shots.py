import argparse
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd


def parse_bool_like(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in {"true", "1", "t", "yes", "y"}


def pick_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def derive_rally_id(df: pd.DataFrame) -> pd.DataFrame:
    if "rally_id" in df.columns:
        return df
    game_col = pick_col(df, "GameNumber", "game_number", "Game")
    rally_col = pick_col(df, "RallyNumber", "rally_number", "Rally")
    if game_col and rally_col:
        df = df.copy()
        df["rally_id"] = df[game_col].astype(str) + "_" + df[rally_col].astype(str)
        return df
    raise ValueError("Input effectiveness CSV is missing 'rally_id' and Game/Rally columns to derive it.")


def build_shot_timeline_map(eff_df: pd.DataFrame) -> pd.DataFrame:
    eff_df = derive_rally_id(eff_df)

    stroke_col = pick_col(eff_df, "Stroke")
    player_col = pick_col(eff_df, "Player")
    frame_col = pick_col(eff_df, "FrameNumber", "Frame")
    serve_col = pick_col(eff_df, "is_serve", "IsServe")
    order_col = pick_col(eff_df, "StrokeNumber", "rally_position")

    if stroke_col is None or player_col is None:
        raise ValueError("Effectiveness CSV must contain 'Stroke' and 'Player' columns.")

    # Stable sort: prefer StrokeNumber, then rally_position, else preserve original order
    if order_col is not None:
        eff_df_sorted = eff_df.sort_values(["rally_id", order_col], kind="stable")
    else:
        eff_df_sorted = eff_df.sort_values(["rally_id"], kind="stable")

    rows: List[Dict[str, object]] = []
    for rid, g in eff_df_sorted.groupby("rally_id", sort=False):
        g_local = g.copy()
        if order_col is not None:
            g_local = g_local.sort_values(order_col).reset_index(drop=True)
        else:
            g_local = g_local.reset_index(drop=True)

        # Build shot sequence
        strokes: List[str] = [str(x) for x in g_local[stroke_col].fillna("").tolist() if str(x) != ""]
        shot_sequence = " → ".join(strokes)

        # Determine server
        server: Optional[str] = None
        if serve_col is not None:
            serve_mask = g_local[serve_col].map(parse_bool_like)
            if serve_mask.any():
                first_serve_row = g_local[serve_mask].iloc[0]
                server = str(first_serve_row[player_col])
        if server is None:
            # Fallback: first row whose stroke mentions 'serve'
            serve_like = g_local[stroke_col].astype(str).str.lower().str.contains("serve", na=False)
            if serve_like.any():
                server = str(g_local.loc[serve_like].iloc[0][player_col])
        if server is None and not g_local.empty:
            server = str(g_local.iloc[0][player_col])

        # Optional: start/end frames if needed later
        start_frame = g_local.iloc[0][frame_col] if frame_col is not None else None
        end_frame = g_local.iloc[-1][frame_col] if frame_col is not None else None

        rows.append(
            {
                "rally_id": rid,
                "shot_sequence": shot_sequence,
                "server": server,
                "start_frame": start_frame,
                "end_frame": end_frame,
            }
        )

    return pd.DataFrame(rows)


def augment_narratives_with_shots(narratives_df: pd.DataFrame, shots_df: pd.DataFrame) -> pd.DataFrame:
    if "rally_id" not in narratives_df.columns:
        raise ValueError("Narratives CSV must contain 'rally_id'.")
    # Only keep the columns we add to avoid name clashes
    shots_keep = shots_df[["rally_id", "shot_sequence", "server"]].copy()
    merged = narratives_df.merge(shots_keep, on="rally_id", how="left")
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Augment rally_narratives_enriched.csv with shot sequence and server derived "
            "from *_detailed_effectiveness.csv"
        )
    )
    parser.add_argument("effectiveness_csv", type=str, help="Path to *_detailed_effectiveness.csv")
    parser.add_argument("narratives_csv", type=str, help="Path to rally_narratives_enriched.csv")
    parser.add_argument(
        "output_csv",
        type=str,
        nargs="?",
        default=None,
        help="Output CSV path (default: <narratives_dir>/rally_narratives_enriched_with_shots.csv)",
    )
    args = parser.parse_args()

    eff_csv = args.effectiveness_csv
    narratives_csv = args.narratives_csv
    out_csv = args.output_csv

    if out_csv is None:
        base_dir = os.path.dirname(os.path.abspath(narratives_csv))
        out_csv = os.path.join(base_dir, "rally_narratives_enriched_with_shots.csv")

    eff_df = pd.read_csv(eff_csv)
    narratives_df = pd.read_csv(narratives_csv)

    shots_df = build_shot_timeline_map(eff_df)
    augmented = augment_narratives_with_shots(narratives_df, shots_df)

    augmented.to_csv(out_csv, index=False)
    print(f"Wrote: {out_csv}")
    print(f"Rows: {len(augmented)} | Added columns: shot_sequence, server")


if __name__ == "__main__":
    main()


