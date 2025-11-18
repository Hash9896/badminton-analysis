#!/usr/bin/env python3
"""
Add shot height category (high/medium/flat) to tempo_events.csv for clears and lifts.

Categorization based on:
- Flight time (time from shot to opponent's response) - indicates shot height
- Response time (player's response to incoming shot) - indicates shot setup time

Aggregates cross and straight shots (forehand_clear = forehand_clear_cross).
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


def normalize_shot_name(stroke: str) -> str:
    """Normalize shot name by removing _cross suffix and standardizing."""
    s = str(stroke).strip().lower()
    # Remove _cross suffix
    s = re.sub(r'_cross$', '', s)
    # Standardize variations
    s = re.sub(r'_straight$', '', s)
    return s


def is_clear_or_lift(stroke: str) -> bool:
    """Check if stroke is a clear or lift (normalized)."""
    s = normalize_shot_name(stroke)
    clears = ['forehand_clear', 'backhand_clear', 'overhead_clear']
    lifts = ['forehand_lift', 'backhand_lift']
    return s in clears or s in lifts


def get_shot_category(stroke: str) -> Optional[str]:
    """Get normalized shot category (forehand_clear, backhand_lift, etc.)."""
    if not is_clear_or_lift(stroke):
        return None
    s = normalize_shot_name(stroke)
    return s


def calculate_percentiles(values: List[float]) -> Dict[str, float]:
    """Calculate p25, p50 (median), p75 percentiles."""
    if not values:
        return {"p25": None, "p50": None, "p75": None}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    
    def percentile(q: float) -> float:
        rank = (q / 100.0) * (n - 1)
        low = int(rank)
        high = min(low + 1, n - 1)
        weight = rank - low
        return float(sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight)
    
    return {
        "p25": percentile(25.0),
        "p50": percentile(50.0),
        "p75": percentile(75.0),
    }


def categorize_height(
    flight_time: Optional[float],
    response_time: Optional[float],
    flight_p25: Optional[float],
    flight_p50: Optional[float],
    flight_p75: Optional[float],
    resp_p25: Optional[float],
    resp_p50: Optional[float],
    resp_p75: Optional[float],
) -> str:
    """
    Categorize shot as high/medium/flat based on flight_time and response_time.
    
    Logic:
    - High: Long flight time (shuttle in air longer) OR slow response (more setup time)
    - Flat: Short flight time (shuttle travels fast/low) AND fast response (quick reaction)
    - Medium: Everything else
    """
    if flight_time is None or response_time is None:
        return "unknown"
    
    # Determine flight_time category
    flight_cat = "medium"
    if flight_p75 is not None and flight_time >= flight_p75:
        flight_cat = "high"
    elif flight_p25 is not None and flight_time <= flight_p25:
        flight_cat = "low"
    
    # Determine response_time category
    resp_cat = "medium"
    if resp_p75 is not None and response_time >= resp_p75:
        resp_cat = "slow"
    elif resp_p25 is not None and response_time <= resp_p25:
        resp_cat = "fast"
    
    # Combine to get final category
    if flight_cat == "high" or (flight_cat == "medium" and resp_cat == "slow"):
        return "high"
    elif flight_cat == "low" and resp_cat == "fast":
        return "flat"
    else:
        return "medium"


def process_tempo_events(
    df: pd.DataFrame,
    fps: float,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """
    Process tempo events to add shot height category.
    
    Returns:
        - Augmented DataFrame with shot_height_category column
        - Summary DataFrame with statistics
        - JSON data for scatter plots
    """
    df = df.copy()
    
    # Initialize shot_height_category column
    df["shot_height_category"] = None
    df["shot_category"] = None
    df["flight_time_sec"] = None
    
    # Identify clear/lift shots
    clear_lift_mask = df["Stroke"].apply(is_clear_or_lift)
    clear_lift_indices = df[clear_lift_mask].index.tolist()
    
    # Group by rally_id for processing
    rally_groups = df.groupby("rally_id")
    
    # Process each rally
    flight_times: List[float] = []
    response_times: List[float] = []
    shot_categories_list: List[str] = []
    
    for rally_id, rally_df in rally_groups:
        rally_df = rally_df.sort_values("StrokeNumber")
        rally_indices = rally_df.index.tolist()
        
        for i, idx in enumerate(rally_indices):
            row = rally_df.loc[idx]
            stroke = str(row["Stroke"])
            
            if not is_clear_or_lift(stroke):
                continue
            
            player = str(row["Player"])
            stroke_num = int(row["StrokeNumber"])
            response_time = row.get("response_time_sec")
            
            # Get normalized shot category
            shot_cat = get_shot_category(stroke)
            df.at[idx, "shot_category"] = shot_cat
            
            # Find next opponent response
            flight_time = None
            opponent_response_stroke = None
            
            # Look ahead in rally for opponent's response
            for j in range(i + 1, len(rally_indices)):
                next_idx = rally_indices[j]
                next_row = rally_df.loc[next_idx]
                next_player = str(next_row["Player"])
                next_stroke_num = int(next_row["StrokeNumber"])
                
                if next_player != player and next_stroke_num > stroke_num:
                    # Found opponent's response
                    flight_time = next_row.get("response_time_sec")
                    opponent_response_stroke = str(next_row["Stroke"])
                    break
            
            if flight_time is not None and pd.notna(flight_time):
                try:
                    ft = float(flight_time)
                    if 0.1 <= ft <= 5.0:  # Reasonable range
                        df.at[idx, "flight_time_sec"] = ft
                        df.at[idx, "shot_height_category"] = "pending"  # Will categorize later
                        flight_times.append(ft)
                        if response_time is not None and pd.notna(response_time):
                            try:
                                rt = float(response_time)
                                if 0.1 <= rt <= 5.0:
                                    response_times.append(rt)
                                    shot_categories_list.append(shot_cat)
                            except (ValueError, TypeError):
                                pass
                except (ValueError, TypeError):
                    pass
            else:
                # No opponent response (rally ended with clear/lift)
                df.at[idx, "shot_height_category"] = "unknown"
    
    # Calculate percentiles for categorization
    if flight_times and response_times:
        flight_percentiles = calculate_percentiles(flight_times)
        resp_percentiles = calculate_percentiles(response_times)
        
        # Categorize each clear/lift shot
        for idx in clear_lift_indices:
            if df.at[idx, "shot_height_category"] == "pending":
                flight_time = df.at[idx, "flight_time_sec"]
                response_time = df.at[idx, "response_time_sec"]
                
                category = categorize_height(
                    flight_time=flight_time,
                    response_time=response_time,
                    flight_p25=flight_percentiles["p25"],
                    flight_p50=flight_percentiles["p50"],
                    flight_p75=flight_percentiles["p75"],
                    resp_p25=resp_percentiles["p25"],
                    resp_p50=resp_percentiles["p50"],
                    resp_p75=resp_percentiles["p75"],
                )
                df.at[idx, "shot_height_category"] = category
    else:
        # No valid data, mark all as unknown
        df.loc[df["shot_height_category"] == "pending", "shot_height_category"] = "unknown"
    
    # Build summary statistics
    summary_rows: List[Dict] = []
    scatter_data: Dict = {
        "fps": fps,
        "percentiles": {
            "flight_time": flight_percentiles if flight_times else {},
            "response_time": resp_percentiles if response_times else {},
        },
        "by_category": {},
        "by_player": {},
    }
    
    # Group by shot category and player
    for shot_cat in df["shot_category"].dropna().unique():
        for player in ["P0", "P1"]:
            mask = (df["shot_category"] == shot_cat) & (df["Player"] == player) & (df["shot_height_category"].notna())
            subset = df[mask]
            
            if len(subset) == 0:
                continue
            
            flight_vals = subset["flight_time_sec"].dropna().astype(float).tolist()
            resp_vals = subset["response_time_sec"].dropna().astype(float).tolist()
            eff_vals = subset["effectiveness"].dropna().astype(float).tolist()
            
            if not flight_vals:
                continue
            
            # Summary stats
            summary_rows.append({
                "player": player,
                "shot_category": shot_cat,
                "count": len(subset),
                "high_count": int((subset["shot_height_category"] == "high").sum()),
                "medium_count": int((subset["shot_height_category"] == "medium").sum()),
                "flat_count": int((subset["shot_height_category"] == "flat").sum()),
                "flight_time_min": float(min(flight_vals)),
                "flight_time_median": float(pd.Series(flight_vals).median()),
                "flight_time_mean": float(pd.Series(flight_vals).mean()),
                "flight_time_max": float(max(flight_vals)),
                "response_time_median": float(pd.Series(resp_vals).median()) if resp_vals else None,
                "effectiveness_median": float(pd.Series(eff_vals).median()) if eff_vals else None,
                "effectiveness_mean": float(pd.Series(eff_vals).mean()) if eff_vals else None,
            })
            
            # Scatter plot data
            key = f"{player}_{shot_cat}"
            scatter_data["by_category"][key] = {
                "player": player,
                "shot_category": shot_cat,
                "points": [
                    {
                        "flight_time": float(ft),
                        "response_time": float(rt) if pd.notna(rt) else None,
                        "effectiveness": float(ef) if pd.notna(ef) else None,
                        "height_category": str(hc),
                        "time_sec": float(ts),
                        "rally_id": str(rid),
                    }
                    for ft, rt, ef, hc, ts, rid in zip(
                        subset["flight_time_sec"],
                        subset["response_time_sec"],
                        subset["effectiveness"],
                        subset["shot_height_category"],
                        subset["time_sec"],
                        subset["rally_id"],
                    )
                    if pd.notna(ft)
                ],
            }
    
    summary_df = pd.DataFrame(summary_rows)
    
    return df, summary_df, scatter_data


def main():
    parser = argparse.ArgumentParser(
        description="Add shot height category to tempo_events.csv"
    )
    parser.add_argument("tempo_events_csv", type=str, help="Path to *_tempo_events.csv")
    parser.add_argument("--fps", type=float, default=30.0, help="Video FPS (default: 30)")
    parser.add_argument("--output-suffix", type=str, default="", help="Suffix for output files (default: overwrite input)")
    args = parser.parse_args()
    
    csv_path = Path(args.tempo_events_csv)
    if not csv_path.exists():
        raise SystemExit(f"File not found: {csv_path}")
    
    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    
    print("Processing shot height categories...")
    df_augmented, summary_df, scatter_data = process_tempo_events(df, args.fps)
    
    # Write augmented CSV (backup original if overwriting)
    if args.output_suffix:
        output_csv = csv_path.parent / f"{csv_path.stem}{args.output_suffix}.csv"
    else:
        # Create backup before overwriting
        backup_csv = csv_path.parent / f"{csv_path.stem}_backup.csv"
        if not backup_csv.exists():
            import shutil
            shutil.copy2(csv_path, backup_csv)
            print(f"Created backup: {backup_csv}")
        output_csv = csv_path  # Overwrite input
    
    print(f"Writing augmented CSV to {output_csv}...")
    df_augmented.to_csv(output_csv, index=False)
    
    # Write summary CSV
    summary_csv = csv_path.parent / f"{csv_path.stem}_shot_height_summary.csv"
    print(f"Writing summary to {summary_csv}...")
    summary_df.to_csv(summary_csv, index=False)
    
    # Write scatter plot JSON
    scatter_json = csv_path.parent / f"{csv_path.stem}_shot_height_scatter.json"
    print(f"Writing scatter plot data to {scatter_json}...")
    with open(scatter_json, "w") as f:
        json.dump(scatter_data, f, indent=2, allow_nan=False)
    
    # Print statistics
    total_clears_lifts = (df_augmented["shot_height_category"].notna()).sum()
    high_count = (df_augmented["shot_height_category"] == "high").sum()
    medium_count = (df_augmented["shot_height_category"] == "medium").sum()
    flat_count = (df_augmented["shot_height_category"] == "flat").sum()
    
    print(f"\nStatistics:")
    print(f"  Total clears/lifts processed: {total_clears_lifts}")
    print(f"  High: {high_count} ({100*high_count/total_clears_lifts:.1f}%)" if total_clears_lifts > 0 else "  High: 0")
    print(f"  Medium: {medium_count} ({100*medium_count/total_clears_lifts:.1f}%)" if total_clears_lifts > 0 else "  Medium: 0")
    print(f"  Flat: {flat_count} ({100*flat_count/total_clears_lifts:.1f}%)" if total_clears_lifts > 0 else "  Flat: 0")
    print(f"\nDone!")


if __name__ == "__main__":
    main()

