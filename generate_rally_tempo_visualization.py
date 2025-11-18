#!/usr/bin/env python3
"""
Generate rally tempo visualization JSON from tempo_analysis_new.csv

This script processes the tempo analysis CSV and creates a JSON structure
optimized for visualizing tempo states of P0 and P1 throughout each rally.
"""

import pandas as pd
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


def process_tempo_csv(csv_path: str) -> Dict[str, Any]:
    """
    Process tempo_analysis_new.csv and generate rally tempo visualization data.
    
    Returns a dictionary with rally-by-rally tempo data for visualization.
    """
    df = pd.read_csv(csv_path)
    
    # Filter out serves (they don't have response_time_sec)
    df = df[df['is_serve'] != True].copy()
    
    # Convert numeric columns, handling missing values
    numeric_cols = ['time_sec', 'response_time_sec', 'StrokeNumber', 'FrameNumber', 
                    'effectiveness', 'RallyNumber', 'GameNumber']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Group by rally
    rallies = {}
    
    for rally_id, rally_df in df.groupby('rally_id'):
        if rally_df.empty:
            continue
        
        # Sort by stroke number
        rally_df = rally_df.sort_values('StrokeNumber').reset_index(drop=True)
        
        # Get rally metadata
        game_num = int(rally_df.iloc[0]['GameNumber']) if pd.notna(rally_df.iloc[0]['GameNumber']) else 0
        rally_num = int(rally_df.iloc[0]['RallyNumber']) if pd.notna(rally_df.iloc[0]['RallyNumber']) else 0
        rally_winner = str(rally_df.iloc[0].get('rally_winner', '')).strip() if pd.notna(rally_df.iloc[0].get('rally_winner', '')) else ''
        
        # Extract shots for P0 and P1
        p0_shots = []
        p1_shots = []
        
        for _, row in rally_df.iterrows():
            player = str(row.get('Player', '')).strip()
            if player not in ['P0', 'P1']:
                continue
            
            # Get tempo data
            time_sec = float(row.get('time_sec', 0)) if pd.notna(row.get('time_sec')) else 0
            response_time = float(row.get('response_time_sec', 0)) if pd.notna(row.get('response_time_sec')) else None
            stroke_num = int(row.get('StrokeNumber', 0)) if pd.notna(row.get('StrokeNumber')) else 0
            frame_num = int(row.get('FrameNumber', 0)) if pd.notna(row.get('FrameNumber')) else 0
            
            # Tempo control states
            tempo_control = str(row.get('tempo_control', '')).strip() if pd.notna(row.get('tempo_control')) else 'neutral'
            control_type = str(row.get('control_type', '')).strip() if pd.notna(row.get('control_type')) else 'balanced'
            classification = str(row.get('classification', '')).strip() if pd.notna(row.get('classification')) else 'normal'
            
            # Shot info
            stroke = str(row.get('Stroke', '')).strip()
            effectiveness = float(row.get('effectiveness', 0)) if pd.notna(row.get('effectiveness')) else None
            
            shot_data = {
                'stroke_number': stroke_num,
                'time_sec': time_sec,
                'frame_number': frame_num,
                'response_time_sec': response_time,
                'stroke': stroke,
                'effectiveness': effectiveness,
                'tempo_control': tempo_control,
                'control_type': control_type,
                'classification': classification,
            }
            
            if player == 'P0':
                p0_shots.append(shot_data)
            else:
                p1_shots.append(shot_data)
        
        # Only include rallies with at least 2 shots (one from each player ideally)
        if len(p0_shots) == 0 and len(p1_shots) == 0:
            continue
        
        # Calculate rally start time (first shot time)
        all_times = [s['time_sec'] for s in p0_shots + p1_shots if s['time_sec'] > 0]
        rally_start_time = min(all_times) if all_times else 0
        
        # Normalize times relative to rally start
        for shot in p0_shots + p1_shots:
            if rally_start_time > 0:
                shot['time_in_rally'] = shot['time_sec'] - rally_start_time
            else:
                shot['time_in_rally'] = shot['time_sec']
        
        rallies[rally_id] = {
            'rally_id': rally_id,
            'game_number': game_num,
            'rally_number': rally_num,
            'rally_winner': rally_winner,
            'rally_start_time': rally_start_time,
            'p0_shots': p0_shots,
            'p1_shots': p1_shots,
            'total_shots': len(p0_shots) + len(p1_shots),
        }
    
    # Sort rallies by game and rally number
    sorted_rallies = sorted(rallies.values(), key=lambda r: (r['game_number'], r['rally_number']))
    
    return {
        'rallies': sorted_rallies,
        'total_rallies': len(sorted_rallies),
        'metadata': {
            'source_file': str(csv_path),
            'generated_by': 'generate_rally_tempo_visualization.py'
        }
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_rally_tempo_visualization.py <tempo_analysis_new.csv> [output.json]")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not Path(csv_path).exists():
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)
    
    print(f"Processing {csv_path}...")
    data = process_tempo_csv(csv_path)
    
    if output_path:
        output_file = Path(output_path)
    else:
        # Auto-generate output filename
        csv_file = Path(csv_path)
        output_file = csv_file.parent / f"{csv_file.stem}_rally_tempo_viz.json"
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Generated {output_file}")
    print(f"Total rallies: {data['total_rallies']}")


if __name__ == '__main__':
    main()

