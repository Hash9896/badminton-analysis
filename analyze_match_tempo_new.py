"""
New tempo analysis method with execution time calculation and validation.
Creates a unified tempo analysis CSV from tempo_events and effectiveness CSVs.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple, Any
from pathlib import Path


def calculate_execution_time(
    response_time_sec: float,
    opp_prev_stroke: Optional[str],
    shot_height_category: Optional[str]
) -> Dict[str, Any]:
    """
    Calculate execution time from response time, accounting for flight time.
    
    Execution time = Response time - Estimated flight time
    
    Args:
        response_time_sec: Total response time (includes flight + execution)
        opp_prev_stroke: Opponent's previous stroke type
        shot_height_category: Shot height category (high/medium/flat)
    
    Returns:
        Dictionary with execution_time, estimated_flight, and confidence
    """
    if pd.isna(response_time_sec) or response_time_sec <= 0:
        return {
            'execution_time': None,
            'estimated_flight': None,
            'confidence': None
        }
    
    # Estimate flight time based on shot height category
    # High shots have longer flight time, flat shots have shorter
    if shot_height_category == 'high':
        estimated_flight = 1.2  # ~1.2s for high shots
    elif shot_height_category == 'flat':
        estimated_flight = 0.5  # ~0.5s for flat shots
    elif shot_height_category == 'medium':
        estimated_flight = 0.85  # ~0.85s for medium shots
    else:
        # Default based on opponent stroke type
        if opp_prev_stroke:
            opp_lower = str(opp_prev_stroke).lower()
            if 'smash' in opp_lower or 'drive' in opp_lower:
                estimated_flight = 0.5  # Fast shots
            elif 'clear' in opp_lower or 'lift' in opp_lower:
                estimated_flight = 1.2  # High shots
            else:
                estimated_flight = 0.85  # Default medium
        else:
            estimated_flight = 0.85  # Default
    
    # Execution time = response time - flight time
    execution_time = max(0.1, response_time_sec - estimated_flight)
    
    # Confidence based on how well we can estimate flight time
    if shot_height_category in ['high', 'medium', 'flat']:
        confidence = 'high'
    elif opp_prev_stroke:
        confidence = 'medium'
    else:
        confidence = 'low'
    
    return {
        'execution_time': execution_time,
        'estimated_flight': estimated_flight,
        'confidence': confidence
    }


def calculate_player_baseline_execution(df: pd.DataFrame, player: str) -> Dict[str, float]:
    """
    Calculate baseline execution metrics for a player.
    
    Args:
        df: DataFrame with execution_time column
        player: Player identifier (P0 or P1)
    
    Returns:
        Dictionary with baseline metrics
    """
    player_df = df[df['Player'] == player].copy()
    
    # Filter valid execution times
    valid_exec = player_df['execution_time'].dropna()
    
    if len(valid_exec) == 0:
        return {
            'overall_baseline': 0.45,  # Default
            'median': 0.45,
            'mean': 0.45,
            'std': 0.15,
            'count': 0
        }
    
    valid_exec = valid_exec[valid_exec > 0]
    
    if len(valid_exec) == 0:
        return {
            'overall_baseline': 0.45,
            'median': 0.45,
            'mean': 0.45,
            'std': 0.15,
            'count': 0
        }
    
    median_exec = valid_exec.median()
    mean_exec = valid_exec.mean()
    std_exec = valid_exec.std() if len(valid_exec) > 1 else 0.15
    
    # Overall baseline is median (more robust to outliers)
    return {
        'overall_baseline': float(median_exec),
        'median': float(median_exec),
        'mean': float(mean_exec),
        'std': float(std_exec),
        'count': len(valid_exec)
    }


def validate_execution_with_effectiveness(
    execution_time: float,
    effectiveness: float,
    incoming_eff: Optional[float]
) -> Dict[str, Any]:
    """
    Validate execution time makes sense given effectiveness.
    
    Logic:
    - Fast execution with high effectiveness = good
    - Slow execution with low effectiveness = concerning
    - High incoming effectiveness should force slower execution
    
    Args:
        execution_time: Calculated execution time
        effectiveness: Current shot effectiveness
        incoming_eff: Incoming shot effectiveness
    
    Returns:
        Dictionary with validation results
    """
    if pd.isna(execution_time):
        return {
            'is_valid': None,
            'validation_score': None,
            'notes': 'No execution time'
        }
    
    validation_score = 0.0
    notes = []
    
    # Check 1: Fast execution should correlate with higher effectiveness
    if execution_time < 0.45:  # Fast execution
        if effectiveness > 60:
            validation_score += 1.0
            notes.append('Fast execution with high effectiveness')
        elif effectiveness < 40:
            validation_score -= 0.5
            notes.append('Fast execution but low effectiveness')
    
    # Check 2: Slow execution with high incoming effectiveness is expected
    if incoming_eff is not None and not pd.isna(incoming_eff):
        if incoming_eff > 70:  # High incoming pressure
            if execution_time > 0.55:  # Slower execution
                validation_score += 0.5
                notes.append('Appropriate slow execution under pressure')
            elif execution_time < 0.4:  # Too fast under pressure
                validation_score -= 0.5
                notes.append('Too fast execution under high pressure')
    
    # Check 3: Very slow execution with low effectiveness is concerning
    if execution_time > 0.65:
        if effectiveness < 40:
            validation_score -= 1.0
            notes.append('Slow execution with low effectiveness')
    
    # Normalize score
    is_valid = validation_score >= 0.0
    
    return {
        'is_valid': is_valid,
        'validation_score': validation_score,
        'notes': '; '.join(notes) if notes else 'Normal'
    }


def classify_tempo_control(
    curr_execution_time: float,
    prev_execution_time: float,
    curr_effectiveness: float,
    prev_effectiveness: float,
    curr_baseline: float,
    prev_baseline: float
) -> Dict[str, Any]:
    """
    Classify tempo control in an exchange between players.
    
    Args:
        curr_execution_time: Current player's execution time
        prev_execution_time: Previous player's execution time
        curr_effectiveness: Current player's shot effectiveness
        prev_effectiveness: Previous player's shot effectiveness
        curr_baseline: Current player's baseline execution time
        prev_baseline: Previous player's baseline execution time
    
    Returns:
        Dictionary with tempo control classification
    """
    # Calculate relative speeds
    curr_vs_baseline = curr_execution_time - curr_baseline
    prev_vs_baseline = prev_execution_time - prev_baseline
    
    # Speed difference
    speed_diff = prev_execution_time - curr_execution_time
    
    # Effectiveness difference
    eff_diff = curr_effectiveness - prev_effectiveness
    
    # Classify tempo control
    if speed_diff > 0.15:  # Current player significantly faster
        if curr_effectiveness > prev_effectiveness + 10:
            tempo_control = 'player_dominant'
            control_type = 'speed_and_quality'
        elif curr_effectiveness >= prev_effectiveness:
            tempo_control = 'player_dominant'
            control_type = 'speed'
        else:
            tempo_control = 'player_aggressive'
            control_type = 'speed_risk'
    elif speed_diff < -0.15:  # Current player significantly slower
        if curr_effectiveness > prev_effectiveness + 10:
            tempo_control = 'opponent_dominant'
            control_type = 'forced_slow'
        else:
            tempo_control = 'opponent_dominant'
            control_type = 'pressure'
    else:  # Similar speeds
        if curr_effectiveness > prev_effectiveness + 15:
            tempo_control = 'player_dominant'
            control_type = 'quality'
        elif prev_effectiveness > curr_effectiveness + 15:
            tempo_control = 'opponent_dominant'
            control_type = 'quality'
        else:
            tempo_control = 'neutral'
            control_type = 'balanced'
    
    return {
        'tempo_control': tempo_control,
        'control_type': control_type,
        'speed_difference': speed_diff,
        'effectiveness_difference': eff_diff,
        'curr_vs_baseline': curr_vs_baseline,
        'prev_vs_baseline': prev_vs_baseline
    }


def analyze_match_tempo(tempo_events_csv: str, effectiveness_csv: str) -> pd.DataFrame:
    """
    Complete tempo analysis pipeline
    Combines all metrics into unified framework
    """
    
    # Load data
    tempo_df = pd.read_csv(tempo_events_csv)
    eff_df = pd.read_csv(effectiveness_csv)
    
    # Merge on common columns - tempo_df already has effectiveness, but we need RallyWinner
    merge_cols = ['GameNumber', 'RallyNumber', 'StrokeNumber']
    
    # Select columns to merge from effectiveness CSV
    eff_cols_to_merge = ['RallyWinner']
    if 'quality_score' in eff_df.columns:
        eff_cols_to_merge.append('quality_score')
    if 'band' in eff_df.columns:
        eff_cols_to_merge.append('band')
    
    # Merge only the columns we need
    df = tempo_df.copy()
    if eff_cols_to_merge:
        eff_subset = eff_df[merge_cols + eff_cols_to_merge]
        df = df.merge(
            eff_subset,
            on=merge_cols,
            how='left'
        )
    
    # Ensure columns exist (with defaults if not merged)
    if 'RallyWinner' not in df.columns:
        df['RallyWinner'] = None
    if 'quality_score' not in df.columns:
        df['quality_score'] = None
    if 'band' not in df.columns:
        df['band'] = None
    
    # Calculate player baselines (will update after execution_time is calculated)
    # First pass: calculate execution times
    df['execution_metrics'] = df.apply(
        lambda row: calculate_execution_time(
            row.get('response_time_sec'),
            row.get('opp_prev_stroke'),
            row.get('shot_height_category')
        ) if pd.notna(row.get('response_time_sec')) else None,
        axis=1
    )
    
    # Unpack execution metrics
    df['execution_time'] = df['execution_metrics'].apply(
        lambda x: x['execution_time'] if x else None
    )
    df['estimated_flight'] = df['execution_metrics'].apply(
        lambda x: x['estimated_flight'] if x else None
    )
    df['execution_confidence'] = df['execution_metrics'].apply(
        lambda x: x['confidence'] if x else None
    )
    
    # Calculate player baselines
    p0_baseline = calculate_player_baseline_execution(df, 'P0')
    p1_baseline = calculate_player_baseline_execution(df, 'P1')
    
    # Add baseline to each row
    df['player_baseline'] = df['Player'].map({
        'P0': p0_baseline['overall_baseline'],
        'P1': p1_baseline['overall_baseline']
    })
    
    # Validate with effectiveness
    df['validation'] = df.apply(
        lambda row: validate_execution_with_effectiveness(
            row.get('execution_time'),
            row.get('effectiveness', 50),
            row.get('incoming_eff')
        ) if pd.notna(row.get('execution_time')) else None,
        axis=1
    )
    
    # Unpack validation
    df['validation_is_valid'] = df['validation'].apply(
        lambda x: x['is_valid'] if x else None
    )
    df['validation_score'] = df['validation'].apply(
        lambda x: x['validation_score'] if x else None
    )
    df['validation_notes'] = df['validation'].apply(
        lambda x: x['notes'] if x else None
    )
    
    # Calculate rally winners for tempo control
    # RallyWinner is already in df from the merge
    df['rally_winner'] = df.get('RallyWinner', None)
    
    # Calculate tempo control for each exchange
    tempo_controls = []
    
    for (game, rally), rally_df in df.groupby(['GameNumber', 'RallyNumber']):
        rally_df = rally_df.sort_values('StrokeNumber').reset_index(drop=True)
        
        for i in range(1, len(rally_df)):
            curr = rally_df.iloc[i]
            prev = rally_df.iloc[i-1]
            
            if curr['Player'] != prev['Player']:  # Exchange between players
                tempo_control = classify_tempo_control(
                    curr.get('execution_time', 0.5) or 0.5,
                    prev.get('execution_time', 0.5) or 0.5,
                    curr.get('effectiveness', 50) or 50,
                    prev.get('effectiveness', 50) or 50,
                    curr.get('player_baseline', 0.45) or 0.45,
                    prev.get('player_baseline', 0.45) or 0.45
                )
                
                tempo_controls.append({
                    'GameNumber': game,
                    'RallyNumber': rally,
                    'StrokeNumber': curr['StrokeNumber'],
                    **tempo_control
                })
    
    # Merge tempo control back
    if tempo_controls:
        tempo_control_df = pd.DataFrame(tempo_controls)
        df = df.merge(
            tempo_control_df,
            on=['GameNumber', 'RallyNumber', 'StrokeNumber'],
            how='left'
        )
    else:
        # Add empty columns if no tempo controls
        df['tempo_control'] = None
        df['control_type'] = None
        df['speed_difference'] = None
        df['effectiveness_difference'] = None
        df['curr_vs_baseline'] = None
        df['prev_vs_baseline'] = None
    
    # Clean up intermediate columns
    df = df.drop(columns=['execution_metrics', 'validation'], errors='ignore')
    
    return df


def validate_tempo_analysis(df: pd.DataFrame) -> dict:
    """
    Validate tempo analysis using effectiveness correlation
    """
    
    # Test 1: Fast execution should correlate with higher effectiveness
    fast_exec = df[(df['execution_time'] < 0.45) & (df['execution_time'].notna())]
    slow_exec = df[(df['execution_time'] > 0.65) & (df['execution_time'].notna())]
    
    fast_eff_mean = None
    if len(fast_exec) > 0 and 'effectiveness' in fast_exec.columns:
        fast_eff = fast_exec['effectiveness'].dropna()
        fast_eff_mean = fast_eff.mean() if len(fast_eff) > 0 else None
    
    slow_eff_mean = None
    if len(slow_exec) > 0 and 'effectiveness' in slow_exec.columns:
        slow_eff = slow_exec['effectiveness'].dropna()
        slow_eff_mean = slow_eff.mean() if len(slow_eff) > 0 else None
    
    # Test 2: High incoming effectiveness should force slower execution
    high_incoming = df[(df['incoming_eff'] > 70) & (df['incoming_eff'].notna())]
    low_incoming = df[(df['incoming_eff'] < 40) & (df['incoming_eff'].notna())]
    
    forced_slow = None
    if len(high_incoming) > 0:
        exec_times = high_incoming['execution_time'].dropna()
        forced_slow = exec_times.mean() if len(exec_times) > 0 else None
    
    opportunity_fast = None
    if len(low_incoming) > 0:
        exec_times = low_incoming['execution_time'].dropna()
        opportunity_fast = exec_times.mean() if len(exec_times) > 0 else None
    
    # Test 3: Tempo control should predict rally outcome
    player_dominant = df[df['tempo_control'] == 'player_dominant']
    player_win_rate = None
    if len(player_dominant) > 0 and 'rally_winner' in player_dominant.columns:
        # Check if player who had tempo control won the rally
        valid_rows = player_dominant[
            player_dominant['rally_winner'].notna() & 
            player_dominant['Player'].notna()
        ]
        if len(valid_rows) > 0:
            valid_rows = valid_rows.copy()
            valid_rows['player_won'] = (
                valid_rows['Player'] == valid_rows['rally_winner']
            )
            player_win_rate = valid_rows['player_won'].mean()
    
    return {
        'fast_exec_effectiveness': fast_eff_mean,
        'slow_exec_effectiveness': slow_eff_mean,
        'correlation_check': fast_eff_mean > slow_eff_mean if (fast_eff_mean is not None and slow_eff_mean is not None) else None,
        
        'forced_slow_exec': forced_slow,
        'opportunity_exec': opportunity_fast,
        'pressure_check': forced_slow > opportunity_fast if (forced_slow is not None and opportunity_fast is not None) else None,
        
        'tempo_control_win_rate': player_win_rate,
        'prediction_check': player_win_rate > 0.60 if player_win_rate is not None else None,
        
        'total_shots': len(df),
        'shots_with_execution_time': len(df[df['execution_time'].notna()]),
        'shots_with_tempo_control': len(df[df['tempo_control'].notna()])
    }


def main():
    """Main function to run the new tempo analysis"""
    
    # Input files from tara/devika/2 folder
    base_dir = Path('tara/devika/2')
    tempo_events_csv = base_dir / 'QRsUgVlibBU_detailed_tempo_events.csv'
    effectiveness_csv = base_dir / 'QRsUgVlibBU_detailed_effectiveness.csv'
    
    # Output file
    output_csv = base_dir / 'QRsUgVlibBU_tempo_analysis_new.csv'
    
    print(f"Loading tempo events from: {tempo_events_csv}")
    print(f"Loading effectiveness from: {effectiveness_csv}")
    
    # Run analysis
    print("\nRunning tempo analysis...")
    df = analyze_match_tempo(str(tempo_events_csv), str(effectiveness_csv))
    
    # Run validation
    print("\nValidating analysis...")
    validation_results = validate_tempo_analysis(df)
    
    # Print validation results
    print("\n=== Validation Results ===")
    for key, value in validation_results.items():
        print(f"{key}: {value}")
    
    # Save to CSV
    print(f"\nSaving results to: {output_csv}")
    df.to_csv(output_csv, index=False)
    
    print(f"\nAnalysis complete! Output saved to {output_csv}")
    print(f"Total rows: {len(df)}")
    print(f"Rows with execution_time: {len(df[df['execution_time'].notna()])}")
    print(f"Rows with tempo_control: {len(df[df['tempo_control'].notna()])}")


if __name__ == '__main__':
    main()

