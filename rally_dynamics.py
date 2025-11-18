import pandas as pd
import numpy as np
import json
import sys
import os
import subprocess
from typing import Dict, List, Tuple, Optional

def load_shot_categories(json_path: str) -> Dict[str, List[str]]:
    """Load shot categories from response_classification.json"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    return data.get('shot_categories', {})

def pick_col(row_or_df, *candidates: str, default=None):
    """Return the first available column value (row) or column name (df) among candidates."""
    if isinstance(row_or_df, pd.Series):
        for c in candidates:
            if c in row_or_df.index:
                return row_or_df.get(c)
        return default
    # DataFrame path: return first existing column name
    for c in candidates:
        if c in row_or_df.columns:
            return c
    return None

def parse_bool_like(val) -> bool:
    if isinstance(val, bool):
        return val
    try:
        s = str(val).strip().lower()
        return s in ("true", "1", "yes", "y", "t")
    except Exception:
        return False

def classify_shot_category(shot: str, shot_categories: Dict[str, List[str]]) -> str:
    """
    Classify a shot into its category
    Strips _cross suffix for classification
    """
    shot_normalized = shot.lower().replace('_cross', '')
    
    for category, shots in shot_categories.items():
        normalized_shots = [s.lower().replace('_cross', '') for s in shots]
        if shot_normalized in normalized_shots:
            return category
    
    return 'unknown'

def detect_phases(player_shots: pd.DataFrame, shot_categories: Dict[str, List[str]], min_phase_length: int = 2) -> List[Dict]:
    """
    Detect phases for a player based on shot category changes with minimum phase length
    Each phase = continuous sequence of shots in same category (minimum length enforced)
    """
    if len(player_shots) == 0:
        return []
    
    # First pass: detect raw phases
    raw_phases = []
    # Treat serves as their own category to avoid merging
    def to_category(shot_type: str) -> str:
        s = str(shot_type or '').lower()
        if 'serve' in s:
            return 'serve_shots'
        return classify_shot_category(shot_type, shot_categories)

    current_phase = {
        'start_position': player_shots.iloc[0]['rally_position'],
        'end_position': player_shots.iloc[0]['rally_position'],
        'category': to_category(player_shots.iloc[0]['Stroke']),
        'shots': [player_shots.iloc[0]],
        'effectiveness_values': []
    }
    
    for i in range(len(player_shots)):
        shot = player_shots.iloc[i]
        category = to_category(shot['Stroke'])
        
        # Add effectiveness if available
        eff = shot.get('effectiveness')
        if pd.notna(eff):
            current_phase['effectiveness_values'].append(float(eff))
        
        if i == 0:
            continue
        
        # Phase boundary = category change
        if category != current_phase['category']:
            # Save current phase
            current_phase['end_position'] = player_shots.iloc[i-1]['rally_position']
            raw_phases.append(current_phase)
            
            # Start new phase
            current_phase = {
                'start_position': shot['rally_position'],
                'end_position': shot['rally_position'],
                'category': category,
                'shots': [shot],
                'effectiveness_values': []
            }
            if pd.notna(eff):
                current_phase['effectiveness_values'].append(float(eff))
        else:
            # Continue current phase
            current_phase['end_position'] = shot['rally_position']
            current_phase['shots'].append(shot)
    
    # Add final phase
    raw_phases.append(current_phase)
    
    # Second pass: merge short phases with adjacent phases
    if len(raw_phases) <= 1:
        return raw_phases
    
    merged_phases = []
    i = 0
    
    while i < len(raw_phases):
        current_phase = raw_phases[i].copy()
        
        # If phase is too short, try to merge with next phase
        while (len(current_phase['shots']) < min_phase_length and 
               i + 1 < len(raw_phases) and
               # Don't merge serve phases with other phases
               current_phase['category'] != 'serve_shots'):
            
            next_phase = raw_phases[i + 1]
            
            # Merge phases: extend current phase to include next phase
            current_phase['end_position'] = next_phase['end_position']
            current_phase['shots'].extend(next_phase['shots'])
            current_phase['effectiveness_values'].extend(next_phase['effectiveness_values'])
            
            # Use the category of the longer phase, or current if equal
            if len(next_phase['shots']) > len(current_phase['shots']) - len(next_phase['shots']):
                current_phase['category'] = next_phase['category']
            
            i += 1
        
        merged_phases.append(current_phase)
        i += 1
    
    return merged_phases

def get_phase_label(category: str) -> str:
    """Convert category to readable phase label"""
    labels = {
        'attacking_shots': 'Attacking',
        'defensive_shots': 'Defensive',
        'net_shots': 'Net Battle',
        'net_kill': 'Net Kill',
        'placement_shots': 'Placement',
        'reset_shots': 'Reset/Baseline',
        'pressure_shots': 'Pressure',
        'serve_shots': 'Serve',
        'unknown': 'Mixed'
    }
    return labels.get(category, category)

def find_turning_points(player_shots: pd.DataFrame, threshold: float = 40.0) -> List[Dict]:
    """
    Find shots where effectiveness swung significantly
    """
    turning_points = []
    
    for i in range(1, len(player_shots)):
        curr = player_shots.iloc[i]
        prev = player_shots.iloc[i-1]
        
        curr_eff = curr.get('effectiveness')
        prev_eff = prev.get('effectiveness')
        
        if pd.notna(curr_eff) and pd.notna(prev_eff):
            swing = float(curr_eff) - float(prev_eff)
            
            if abs(swing) >= threshold:
                turning_points.append({
                    'shot_position': int(curr['rally_position']),
                    'shot_type': curr['Stroke'],
                    'effectiveness': float(curr_eff),
                    'swing': swing,
                    'direction': 'positive' if swing > 0 else 'negative'
                })
    
    return turning_points

def generate_narrative(
    player: str,
    phases: List[Dict],
    turning_points: List[Dict],
    outcome: str,
    rally_winner: str
) -> str:
    """
    Generate concise narrative for player's rally experience
    """
    narrative_parts = []
    
    # Phase descriptions
    for i, phase in enumerate(phases):
        label = get_phase_label(phase['category'])
        start = phase['start_position']
        end = phase['end_position']
        
        # Calculate average effectiveness
        if len(phase['effectiveness_values']) > 0:
            avg_eff = np.mean(phase['effectiveness_values'])
            eff_str = f"avg {avg_eff:.0f}%"
        else:
            eff_str = "no score"
        
        # Shot range
        if start == end:
            shot_range = f"Shot {start}"
        else:
            shot_range = f"Shots {start}-{end}"
        
        phase_desc = f"Phase {i+1} ({shot_range}): {label} - {eff_str}"
        
        # Add context based on effectiveness
        if len(phase['effectiveness_values']) > 0:
            if avg_eff > 70:
                phase_desc += " → Dominated"
            elif avg_eff > 55:
                phase_desc += " → Controlled"
            elif avg_eff > 40:
                phase_desc += " → Contested"
            else:
                phase_desc += " → Struggled"
        
        narrative_parts.append(phase_desc)
    
    # Add turning points
    for tp in turning_points:
        tp_desc = f"TURNING POINT Shot {tp['shot_position']}: {tp['shot_type']} ({tp['effectiveness']:.0f}% eff, {tp['swing']:+.0f} swing)"
        narrative_parts.append(tp_desc)
    
    # Outcome analysis
    did_win = (player == rally_winner)
    outcome_str = "Result: WIN" if did_win else "Result: LOSS"
    
    # Determine why
    if len(phases) > 0:
        overall_eff = []
        for p in phases:
            overall_eff.extend(p['effectiveness_values'])
        
        if len(overall_eff) > 0:
            avg_overall = np.mean(overall_eff)
            
            if did_win:
                if avg_overall > 70:
                    outcome_str += " - Dominated throughout"
                elif len(turning_points) > 0:
                    # Find most impactful positive turning point
                    best_tp = max(turning_points, key=lambda x: x['swing'])
                    outcome_str += f" - Key moment: Shot {best_tp['shot_position']}"
                elif len(phases) > 1:
                    # Check if finished strong
                    last_phase_eff = np.mean(phases[-1]['effectiveness_values']) if len(phases[-1]['effectiveness_values']) > 0 else 50
                    if last_phase_eff > 60:
                        outcome_str += f" - Strong finish with {get_phase_label(phases[-1]['category'])}"
                    else:
                        outcome_str += " - Capitalized on opportunities"
                else:
                    outcome_str += " - Executed well"
            else:
                if avg_overall < 35:
                    outcome_str += " - Outplayed throughout"
                elif len(turning_points) > 0:
                    # Find most impactful negative turning point
                    worst_tp = min(turning_points, key=lambda x: x['swing'])
                    outcome_str += f" - Lost momentum at Shot {worst_tp['shot_position']}"
                elif len(phases) > 1:
                    last_phase_eff = np.mean(phases[-1]['effectiveness_values']) if len(phases[-1]['effectiveness_values']) > 0 else 50
                    if last_phase_eff < 40:
                        outcome_str += f" - Failed in {get_phase_label(phases[-1]['category'])}"
                    else:
                        outcome_str += " - Couldn't convert opportunities"
                else:
                    outcome_str += " - Opponent executed better"
    
    narrative_parts.append(outcome_str)
    
    return " | ".join(narrative_parts)

def analyze_rally(rally_df: pd.DataFrame, shot_categories: Dict[str, List[str]], 
                  turning_point_threshold: float = 40.0, min_phase_length: int = 2) -> Dict:
    """
    Analyze a single rally from both P0 and P1 perspectives
    """
    rally_id = rally_df.iloc[0]['rally_id']
    game_number = rally_df.iloc[0].get('GameNumber', 'N/A')
    # Winner/loser flexible columns
    win_col = pick_col(rally_df, 'rally_winner', 'RallyWinner')
    lose_col = pick_col(rally_df, 'rally_loser', 'RallyLoser')
    rally_winner = rally_df.iloc[0].get(win_col) if win_col else None
    rally_loser = rally_df.iloc[0].get(lose_col) if lose_col else None
    if rally_winner is None or rally_loser is None:
        # Infer from final shot flags
        last = rally_df.iloc[-1]
        win_flag_col = pick_col(rally_df, 'is_winning_shot', 'IsWinningShot')
        lose_flag_col = pick_col(rally_df, 'is_losing_shot', 'IsLosingShot')
        if win_flag_col and parse_bool_like(last.get(win_flag_col)):
            rally_winner = last.get('Player')
            rally_loser = 'P0' if rally_winner == 'P1' else 'P1'
        elif lose_flag_col and parse_bool_like(last.get(lose_flag_col)):
            rally_loser = last.get('Player')
            rally_winner = 'P0' if rally_loser == 'P1' else 'P1'
    total_shots = len(rally_df)
    
    # Extract frame and phase information
    # Prefer FrameNumber; some CSVs have Frame
    start_frame = rally_df.iloc[0].get('FrameNumber', rally_df.iloc[0].get('Frame', 'N/A'))
    end_frame = rally_df.iloc[-1].get('FrameNumber', rally_df.iloc[-1].get('Frame', 'N/A'))
    # Prefer PhaseDetail
    phase = rally_df.iloc[0].get('PhaseDetail', rally_df.iloc[0].get('Phase', 'N/A'))
    
    # Separate shots by player
    p0_shots = rally_df[rally_df['Player'] == 'P0'].copy().reset_index(drop=True)
    p1_shots = rally_df[rally_df['Player'] == 'P1'].copy().reset_index(drop=True)
    
    # Detect phases for each player
    p0_phases = detect_phases(p0_shots, shot_categories, min_phase_length)
    p1_phases = detect_phases(p1_shots, shot_categories, min_phase_length)
    
    # Find turning points
    p0_turning_points = find_turning_points(p0_shots, turning_point_threshold)
    p1_turning_points = find_turning_points(p1_shots, turning_point_threshold)
    
    # Generate narratives
    p0_narrative = generate_narrative('P0', p0_phases, p0_turning_points, 'win' if rally_winner == 'P0' else 'loss', rally_winner)
    p1_narrative = generate_narrative('P1', p1_phases, p1_turning_points, 'win' if rally_winner == 'P1' else 'loss', rally_winner)
    
    # Format phase summaries
    p0_phases_str = " → ".join([
        f"{get_phase_label(p['category'])}({p['start_position']}-{p['end_position']})" 
        for p in p0_phases
    ])
    p1_phases_str = " → ".join([
        f"{get_phase_label(p['category'])}({p['start_position']}-{p['end_position']})" 
        for p in p1_phases
    ])
    
    return {
        'rally_id': rally_id,
        'game_number': game_number,
        'start_frame': start_frame,
        'end_frame': end_frame,
        'phase': phase,
        'rally_winner': rally_winner,
        'rally_loser': rally_loser,
        'total_shots': total_shots,
        'P0_narrative': p0_narrative,
        'P1_narrative': p1_narrative,
        'P0_phases': p0_phases_str,
        'P1_phases': p1_phases_str,
        'P0_turning_points': len(p0_turning_points),
        'P1_turning_points': len(p1_turning_points)
    }

def process_enriched_csv(input_csv: str, output_csv: str, shot_categories_json: str,
                        turning_point_threshold: float = 40.0, min_phase_length: int = 2):
    """
    Main processing function
    """
    print(f"Loading enriched CSV: {input_csv}")
    df = pd.read_csv(input_csv)
    # Ensure rally_id present
    if 'rally_id' not in df.columns:
        raise ValueError('Expected rally_id column in input CSV')
    # Ensure rally_position exists; derive if missing
    if 'rally_position' not in df.columns:
        # Sort within rally by StrokeNumber if present, then derive
        sort_cols = ['rally_id'] + (['StrokeNumber'] if 'StrokeNumber' in df.columns else [])
        df = df.sort_values(sort_cols).reset_index(drop=True)
        df['rally_position'] = df.groupby('rally_id').cumcount() + 1
    
    print(f"Loading shot categories from: {shot_categories_json}")
    shot_categories = load_shot_categories(shot_categories_json)
    
    print(f"Processing {len(df['rally_id'].unique())} rallies...")
    
    results = []
    
    # Group by rally
    for rally_id, rally_df in df.groupby('rally_id'):
        # Stable sort: StrokeNumber > rally_position > original order
        if 'StrokeNumber' in rally_df.columns:
            rally_df = rally_df.sort_values('StrokeNumber').reset_index(drop=True)
        else:
            rally_df = rally_df.sort_values('rally_position').reset_index(drop=True)
        
        try:
            result = analyze_rally(rally_df, shot_categories, turning_point_threshold, min_phase_length)
            results.append(result)
        except Exception as e:
            print(f"Error processing rally {rally_id}: {e}")
            continue
    
    # Create output dataframe
    output_df = pd.DataFrame(results)
    
    # Sort chronologically: extract game_number and rally_number from rally_id
    # rally_id format: "GameNumber_RallyNumber" or "GameNumber_RallyNumber_segN"
    def parse_rally_id(rally_id):
        text = str(rally_id)
        parts = text.split('_')
        nums = []
        for p in parts:
            try:
                nums.append(int(p))
            except Exception:
                # ignore non-numeric tokens like 'seg1'
                continue
        if len(nums) >= 2:
            return (nums[0], nums[1])
        # Fallback for single-number rally_ids
        try:
            return (0, int(text))
        except Exception:
            return (0, 0)
    
    output_df['_sort_key'] = output_df['rally_id'].apply(parse_rally_id)
    output_df = output_df.sort_values('_sort_key').drop(columns=['_sort_key']).reset_index(drop=True)
    
    print(f"Writing results to: {output_csv}")
    output_df.to_csv(output_csv, index=False)
    
    print(f"\nCompleted! Processed {len(results)} rallies.")
    print(f"\nSample narratives:")
    if len(output_df) > 0:
        print("\n" + "="*80)
        sample = output_df.iloc[0]
        print(f"Rally {sample['rally_id']} (Game {sample['game_number']}):")
        print(f"Winner: {sample['rally_winner']}")
        print(f"\nP0 Perspective:")
        print(sample['P0_narrative'])
        print(f"\nP1 Perspective:")
        print(sample['P1_narrative'])
        print("="*80)

if __name__ == '__main__':
    # This script now supports two modes:
    # 1) Input is already an effectiveness CSV: *_detailed_effectiveness.csv
    # 2) Input is a base detailed CSV: *_detailed.csv, in which case we auto-run
    #    compute_effectiveness_v2_hybrid.py to generate the effectiveness CSV first.
    if len(sys.argv) < 3:
        print("Usage: python rally_dynamics.py <input.csv> <output_narratives.csv> [shot_categories.json] [turning_point_threshold] [min_phase_length]")
        print("\nNotes:")
        print("  - If <input.csv> is *_detailed.csv, the script will first run compute_effectiveness_v2_hybrid.py")
        print("    to generate *_detailed_effectiveness.csv next to it, then proceed.")
        print("  - If <input.csv> is already *_detailed_effectiveness.csv, it will be used directly.")
        print("  - shot_categories.json defaults to response_classifications_template.json in project root.")
        print("\nExample:")
        print("  python rally_dynamics.py kiran/Kiran_2_detailed.csv rally_narratives.csv")
        print("  python rally_dynamics.py kiran/Kiran_2_detailed_effectiveness.csv rally_narratives.csv response_classifications_template.json 30 2")
        sys.exit(1)

    input_path = sys.argv[1]
    output_csv = sys.argv[2]
    # Default shot categories JSON to project root response_classifications_template.json
    default_shot_json = os.path.join(os.path.dirname(__file__), 'response_classifications_template.json')
    shot_categories_json = sys.argv[3] if len(sys.argv) > 3 else default_shot_json
    threshold = float(sys.argv[4]) if len(sys.argv) > 4 else 40.0
    min_phase_length = int(sys.argv[5]) if len(sys.argv) > 5 else 2

    # If input is not an effectiveness CSV, generate it using the hybrid script
    in_base = os.path.basename(input_path)
    in_dir = os.path.dirname(input_path)
    if in_base.endswith('_detailed_effectiveness.csv'):
        eff_csv = input_path
    else:
        # Derive effectiveness CSV name
        if in_base.endswith('_detailed.csv'):
            eff_name = in_base[:-len('_detailed.csv')] + '_detailed_effectiveness.csv'
        elif in_base.endswith('.csv'):
            eff_name = os.path.splitext(in_base)[0] + '_detailed_effectiveness.csv'
        else:
            eff_name = in_base + '_detailed_effectiveness.csv'
        eff_csv = os.path.join(in_dir, eff_name) if in_dir else eff_name
        # Paths for rules
        rules_json = default_shot_json
        triple_rules_json = os.path.join(os.path.dirname(__file__), 'triple_category_rules.json')
        # Run the hybrid effectiveness script
        print(f"Input is not an effectiveness CSV. Generating: {eff_csv}")
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), 'compute_effectiveness_v2_hybrid.py'),
            input_path,
            rules_json,
            rules_json,
            triple_rules_json,
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error generating effectiveness CSV: {e}")
            sys.exit(1)

    process_enriched_csv(eff_csv, output_csv, shot_categories_json, threshold, min_phase_length)

