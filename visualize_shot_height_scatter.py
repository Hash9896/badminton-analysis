#!/usr/bin/env python3
"""
Simple visualization script for shot height scatter plots.
Requires matplotlib: pip install matplotlib
"""

import argparse
import json
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("Error: matplotlib and numpy are required. Install with: pip install matplotlib numpy")
    exit(1)


def load_scatter_data(json_path: Path) -> dict:
    """Load scatter plot data from JSON."""
    with open(json_path, "r") as f:
        return json.load(f)


def create_scatter_plots(data: dict, output_dir: Path):
    """Create scatter plots for each shot category."""
    by_category = data.get("by_category", {})
    
    if not by_category:
        print("No data to plot.")
        return
    
    # Create figure with subplots
    n_categories = len(by_category)
    cols = 3
    rows = (n_categories + cols - 1) // cols
    
    fig, axes = plt.subplots(rows, cols, figsize=(15, 5 * rows))
    if rows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()
    
    for idx, (key, category_data) in enumerate(by_category.items()):
        ax = axes[idx]
        points = category_data.get("points", [])
        
        if not points:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(key)
            continue
        
        # Extract data
        flight_times = [p["flight_time"] for p in points if p.get("flight_time") is not None]
        effectiveness = [p["effectiveness"] for p in points if p.get("effectiveness") is not None]
        height_cats = [p.get("height_category", "unknown") for p in points]
        
        if not flight_times or not effectiveness:
            ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(key)
            continue
        
        # Color by height category
        colors = {"high": "red", "medium": "orange", "flat": "blue", "unknown": "gray"}
        point_colors = [colors.get(hc, "gray") for hc in height_cats]
        
        # Scatter plot
        scatter = ax.scatter(flight_times, effectiveness, c=point_colors, alpha=0.6, s=50)
        
        # Labels and title
        ax.set_xlabel("Flight Time (sec)")
        ax.set_ylabel("Effectiveness")
        ax.set_title(f"{key}\n(n={len(points)})")
        ax.grid(True, alpha=0.3)
        
        # Add legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=colors["high"], label="High"),
            Patch(facecolor=colors["medium"], label="Medium"),
            Patch(facecolor=colors["flat"], label="Flat"),
        ]
        ax.legend(handles=legend_elements, loc="upper right", fontsize=8)
    
    # Hide unused subplots
    for idx in range(len(by_category), len(axes)):
        axes[idx].axis("off")
    
    plt.tight_layout()
    
    # Save figure
    output_path = output_dir / "shot_height_scatter_plots.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved scatter plots to {output_path}")
    
    # Also create a combined plot
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    
    all_flight_times = []
    all_effectiveness = []
    all_colors = []
    all_labels = []
    
    for key, category_data in by_category.items():
        points = category_data.get("points", [])
        for p in points:
            if p.get("flight_time") is not None and p.get("effectiveness") is not None:
                all_flight_times.append(p["flight_time"])
                all_effectiveness.append(p["effectiveness"])
                hc = p.get("height_category", "unknown")
                all_colors.append(colors.get(hc, "gray"))
                all_labels.append(f"{key}_{hc}")
    
    if all_flight_times:
        ax2.scatter(all_flight_times, all_effectiveness, c=all_colors, alpha=0.5, s=30)
        ax2.set_xlabel("Flight Time (sec)")
        ax2.set_ylabel("Effectiveness")
        ax2.set_title("All Clears/Lifts: Effectiveness vs Flight Time")
        ax2.grid(True, alpha=0.3)
        
        legend_elements = [
            Patch(facecolor=colors["high"], label="High"),
            Patch(facecolor=colors["medium"], label="Medium"),
            Patch(facecolor=colors["flat"], label="Flat"),
        ]
        ax2.legend(handles=legend_elements, loc="upper right")
        
        output_path2 = output_dir / "shot_height_scatter_combined.png"
        plt.savefig(output_path2, dpi=150, bbox_inches="tight")
        print(f"Saved combined scatter plot to {output_path2}")
    
    plt.close("all")


def main():
    parser = argparse.ArgumentParser(description="Create scatter plots from shot height data")
    parser.add_argument("scatter_json", type=str, help="Path to *_shot_height_scatter.json")
    args = parser.parse_args()
    
    json_path = Path(args.scatter_json)
    if not json_path.exists():
        raise SystemExit(f"File not found: {json_path}")
    
    print(f"Loading data from {json_path}...")
    data = load_scatter_data(json_path)
    
    print("Creating scatter plots...")
    create_scatter_plots(data, json_path.parent)
    
    print("Done!")


if __name__ == "__main__":
    main()

