import pandas as pd
import re
from collections import Counter, defaultdict
import json
import os

def extract_shot_types(narrative):
    """Extract shot types from narrative text."""
    shot_pattern = r'(overhead_\w+|backhand_\w+|forehand_\w+|flat_game\w*)'
    shots = re.findall(shot_pattern, narrative)
    return shots

def extract_turning_points(narrative):
    """Extract turning point information including shot type and swing."""
    tp_pattern = r'TURNING POINT Shot \d+: ([\w_]+) \((\d+)% eff, ([+-]\d+) swing\)'
    turning_points = re.findall(tp_pattern, narrative)
    return turning_points

def extract_phases(phase_sequence):
    """Extract list of phases from phase sequence."""
    if pd.isna(phase_sequence) or phase_sequence == '':
        return []
    
    phases = re.findall(r'(\w+(?:\s\w+)*)\(\d+-\d+\)', phase_sequence)
    return phases

def get_first_phase(phase_sequence):
    """Get the first phase from a phase sequence (excluding Serve)."""
    phases = extract_phases(phase_sequence)
    # Filter out 'Serve' from opening phases
    non_serve_phases = [p for p in phases if p.lower() != 'serve']
    return non_serve_phases[0] if non_serve_phases else None

def analyze_badminton_data(input_csv):
    """Main analysis function to extract all 9 insights into 3 files."""
    
    df = pd.read_csv(input_csv)
    
    # Normalize column names from rally_narratives.csv to expected schema
    rename_map = {
        'P0_narrative': 'P0_Narrative',
        'P1_narrative': 'P1_Narrative',
        'P0_phases': 'P0_Phases',
        'P1_phases': 'P1_Phases',
        'rally_winner': 'Winner',
        'game_number': 'GameNumber',
        'rally_id': 'RallyNumber',
        # Map lowercase frame columns produced by rally_dynamics to expected names
        'start_frame': 'StartFrame',
        'end_frame': 'EndFrame'
    }
    df = df.rename(columns=rename_map)
    
    # Ensure required columns exist with safe defaults if absent
    if 'Phase' not in df.columns:
        df['Phase'] = 'overall'
    if 'StartFrame' not in df.columns:
        df['StartFrame'] = ''
    if 'EndFrame' not in df.columns:
        df['EndFrame'] = ''
    
    summary_results = []
    detailed_data = {}
    frame_map_results = []
    
    # ===== INSIGHT 1: Phase Transitions & Playing Style Index =====
    print("Analyzing Insight 1: Phase transitions and playing style...")
    
    p0_all_phases = []
    p1_all_phases = []
    p0_total_transitions = 0
    p1_total_transitions = 0
    total_rallies = len(df)
    
    for idx, row in df.iterrows():
        p0_phases = extract_phases(row['P0_Phases'])
        p1_phases = extract_phases(row['P1_Phases'])
        
        # Filter out 'Serve' from phase analysis
        p0_phases_no_serve = [p for p in p0_phases if p.lower() != 'serve']
        p1_phases_no_serve = [p for p in p1_phases if p.lower() != 'serve']
        
        p0_transitions = len(p0_phases) - 1 if len(p0_phases) > 1 else 0
        p1_transitions = len(p1_phases) - 1 if len(p1_phases) > 1 else 0
        
        p0_total_transitions += p0_transitions
        p1_total_transitions += p1_transitions
        
        p0_all_phases.extend(p0_phases_no_serve)
        p1_all_phases.extend(p1_phases_no_serve)
    
    # Calculate average transitions
    p0_avg_transitions = p0_total_transitions / total_rallies
    p1_avg_transitions = p1_total_transitions / total_rallies
    
    # Phase counters
    p0_phase_counter = Counter(p0_all_phases)
    p1_phase_counter = Counter(p1_all_phases)
    
    p0_total = sum(p0_phase_counter.values())
    p1_total = sum(p1_phase_counter.values())
    
    # Create phase distribution strings
    p0_phase_dist = ', '.join([f"{phase}: {(count/p0_total)*100:.1f}%" 
                               for phase, count in p0_phase_counter.most_common()])
    p1_phase_dist = ', '.join([f"{phase}: {(count/p1_total)*100:.1f}%" 
                               for phase, count in p1_phase_counter.most_common()])
    
    summary_results.append({
        'Insight_Category': '1. Phase Transitions',
        'Player': 'P0',
        'Metric': 'Avg Transitions per Rally',
        'Value': f"{p0_avg_transitions:.2f}"
    })
    
    summary_results.append({
        'Insight_Category': '1. Phase Transitions',
        'Player': 'P1',
        'Metric': 'Avg Transitions per Rally',
        'Value': f"{p1_avg_transitions:.2f}"
    })
    
    summary_results.append({
        'Insight_Category': '1. Playing Style',
        'Player': 'P0',
        'Metric': 'Phase Distribution',
        'Value': p0_phase_dist
    })
    
    summary_results.append({
        'Insight_Category': '1. Playing Style',
        'Player': 'P1',
        'Metric': 'Phase Distribution',
        'Value': p1_phase_dist
    })
    
    # Detailed JSON data
    detailed_data['1_phase_transitions'] = {
        'p0': {
            'average': round(p0_avg_transitions, 2),
            'total_transitions': p0_total_transitions,
            'total_rallies': total_rallies
        },
        'p1': {
            'average': round(p1_avg_transitions, 2),
            'total_transitions': p1_total_transitions,
            'total_rallies': total_rallies
        }
    }
    
    detailed_data['1_playing_style_index'] = {
        'p0': {phase: {'count': count, 'percentage': round((count/p0_total)*100, 1)} 
               for phase, count in p0_phase_counter.most_common()},
        'p1': {phase: {'count': count, 'percentage': round((count/p1_total)*100, 1)} 
               for phase, count in p1_phase_counter.most_common()}
    }
    
    # ===== INSIGHT 2: Momentum Swing Frequency - Top 3 Shots per Player =====
    print("Analyzing Insight 2: Momentum swing frequency...")
    
    p0_positive_shots = []
    p0_negative_shots = []
    p1_positive_shots = []
    p1_negative_shots = []
    
    # Store detailed info for frame map
    p0_positive_details = []
    p0_negative_details = []
    p1_positive_details = []
    p1_negative_details = []
    
    for idx, row in df.iterrows():
        p0_tps = extract_turning_points(row['P0_Narrative'])
        p1_tps = extract_turning_points(row['P1_Narrative'])
        
        for shot, eff, swing in p0_tps:
            swing_val = int(swing)
            if swing_val > 0:
                p0_positive_shots.append(shot)
                p0_positive_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'shot': shot,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame'],
                    'swing': swing,
                    'effectiveness': eff
                })
            else:
                p0_negative_shots.append(shot)
                p0_negative_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'shot': shot,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame'],
                    'swing': swing,
                    'effectiveness': eff
                })
        
        for shot, eff, swing in p1_tps:
            swing_val = int(swing)
            if swing_val > 0:
                p1_positive_shots.append(shot)
                p1_positive_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'shot': shot,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame'],
                    'swing': swing,
                    'effectiveness': eff
                })
            else:
                p1_negative_shots.append(shot)
                p1_negative_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'shot': shot,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame'],
                    'swing': swing,
                    'effectiveness': eff
                })
    
    p0_pos_counter = Counter(p0_positive_shots)
    p0_neg_counter = Counter(p0_negative_shots)
    p1_pos_counter = Counter(p1_positive_shots)
    p1_neg_counter = Counter(p1_negative_shots)
    
    # Top 3 for each
    p0_top3_pos = p0_pos_counter.most_common(3)
    p0_top3_neg = p0_neg_counter.most_common(3)
    p1_top3_pos = p1_pos_counter.most_common(3)
    p1_top3_neg = p1_neg_counter.most_common(3)
    
    # Build frame ranges for P0 positive swings (top 3 shots)
    p0_top_pos_set = {shot for shot, _ in p0_top3_pos}
    p0_pos_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p0_positive_details
        if d.get('shot') in p0_top_pos_set and d.get('start_frame') and d.get('end_frame')
    ][:10]
    p0_pos_first = next((d for d in p0_positive_details if d.get('shot') in p0_top_pos_set and d.get('start_frame') and d.get('end_frame')), None)
    summary_results.append({
        'Insight_Category': '2. Momentum Swings - Positive',
        'Player': 'P0',
        'Metric': 'Top 3 Shots Causing +Swing',
        'Value': ', '.join([f"{shot} ({count}x)" for shot, count in p0_top3_pos]),
        'StartFrame': (p0_pos_first.get('start_frame') if p0_pos_first else ''),
        'EndFrame': (p0_pos_first.get('end_frame') if p0_pos_first else ''),
        'FrameRanges': '; '.join(p0_pos_ranges)
    })
    
    # Build frame ranges for P0 negative swings (top 3 shots)
    p0_top_neg_set = {shot for shot, _ in p0_top3_neg}
    p0_neg_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p0_negative_details
        if d.get('shot') in p0_top_neg_set and d.get('start_frame') and d.get('end_frame')
    ][:10]
    p0_neg_first = next((d for d in p0_negative_details if d.get('shot') in p0_top_neg_set and d.get('start_frame') and d.get('end_frame')), None)
    summary_results.append({
        'Insight_Category': '2. Momentum Swings - Negative',
        'Player': 'P0',
        'Metric': 'Top 3 Shots Causing -Swing',
        'Value': ', '.join([f"{shot} ({count}x)" for shot, count in p0_top3_neg]),
        'StartFrame': (p0_neg_first.get('start_frame') if p0_neg_first else ''),
        'EndFrame': (p0_neg_first.get('end_frame') if p0_neg_first else ''),
        'FrameRanges': '; '.join(p0_neg_ranges)
    })
    
    # Build frame ranges for P1 positive swings (top 3 shots)
    p1_top_pos_set = {shot for shot, _ in p1_top3_pos}
    p1_pos_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p1_positive_details
        if d.get('shot') in p1_top_pos_set and d.get('start_frame') and d.get('end_frame')
    ][:10]
    p1_pos_first = next((d for d in p1_positive_details if d.get('shot') in p1_top_pos_set and d.get('start_frame') and d.get('end_frame')), None)
    summary_results.append({
        'Insight_Category': '2. Momentum Swings - Positive',
        'Player': 'P1',
        'Metric': 'Top 3 Shots Causing +Swing',
        'Value': ', '.join([f"{shot} ({count}x)" for shot, count in p1_top3_pos]),
        'StartFrame': (p1_pos_first.get('start_frame') if p1_pos_first else ''),
        'EndFrame': (p1_pos_first.get('end_frame') if p1_pos_first else ''),
        'FrameRanges': '; '.join(p1_pos_ranges)
    })
    
    # Build frame ranges for P1 negative swings (top 3 shots)
    p1_top_neg_set = {shot for shot, _ in p1_top3_neg}
    p1_neg_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p1_negative_details
        if d.get('shot') in p1_top_neg_set and d.get('start_frame') and d.get('end_frame')
    ][:10]
    p1_neg_first = next((d for d in p1_negative_details if d.get('shot') in p1_top_neg_set and d.get('start_frame') and d.get('end_frame')), None)
    summary_results.append({
        'Insight_Category': '2. Momentum Swings - Negative',
        'Player': 'P1',
        'Metric': 'Top 3 Shots Causing -Swing',
        'Value': ', '.join([f"{shot} ({count}x)" for shot, count in p1_top3_neg]),
        'StartFrame': (p1_neg_first.get('start_frame') if p1_neg_first else ''),
        'EndFrame': (p1_neg_first.get('end_frame') if p1_neg_first else ''),
        'FrameRanges': '; '.join(p1_neg_ranges)
    })
    
    # Add to frame map - all instances
    for detail in p0_positive_details:
        if detail['shot'] in [shot for shot, _ in p0_top3_pos]:
            frame_map_results.append({
                'Type': 'Shot',
                'Category': 'Positive Momentum',
                'Player': 'P0',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['shot'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': detail['swing'],
                'Effectiveness': f"{detail['effectiveness']}%",
                'Context': 'Turning point shot'
            })
    
    for detail in p0_negative_details:
        if detail['shot'] in [shot for shot, _ in p0_top3_neg]:
            frame_map_results.append({
                'Type': 'Shot',
                'Category': 'Negative Momentum',
                'Player': 'P0',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['shot'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': detail['swing'],
                'Effectiveness': f"{detail['effectiveness']}%",
                'Context': 'Lost momentum'
            })
    
    for detail in p1_positive_details:
        if detail['shot'] in [shot for shot, _ in p1_top3_pos]:
            frame_map_results.append({
                'Type': 'Shot',
                'Category': 'Positive Momentum',
                'Player': 'P1',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['shot'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': detail['swing'],
                'Effectiveness': f"{detail['effectiveness']}%",
                'Context': 'Turning point shot'
            })
    
    for detail in p1_negative_details:
        if detail['shot'] in [shot for shot, _ in p1_top3_neg]:
            frame_map_results.append({
                'Type': 'Shot',
                'Category': 'Negative Momentum',
                'Player': 'P1',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['shot'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': detail['swing'],
                'Effectiveness': f"{detail['effectiveness']}%",
                'Context': 'Lost momentum'
            })
    
    # Detailed JSON
    detailed_data['2_momentum_swings_positive'] = {
        'p0': {shot: {'count': count} for shot, count in p0_pos_counter.most_common()},
        'p1': {shot: {'count': count} for shot, count in p1_pos_counter.most_common()}
    }
    
    detailed_data['2_momentum_swings_negative'] = {
        'p0': {shot: {'count': count} for shot, count in p0_neg_counter.most_common()},
        'p1': {shot: {'count': count} for shot, count in p1_neg_counter.most_common()}
    }
    
    # ===== INSIGHT 4: Most Common Opening Phases (Excluding Serve) =====
    print("Analyzing Insight 4: Most common opening phases...")
    
    p0_opening_phases = []
    p1_opening_phases = []
    
    for idx, row in df.iterrows():
        p0_first = get_first_phase(row['P0_Phases'])
        p1_first = get_first_phase(row['P1_Phases'])
        
        if p0_first:
            p0_opening_phases.append(p0_first)
        if p1_first:
            p1_opening_phases.append(p1_first)
    
    p0_opening_counter = Counter(p0_opening_phases)
    p1_opening_counter = Counter(p1_opening_phases)
    
    p0_opening_total = len(p0_opening_phases)
    p1_opening_total = len(p1_opening_phases)
    
    p0_opening_str = ', '.join([f"{phase} ({count}, {(count/p0_opening_total)*100:.1f}%)" 
                                for phase, count in p0_opening_counter.most_common(3)])
    p1_opening_str = ', '.join([f"{phase} ({count}, {(count/p1_opening_total)*100:.1f}%)" 
                                for phase, count in p1_opening_counter.most_common(3)])
    
    summary_results.append({
        'Insight_Category': '4. Opening Phases',
        'Player': 'P0',
        'Metric': 'Most Common Opening (excl. Serve)',
        'Value': p0_opening_str
    })
    
    summary_results.append({
        'Insight_Category': '4. Opening Phases',
        'Player': 'P1',
        'Metric': 'Most Common Opening (excl. Serve)',
        'Value': p1_opening_str
    })
    
    detailed_data['4_opening_phases'] = {
        'p0': {phase: {'count': count, 'percentage': round((count/p0_opening_total)*100, 1)} 
               for phase, count in p0_opening_counter.most_common()},
        'p1': {phase: {'count': count, 'percentage': round((count/p1_opening_total)*100, 1)} 
               for phase, count in p1_opening_counter.most_common()}
    }
    
    # ===== INSIGHT 5: Top 2 Phase Winning/Losing Transitions =====
    print("Analyzing Insight 5: Winning and losing phase transitions...")
    
    p0_win_transitions = []
    p0_loss_transitions = []
    p1_win_transitions = []
    p1_loss_transitions = []
    
    # Store details for frame map
    p0_win_trans_details = []
    p0_loss_trans_details = []
    p1_win_trans_details = []
    p1_loss_trans_details = []
    
    for idx, row in df.iterrows():
        p0_phases = extract_phases(row['P0_Phases'])
        p1_phases = extract_phases(row['P1_Phases'])
        
        # Create transitions
        p0_trans = [f"{p0_phases[i]} → {p0_phases[i+1]}" for i in range(len(p0_phases)-1)]
        p1_trans = [f"{p1_phases[i]} → {p1_phases[i+1]}" for i in range(len(p1_phases)-1)]
        
        if row['Winner'] == 'P0':
            p0_win_transitions.extend(p0_trans)
            p1_loss_transitions.extend(p1_trans)
            for trans in p0_trans:
                p0_win_trans_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'transition': trans,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame']
                })
            for trans in p1_trans:
                p1_loss_trans_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'transition': trans,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame']
                })
        else:
            p1_win_transitions.extend(p1_trans)
            p0_loss_transitions.extend(p0_trans)
            for trans in p1_trans:
                p1_win_trans_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'transition': trans,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame']
                })
            for trans in p0_trans:
                p0_loss_trans_details.append({
                    'game': row['GameNumber'],
                    'rally': row['RallyNumber'],
                    'phase': row['Phase'],
                    'transition': trans,
                    'start_frame': row['StartFrame'],
                    'end_frame': row['EndFrame']
                })
    
    p0_win_counter = Counter(p0_win_transitions)
    p0_loss_counter = Counter(p0_loss_transitions)
    p1_win_counter = Counter(p1_win_transitions)
    p1_loss_counter = Counter(p1_loss_transitions)
    
    # Attach frames using first matching detail for top transitions when available
    def first_frames(details_list, transitions):
        try:
            if not transitions:
                return ('', '')
            first_trans = transitions[0]
            for d in details_list:
                if d.get('transition') == first_trans:
                    return (d.get('start_frame', ''), d.get('end_frame', ''))
        except Exception:
            pass
        return ('', '')

    top_p0_win = [trans for trans, _ in p0_win_counter.most_common(2)]
    win_sf, win_ef = first_frames(p0_win_trans_details, top_p0_win)
    p0_win_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p0_win_trans_details
        if d.get('transition') in top_p0_win and d.get('start_frame') and d.get('end_frame')
    ][:10]
    summary_results.append({
        'Insight_Category': '5. Phase Transitions',
        'Player': 'P0',
        'Metric': 'Top 2 Winning Transitions',
        'Value': ', '.join([f"{trans} ({count}x)" for trans, count in p0_win_counter.most_common(2)]),
        'StartFrame': win_sf,
        'EndFrame': win_ef,
        'FrameRanges': '; '.join(p0_win_ranges)
    })
    
    top_p0_loss = [trans for trans, _ in p0_loss_counter.most_common(2)]
    loss_sf, loss_ef = first_frames(p0_loss_trans_details, top_p0_loss)
    p0_loss_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p0_loss_trans_details
        if d.get('transition') in top_p0_loss and d.get('start_frame') and d.get('end_frame')
    ][:10]
    summary_results.append({
        'Insight_Category': '5. Phase Transitions',
        'Player': 'P0',
        'Metric': 'Top 2 Losing Transitions',
        'Value': ', '.join([f"{trans} ({count}x)" for trans, count in p0_loss_counter.most_common(2)]),
        'StartFrame': loss_sf,
        'EndFrame': loss_ef,
        'FrameRanges': '; '.join(p0_loss_ranges)
    })
    
    top_p1_win = [trans for trans, _ in p1_win_counter.most_common(2)]
    p1_win_sf, p1_win_ef = first_frames(p1_win_trans_details, top_p1_win)
    p1_win_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p1_win_trans_details
        if d.get('transition') in top_p1_win and d.get('start_frame') and d.get('end_frame')
    ][:10]
    summary_results.append({
        'Insight_Category': '5. Phase Transitions',
        'Player': 'P1',
        'Metric': 'Top 2 Winning Transitions',
        'Value': ', '.join([f"{trans} ({count}x)" for trans, count in p1_win_counter.most_common(2)]),
        'StartFrame': p1_win_sf,
        'EndFrame': p1_win_ef,
        'FrameRanges': '; '.join(p1_win_ranges)
    })
    
    top_p1_loss = [trans for trans, _ in p1_loss_counter.most_common(2)]
    p1_loss_sf, p1_loss_ef = first_frames(p1_loss_trans_details, top_p1_loss)
    p1_loss_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p1_loss_trans_details
        if d.get('transition') in top_p1_loss and d.get('start_frame') and d.get('end_frame')
    ][:10]
    summary_results.append({
        'Insight_Category': '5. Phase Transitions',
        'Player': 'P1',
        'Metric': 'Top 2 Losing Transitions',
        'Value': ', '.join([f"{trans} ({count}x)" for trans, count in p1_loss_counter.most_common(2)]),
        'StartFrame': p1_loss_sf,
        'EndFrame': p1_loss_ef,
        'FrameRanges': '; '.join(p1_loss_ranges)
    })
    
    # Add top 2 to frame map
    p0_top2_win = [trans for trans, _ in p0_win_counter.most_common(2)]
    p0_top2_loss = [trans for trans, _ in p0_loss_counter.most_common(2)]
    p1_top2_win = [trans for trans, _ in p1_win_counter.most_common(2)]
    p1_top2_loss = [trans for trans, _ in p1_loss_counter.most_common(2)]
    
    for detail in p0_win_trans_details:
        if detail['transition'] in p0_top2_win:
            frame_map_results.append({
                'Type': 'Rally',
                'Category': 'Winning Transition',
                'Player': 'P0',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['transition'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': '',
                'Effectiveness': '',
                'Context': 'Won rally'
            })
    
    for detail in p0_loss_trans_details:
        if detail['transition'] in p0_top2_loss:
            frame_map_results.append({
                'Type': 'Rally',
                'Category': 'Losing Transition',
                'Player': 'P0',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['transition'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': '',
                'Effectiveness': '',
                'Context': 'Lost rally'
            })
    
    for detail in p1_win_trans_details:
        if detail['transition'] in p1_top2_win:
            frame_map_results.append({
                'Type': 'Rally',
                'Category': 'Winning Transition',
                'Player': 'P1',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['transition'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': '',
                'Effectiveness': '',
                'Context': 'Won rally'
            })
    
    for detail in p1_loss_trans_details:
        if detail['transition'] in p1_top2_loss:
            frame_map_results.append({
                'Type': 'Rally',
                'Category': 'Losing Transition',
                'Player': 'P1',
                'Game': detail['game'],
                'Rally': detail['rally'],
                'Phase': detail['phase'],
                'Shot_Type_or_Sequence': detail['transition'],
                'StartFrame': detail['start_frame'],
                'EndFrame': detail['end_frame'],
                'Swing': '',
                'Effectiveness': '',
                'Context': 'Lost rally'
            })
    
    detailed_data['5_phase_transitions'] = {
        'p0_winning': {trans: {'count': count} for trans, count in p0_win_counter.most_common()},
        'p0_losing': {trans: {'count': count} for trans, count in p0_loss_counter.most_common()},
        'p1_winning': {trans: {'count': count} for trans, count in p1_win_counter.most_common()},
        'p1_losing': {trans: {'count': count} for trans, count in p1_loss_counter.most_common()}
    }
    
    # ===== INSIGHT 6: Ability to Maintain Advantage (Aggregate) =====
    print("Analyzing Insight 6: Maintaining advantage after positive swings...")
    
    p0_positive_swing_wins = 0
    p0_positive_swing_total = 0
    p1_positive_swing_wins = 0
    p1_positive_swing_total = 0
    
    for idx, row in df.iterrows():
        p0_tps = extract_turning_points(row['P0_Narrative'])
        p1_tps = extract_turning_points(row['P1_Narrative'])
        
        p0_has_positive = any(int(swing) > 0 for _, _, swing in p0_tps)
        p1_has_positive = any(int(swing) > 0 for _, _, swing in p1_tps)
        
        if p0_has_positive:
            p0_positive_swing_total += 1
            if row['Winner'] == 'P0':
                p0_positive_swing_wins += 1
        
        if p1_has_positive:
            p1_positive_swing_total += 1
            if row['Winner'] == 'P1':
                p1_positive_swing_wins += 1
    
    p0_maintain_rate = (p0_positive_swing_wins / p0_positive_swing_total * 100) if p0_positive_swing_total > 0 else 0
    p1_maintain_rate = (p1_positive_swing_wins / p1_positive_swing_total * 100) if p1_positive_swing_total > 0 else 0
    
    summary_results.append({
        'Insight_Category': '6. Maintain Advantage',
        'Player': 'P0',
        'Metric': 'Win Rate After +Swing',
        'Value': f"{p0_maintain_rate:.1f}% ({p0_positive_swing_wins}/{p0_positive_swing_total})"
    })
    
    summary_results.append({
        'Insight_Category': '6. Maintain Advantage',
        'Player': 'P1',
        'Metric': 'Win Rate After +Swing',
        'Value': f"{p1_maintain_rate:.1f}% ({p1_positive_swing_wins}/{p1_positive_swing_total})"
    })
    
    detailed_data['6_maintain_advantage'] = {
        'p0': {
            'win_rate': round(p0_maintain_rate, 1),
            'wins': p0_positive_swing_wins,
            'total_rallies_with_positive_swings': p0_positive_swing_total
        },
        'p1': {
            'win_rate': round(p1_maintain_rate, 1),
            'wins': p1_positive_swing_wins,
            'total_rallies_with_positive_swings': p1_positive_swing_total
        }
    }
    
    # ===== INSIGHT 7: Crucial Phase Strategies (Most Used Only) =====
    print("Analyzing Insight 7: Crucial phase strategies...")
    
    crucial_df = df[df['Phase'] == 'crucial']
    
    p0_crucial_sequences = []
    p1_crucial_sequences = []
    
    p0_crucial_seq_details = []
    p1_crucial_seq_details = []
    
    for idx, row in crucial_df.iterrows():
        p0_phases = extract_phases(row['P0_Phases'])
        p1_phases = extract_phases(row['P1_Phases'])
        
        # Filter out 'Serve' from crucial phase sequences
        p0_phases_no_serve = [p for p in p0_phases if p.lower() != 'serve']
        p1_phases_no_serve = [p for p in p1_phases if p.lower() != 'serve']
        
        p0_seq = ' → '.join(p0_phases_no_serve) if p0_phases_no_serve else 'N/A'
        p1_seq = ' → '.join(p1_phases_no_serve) if p1_phases_no_serve else 'N/A'
        
        p0_crucial_sequences.append(p0_seq)
        p1_crucial_sequences.append(p1_seq)
        
        p0_crucial_seq_details.append({
            'game': row['GameNumber'],
            'rally': row['RallyNumber'],
            'sequence': p0_seq,
            'start_frame': row['StartFrame'],
            'end_frame': row['EndFrame'],
            'winner': row['Winner']
        })
        
        p1_crucial_seq_details.append({
            'game': row['GameNumber'],
            'rally': row['RallyNumber'],
            'sequence': p1_seq,
            'start_frame': row['StartFrame'],
            'end_frame': row['EndFrame'],
            'winner': row['Winner']
        })
    
    p0_crucial_counter = Counter(p0_crucial_sequences)
    p1_crucial_counter = Counter(p1_crucial_sequences)
    
    p0_crucial_total = len(p0_crucial_sequences)
    p1_crucial_total = len(p1_crucial_sequences)
    
    p0_most_used = p0_crucial_counter.most_common(1)[0] if p0_crucial_counter else ('N/A', 0)
    p1_most_used = p1_crucial_counter.most_common(1)[0] if p1_crucial_counter else ('N/A', 0)
    
    p0_most_used_pct = (p0_most_used[1] / p0_crucial_total * 100) if p0_crucial_total > 0 else 0
    p1_most_used_pct = (p1_most_used[1] / p1_crucial_total * 100) if p1_crucial_total > 0 else 0
    
    # Attach frames for most used crucial sequences (first matching occurrence)
    def crucial_frames(details_list, sequence):
        try:
            for d in details_list:
                if d.get('sequence') == sequence:
                    return (d.get('start_frame', ''), d.get('end_frame', ''))
        except Exception:
            pass
        return ('', '')

    p0_csf, p0_cef = crucial_frames(p0_crucial_seq_details, p0_most_used[0])
    p0_crucial_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p0_crucial_seq_details
        if d.get('sequence') == p0_most_used[0] and d.get('start_frame') and d.get('end_frame')
    ][:10]
    summary_results.append({
        'Insight_Category': '7. Crucial Phase Strategy',
        'Player': 'P0',
        'Metric': 'Most Used Crucial Sequence',
        'Value': f"{p0_most_used[0]} ({p0_most_used[1]}x, {p0_most_used_pct:.1f}%)",
        'StartFrame': p0_csf,
        'EndFrame': p0_cef,
        'FrameRanges': '; '.join(p0_crucial_ranges)
    })
    
    p1_csf, p1_cef = crucial_frames(p1_crucial_seq_details, p1_most_used[0])
    p1_crucial_ranges = [
        f"{d['start_frame']}-{d['end_frame']}"
        for d in p1_crucial_seq_details
        if d.get('sequence') == p1_most_used[0] and d.get('start_frame') and d.get('end_frame')
    ][:10]
    summary_results.append({
        'Insight_Category': '7. Crucial Phase Strategy',
        'Player': 'P1',
        'Metric': 'Most Used Crucial Sequence',
        'Value': f"{p1_most_used[0]} ({p1_most_used[1]}x, {p1_most_used_pct:.1f}%)",
        'StartFrame': p1_csf,
        'EndFrame': p1_cef,
        'FrameRanges': '; '.join(p1_crucial_ranges)
    })
    
    # Add all crucial phase rallies to frame map
    for detail in p0_crucial_seq_details:
        frame_map_results.append({
            'Type': 'Rally',
            'Category': 'Crucial Strategy',
            'Player': 'P0',
            'Game': detail['game'],
            'Rally': detail['rally'],
            'Phase': 'crucial',
            'Shot_Type_or_Sequence': detail['sequence'],
            'StartFrame': detail['start_frame'],
            'EndFrame': detail['end_frame'],
            'Swing': '',
            'Effectiveness': '',
            'Context': f"Winner: {detail['winner']}"
        })
    
    for detail in p1_crucial_seq_details:
        frame_map_results.append({
            'Type': 'Rally',
            'Category': 'Crucial Strategy',
            'Player': 'P1',
            'Game': detail['game'],
            'Rally': detail['rally'],
            'Phase': 'crucial',
            'Shot_Type_or_Sequence': detail['sequence'],
            'StartFrame': detail['start_frame'],
            'EndFrame': detail['end_frame'],
            'Swing': '',
            'Effectiveness': '',
            'Context': f"Winner: {detail['winner']}"
        })
    
    detailed_data['7_crucial_phase_strategies'] = {
        'p0': {seq: {'count': count, 'percentage': round((count/p0_crucial_total)*100, 1)} 
               for seq, count in p0_crucial_counter.most_common()},
        'p1': {seq: {'count': count, 'percentage': round((count/p1_crucial_total)*100, 1)} 
               for seq, count in p1_crucial_counter.most_common()}
    }
    
    # ===== INSIGHT 8: Phase Selection Differences (Top 2-3) =====
    print("Analyzing Insight 8: Phase selection differences...")
    
    p0_top_phases = p0_phase_counter.most_common(3)
    p1_top_phases = p1_phase_counter.most_common(3)
    
    p0_top_str = ', '.join([f"{phase} ({count}, {(count/p0_total)*100:.1f}%)" 
                            for phase, count in p0_top_phases])
    p1_top_str = ', '.join([f"{phase} ({count}, {(count/p1_total)*100:.1f}%)" 
                            for phase, count in p1_top_phases])
    
    summary_results.append({
        'Insight_Category': '8. Phase Selection',
        'Player': 'P0',
        'Metric': 'Top 3 Phases',
        'Value': p0_top_str
    })
    
    summary_results.append({
        'Insight_Category': '8. Phase Selection',
        'Player': 'P1',
        'Metric': 'Top 3 Phases',
        'Value': p1_top_str
    })
    
    detailed_data['8_phase_selection_differences'] = {
        'p0_top3': [{'phase': phase, 'count': count, 'percentage': round((count/p0_total)*100, 1)} 
                    for phase, count in p0_top_phases],
        'p1_top3': [{'phase': phase, 'count': count, 'percentage': round((count/p1_total)*100, 1)} 
                    for phase, count in p1_top_phases]
    }
    
    # ===== INSIGHT 9: "Couldn't Convert Opportunities" Frequency =====
    print("Analyzing Insight 9: Couldn't convert opportunities frequency...")
    
    p0_no_convert_count = 0
    p1_no_convert_count = 0
    p0_no_convert_by_phase = defaultdict(int)
    p1_no_convert_by_phase = defaultdict(int)
    
    p0_no_convert_details = []
    p1_no_convert_details = []
    
    for idx, row in df.iterrows():
        if "Couldn't convert opportunities" in row['P0_Narrative']:
            p0_no_convert_count += 1
            p0_phases = extract_phases(row['P0_Phases'])
            # Filter out 'Serve' from failed conversion phase analysis
            p0_phases_no_serve = [p for p in p0_phases if p.lower() != 'serve']
            for phase in p0_phases_no_serve:
                p0_no_convert_by_phase[phase] += 1
            
            p0_no_convert_details.append({
                'game': row['GameNumber'],
                'rally': row['RallyNumber'],
                'phase': row['Phase'],
                'start_frame': row['StartFrame'],
                'end_frame': row['EndFrame']
            })
        
        if "Couldn't convert opportunities" in row['P1_Narrative']:
            p1_no_convert_count += 1
            p1_phases = extract_phases(row['P1_Phases'])
            # Filter out 'Serve' from failed conversion phase analysis
            p1_phases_no_serve = [p for p in p1_phases if p.lower() != 'serve']
            for phase in p1_phases_no_serve:
                p1_no_convert_by_phase[phase] += 1
            
            p1_no_convert_details.append({
                'game': row['GameNumber'],
                'rally': row['RallyNumber'],
                'phase': row['Phase'],
                'start_frame': row['StartFrame'],
                'end_frame': row['EndFrame']
            })
    
    summary_results.append({
        'Insight_Category': '9. Failed Conversions',
        'Player': 'P0',
        'Metric': 'Total Occurrences',
        'Value': f"{p0_no_convert_count} times"
    })
    
    # Add phase breakdown if >= 3 occurrences
    if p0_no_convert_count >= 3:
        p0_phase_breakdown = ', '.join([f"{phase}: {count}x" 
                                        for phase, count in sorted(p0_no_convert_by_phase.items(), 
                                                                  key=lambda x: x[1], reverse=True)])
        summary_results.append({
            'Insight_Category': '9. Failed Conversions',
            'Player': 'P0',
            'Metric': 'Phases with Failures',
            'Value': p0_phase_breakdown
        })
    
    summary_results.append({
        'Insight_Category': '9. Failed Conversions',
        'Player': 'P1',
        'Metric': 'Total Occurrences',
        'Value': f"{p1_no_convert_count} times"
    })
    
    # Add phase breakdown if >= 3 occurrences
    if p1_no_convert_count >= 3:
        p1_phase_breakdown = ', '.join([f"{phase}: {count}x" 
                                        for phase, count in sorted(p1_no_convert_by_phase.items(), 
                                                                  key=lambda x: x[1], reverse=True)])
        summary_results.append({
            'Insight_Category': '9. Failed Conversions',
            'Player': 'P1',
            'Metric': 'Phases with Failures',
            'Value': p1_phase_breakdown
        })
    
    # Add to frame map
    for detail in p0_no_convert_details:
        frame_map_results.append({
            'Type': 'Rally',
            'Category': 'Failed Conversion',
            'Player': 'P0',
            'Game': detail['game'],
            'Rally': detail['rally'],
            'Phase': detail['phase'],
            'Shot_Type_or_Sequence': 'N/A',
            'StartFrame': detail['start_frame'],
            'EndFrame': detail['end_frame'],
            'Swing': '',
            'Effectiveness': '',
            'Context': "Couldn't convert opportunities"
        })
    
    for detail in p1_no_convert_details:
        frame_map_results.append({
            'Type': 'Rally',
            'Category': 'Failed Conversion',
            'Player': 'P1',
            'Game': detail['game'],
            'Rally': detail['rally'],
            'Phase': detail['phase'],
            'Shot_Type_or_Sequence': 'N/A',
            'StartFrame': detail['start_frame'],
            'EndFrame': detail['end_frame'],
            'Swing': '',
            'Effectiveness': '',
            'Context': "Couldn't convert opportunities"
        })
    
    detailed_data['9_failed_conversions'] = {
        'p0': {
            'total': p0_no_convert_count,
            'by_phase': dict(p0_no_convert_by_phase),
            'rally_list': p0_no_convert_details
        },
        'p1': {
            'total': p1_no_convert_count,
            'by_phase': dict(p1_no_convert_by_phase),
            'rally_list': p1_no_convert_details
        }
    }

    # ===== INSIGHT 10: Overall Most Effective/Ineffective Corner =====
    try:
        base_dir = os.path.dirname(input_csv)
        # Prefer focused CSV if present; fallback to full zones file
        ztb_path = os.path.join(base_dir, 'zone_effectiveness_top_vs_bottom.csv')
        zsf_path = os.path.join(base_dir, 'zone_success_frames.csv')
        zones_df = None
        if os.path.exists(ztb_path):
            zones_df = pd.read_csv(ztb_path)
        elif os.path.exists(zsf_path):
            zones_df = pd.read_csv(zsf_path)
        if zones_df is not None and not zones_df.empty:
            # Normalize columns
            if 'ZoneType' in zones_df.columns:
                eff_rows = zones_df[zones_df['ZoneType'].astype(str).isin(['most_effective', 'most_ineffective'])].copy()
            else:
                eff_rows = pd.DataFrame()
            for player in ['P0', 'P1']:
                pf = eff_rows[eff_rows.get('Player', '').astype(str) == player]
                if not pf.empty:
                    # Most Effective Corner
                    me = pf[pf['ZoneType'] == 'most_effective']
                    if not me.empty:
                        r = me.iloc[0]
                        zone = str(r.get('AnchorHittingZone'))
                        uses = r.get('Uses')
                        avg = r.get('AvgEffectiveness')
                        frames = str(r.get('AllFrames') or '')
                        frame_ranges = '; '.join(frames.split('|')[:8]) if frames else ''
                        summary_results.append({
                            'Insight_Category': '10. Zone Effectiveness',
                            'Player': player,
                            'Metric': 'Most Effective Corner',
                            'Value': f"{zone} (avg={avg if pd.notna(avg) else 'NA'}%, uses={int(uses) if pd.notna(uses) else 'NA'})",
                            'FrameRanges': frame_ranges,
                        })
                    # Most Ineffective Corner
                    mi = pf[pf['ZoneType'] == 'most_ineffective']
                    if not mi.empty:
                        r = mi.iloc[0]
                        zone = str(r.get('AnchorHittingZone'))
                        uses = r.get('Uses')
                        avg = r.get('AvgEffectiveness')
                        frames = str(r.get('AllFrames') or '')
                        frame_ranges = '; '.join(frames.split('|')[:8]) if frames else ''
                        summary_results.append({
                            'Insight_Category': '10. Zone Effectiveness',
                            'Player': player,
                            'Metric': 'Most Ineffective Corner',
                            'Value': f"{zone} (avg={avg if pd.notna(avg) else 'NA'}%, uses={int(uses) if pd.notna(uses) else 'NA'})",
                            'FrameRanges': frame_ranges,
                        })
    except Exception:
        # Optional enrichment; ignore failures
        pass
    
    # Ensure StartFrame/EndFrame columns exist on all summary rows
    for _row in summary_results:
        if 'StartFrame' not in _row:
            _row['StartFrame'] = ''
        if 'EndFrame' not in _row:
            _row['EndFrame'] = ''

    return pd.DataFrame(summary_results), detailed_data, pd.DataFrame(frame_map_results)


if __name__ == "__main__":
    import sys
    
    # Check if input file is provided
    if len(sys.argv) < 2:
        print("Usage: python badminton_insights_analyzer.py <input_csv_file>")
        print("Example: python badminton_insights_analyzer.py phase_winloss_narratives.csv")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # Extract filename and save to outputs directory
    import os
    base_filename = os.path.basename(input_file).replace('.csv', '')
    
    # Prefer project outputs directory; allow override via env; fallback to /mnt path if explicitly present
    preferred_outputs_dir = os.environ.get('OUTPUTS_DIR') or os.path.join(os.path.dirname(__file__), 'refined_outputs')
    if not os.path.isdir(preferred_outputs_dir):
        try:
            os.makedirs(preferred_outputs_dir, exist_ok=True)
        except Exception:
            # Last resort fallback
            preferred_outputs_dir = '/mnt/user-data/outputs'
            os.makedirs(preferred_outputs_dir, exist_ok=True)
    
    summary_file = os.path.join(preferred_outputs_dir, f'{base_filename}_insights_summary.csv')
    detailed_file = os.path.join(preferred_outputs_dir, f'{base_filename}_insights_detailed.json')
    frame_map_file = os.path.join(preferred_outputs_dir, f'{base_filename}_frame_map.csv')
    
    print(f"Reading data from: {input_file}")
    print("=" * 60)
    
    # Perform analysis
    summary_df, detailed_data, frame_map_df = analyze_badminton_data(input_file)
    
    # Save files
    summary_df.to_csv(summary_file, index=False)
    
    with open(detailed_file, 'w') as f:
        json.dump(detailed_data, f, indent=2)
    
    frame_map_df.to_csv(frame_map_file, index=False)
    
    print("=" * 60)
    print(f"✅ Analysis complete!")
    print(f"\n📁 Generated Files:")
    print(f"  1. Summary CSV: {summary_file}")
    print(f"     - {len(summary_df)} summary insights")
    print(f"  2. Detailed JSON: {detailed_file}")
    print(f"     - Complete frequency breakdowns")
    print(f"  3. Frame Map CSV: {frame_map_file}")
    print(f"     - {len(frame_map_df)} frame-referenced entries")

