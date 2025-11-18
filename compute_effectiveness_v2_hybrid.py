import pandas as pd
import numpy as np
from typing import Optional
try:
    from rules_loader import load_rules, Rules, load_shot_categories, load_triple_category_rules, classify_category
except Exception:
    load_rules = None
    Rules = None
    load_shot_categories = None
    load_triple_category_rules = None
    classify_category = None

def get_shot_score(shot_type):
    raw = str(shot_type).lower()
    shot = raw.replace('_cross', '')
    # Base score by type (direction-agnostic)
    if shot in ['forehand_smash', 'overhead_smash', 'forehand_dribble', 'backhand_dribble', 'forehand_nettap', 'backhand_nettap']:
        base = 1.0
    elif shot in ['forehand_halfsmash', 'overhead_halfsmash']:
        base = 0.8
    elif shot in ['forehand_netkeep', 'backhand_netkeep']:
        base = 0.7
    elif shot == 'flat_game':
        base = 0.65
    elif shot == 'forehand_drive':
        base = 0.6
    elif shot in ['forehand_pulldrop', 'backhand_pulldrop', 'backhand_drop']:
        base = 0.4
    elif shot in ['forehand_clear', 'overhead_clear']:
        base = 0.50
    elif shot in ['forehand_lift', 'backhand_lift']:
        base = 0.4
    elif shot in ['overhead_drop', 'forehand_drop']:
        base = 0.6
    elif shot == 'backhand_clear':
        base = 0.2
    elif shot in ['forehand_defense', 'backhand_defense']:
        base = 0.1
    elif 'serve' in shot:
        base = 0.0
    else:
        base = 0.5

    # Directional modifier for _cross variants (subtle)
    if raw.endswith('_cross'):
        if 'lift' in raw:
            base -= 0.10
        elif 'drop' in raw:
            base -= 0.05
        elif 'smash' in raw:
            base -= 0.03
    return max(0.0, min(1.0, base))

def get_quality_from_rules(shot_type, opponent_response, rules):
    """Get quality score from JSON rules for shot-response pair"""
    if rules is None:
        return 0.5
    
    try:
        atk = str(shot_type)
        rsp = str(opponent_response)
        rule = rules.lookup(atk, rsp)
        if rule is not None:
            return float(rule.get('quality_score', 0.5))
    except Exception:
        pass
    
    return 0.5

def get_transition_quality(shot_type, player_follow_up, shot_to_cat, triple_cat_rules):
    """Get quality score from triple category rules for shot transitions"""
    if (classify_category is None or shot_to_cat is None or triple_cat_rules is None):
        return 0.5
    
    try:
        start_cat = classify_category(str(shot_type), shot_to_cat)
        end_cat = classify_category(str(player_follow_up), shot_to_cat)
        entry = triple_cat_rules.get((start_cat, end_cat))
        if entry is not None:
            return float(entry.get('q_end', 0.5))
    except Exception:
        pass
    
    return 0.5

def calculate_shot_quality(shot_type, opponent_response, player_follow_up, rules, shot_to_cat, triple_cat_rules):
    """Calculate shot quality using JSON rules as primary source"""
    
    # 1. Get base quality from JSON rules (primary)
    base_quality = get_quality_from_rules(shot_type, opponent_response, rules)
    
    # 2. Get category transition quality
    transition_quality = get_transition_quality(shot_type, player_follow_up, shot_to_cat, triple_cat_rules)
    
    # 3. Blend quality scores
    final_quality = (0.6 * base_quality) + (0.4 * transition_quality)
    
    # 4. Apply quality modifiers to base shot score
    base_score = get_shot_score(shot_type)
    quality_adjusted_score = base_score * final_quality
    
    return quality_adjusted_score, final_quality

def calculate_last_shot_quality(last_shot_stroke, opponent_response_stroke, rules, shot_to_cat, triple_cat_rules):
    """Quality for last shot: no follow-up, neutral transition weight.
    Uses rules for last_shot vs opponent's previous stroke.
    """
    base_quality = get_quality_from_rules(last_shot_stroke, opponent_response_stroke, rules)
    transition_quality = 0.5  # neutral due to no follow-up
    final_quality = (0.6 * base_quality) + (0.4 * transition_quality)
    return final_quality

def get_next_opponent_shot(rally_segment, current_pos, current_player, exclude_serves=True):
    """Return (row, position) for next opponent shot after current_pos, optionally skipping serves."""
    for j in range(current_pos + 1, len(rally_segment)):
        nxt = rally_segment.iloc[j]
        if nxt['Player'] != current_player:
            if exclude_serves and bool(nxt.get('is_serve', False)):
                continue
            return nxt, j
    return None, None

def get_score_band(score):
    if score <= 0.15:
        return 1
    elif score <= 0.35:
        return 2
    elif score <= 0.55:
        return 3
    elif score <= 0.75:
        return 4
    else:
        return 5

def get_rally_weight(shot_position_in_rally):
    # Front-load early shots to value initiative creation
    if shot_position_in_rally <= 4:
        return 1.6
    elif shot_position_in_rally <= 8:
        return 1.3
    elif shot_position_in_rally <= 12:
        return 1.1
    else:
        return 1.0

def calculate_tactical_effectiveness(band_a, band_b, band_c, rally_weight):
    forcing_advantage = (band_a - band_b) * rally_weight
    recovery_advantage = (band_c - band_b) * rally_weight
    total_advantage = forcing_advantage + recovery_advantage
    probability = 50 + (total_advantage * 8)
    if band_a >= 4 and band_b >= 4 and band_c <= 2:
        probability = min(probability, 30)
    if band_a <= 2 and band_b >= 4 and band_c <= 2:
        probability = min(probability, 25)
    return max(0, min(100, round(probability)))

def calculate_effectiveness(quality_adjusted_score, opponent_response, player_follow_up, rally_weight):
    """Calculate effectiveness using quality-adjusted scores"""
    
    # Convert quality-adjusted scores to bands
    shot_band = get_score_band(quality_adjusted_score)
    response_band = get_score_band(opponent_response['quality_adjusted_score'])
    follow_up_band = get_score_band(player_follow_up['quality_adjusted_score'])
    
    # Calculate effectiveness using 3-shot sequence logic
    return calculate_tactical_effectiveness(shot_band, response_band, follow_up_band, rally_weight)

def label_from_effectiveness(eff):
    if eff >= 75:
        return 'Excellent', 'green'
    if eff >= 61:
        return 'Good', 'orange'
    if eff >= 50:
        return 'Neutral', 'yellow'
    if eff >= 35:
        return 'Poor', 'red'
    return 'Bad', 'darkred'

def is_explicit_ue(row):
    try:
        txts = [
            str(row.get('effectiveness_label', '')).lower(),
            str(row.get('reason', '')).lower(),
            str(row.get('Stroke', '')).lower(),
        ]
        return any(('unforced' in t) or ('error' in t) for t in txts)
    except Exception:
        return False

def detect_if_error(shot_row, rally_outcome):
    """
    Detect if a shot is an error (unforced or forced) based on rally outcome.
    Returns: (is_error: bool, kind: str['error'|'winner'])
    """
    try:
        shot_player = shot_row.get('Player')
        rally_winner = rally_outcome.get('winner') if isinstance(rally_outcome, dict) else None
        if rally_winner is None:
            return False, 'winner'
        if str(shot_player) != str(rally_winner):
            return True, 'error'
        return False, 'winner'
    except Exception:
        return False, 'winner'

def classify_error_forced_vs_unforced(fs_minus_1_stroke, error_stroke, fs_minus_1_quality_score, shot_to_cat=None):
    """
    Classify opponent error as 'FORCED' or 'UNFORCED'.
    Primary discriminator: FS-1 quality score.
    Secondary (tiebreak, for borderline quality): category hierarchy comparison.
    """
    try:
        q = 0.5 if fs_minus_1_quality_score is None else float(fs_minus_1_quality_score)
    except Exception:
        q = 0.5

    # Primary thresholds (tunable)
    if q >= 0.56:
        return 'FORCED'
    if q <= 0.55:
        return 'UNFORCED'

    # Borderline: use categories as tiebreaker when available
    if classify_category is None or shot_to_cat is None:
        # Conservative default when lacking category signal
        return 'UNFORCED'

    try:
        fs_category = classify_category(str(fs_minus_1_stroke), shot_to_cat)
    except Exception:
        fs_category = 'unknown'
    try:
        error_category = classify_category(str(error_stroke), shot_to_cat)
    except Exception:
        error_category = 'unknown'

    category_hierarchy = [
        'attacking_shots', 'pressure_shots', 'placement_shots', 'defensive_placement',
        'net_shots', 'reset_shots', 'defensive_shots'
    ]
    fs_rank = category_hierarchy.index(fs_category) if fs_category in category_hierarchy else 3
    err_rank = category_hierarchy.index(error_category) if error_category in category_hierarchy else 3
    if fs_rank < err_rank:
        return 'FORCED'
    return 'UNFORCED'

def calculate_effectiveness_from_quality(quality_adjusted_score):
    """
    Convert quality-adjusted score (0..1) to an effectiveness percentage using band mapping.
    """
    try:
        band = get_score_band(float(quality_adjusted_score))
    except Exception:
        band = 3
    band_to_effectiveness = {
        1: 20,
        2: 35,
        3: 50,
        4: 75,
        5: 90
    }
    return band_to_effectiveness.get(band, 50)

def classify_rally_ending_simple(rally_data, shot_index, rally_outcome, shot_to_cat=None):
    """
    Simple classification that updates effectiveness_label and reason
    """
    
    last_shot = rally_data.iloc[shot_index]
    last_shot_player = last_shot['Player']
    rally_winner = rally_outcome.get('winner')
    
    # Check if last shot player won the rally
    if last_shot_player == rally_winner:
        return ('Rally Winner', 'Won the rally')
    
    # Rally ended with an error
    if shot_index == 0:
        return ('Unforced Error', 'Unforced error')
    
    # Get the shot before the error (FS-1)
    previous_shot = rally_data.iloc[shot_index - 1]
    if bool(previous_shot.get('is_serve', False)):
        return ('Unforced Error', 'Unforced error')

    # 1) Prefer FS-1 effectiveness when available (i.e., when FS-1 had a follow-up path)
    try:
        fs_eff = previous_shot.get('effectiveness')
        if fs_eff is not None and np.isfinite(float(fs_eff)):
            if float(fs_eff) >= 61.0:
                return ('Forced Error', 'Forced error')
            else:
                return ('Unforced Error', 'Unforced error')
    except Exception:
        pass

    # 2) Fallback to intrinsic effectiveness derived from quality_adjusted_score
    try:
        qa = previous_shot.get('quality_adjusted_score')
        if qa is not None and np.isfinite(float(qa)):
            intrinsic_eff = calculate_effectiveness_from_quality(float(qa))
            if intrinsic_eff >= 61.0:
                return ('Forced Error', 'Forced error')
            else:
                return ('Unforced Error', 'Unforced error')
    except Exception:
        pass

    # 3) Final fallback: category hierarchy tiebreak
    if classify_category is None or shot_to_cat is None:
        return ('Unforced Error', 'Unforced error')
    try:
        fs_category = classify_category(str(previous_shot.get('Stroke')), shot_to_cat)
    except Exception:
        fs_category = 'unknown'
    try:
        error_category = classify_category(str(last_shot.get('Stroke')), shot_to_cat)
    except Exception:
        error_category = 'unknown'
    category_hierarchy = [
        'attacking_shots', 'pressure_shots', 'placement_shots',
        'net_shots', 'reset_shots', 'defensive_shots'
    ]
    fs_rank = category_hierarchy.index(fs_category) if fs_category in category_hierarchy else 3
    err_rank = category_hierarchy.index(error_category) if error_category in category_hierarchy else 3
    if fs_rank < err_rank:
        return ('Forced Error', 'Forced error')
    return ('Unforced Error', 'Unforced error')

def create_shot_timeline(df, target_player='P0', rules: Optional['Rules']=None, shot_to_cat=None, triple_cat_rules=None):
    df['is_serve'] = df['Stroke'].str.contains('serve', case=False, na=False)
    
    # Pre-calculate quality-adjusted scores for all shots
    df['base_score'] = df['Stroke'].apply(get_shot_score)
    df['quality_adjusted_score'] = df['base_score']  # Default fallback
    df['quality_score'] = np.nan  # Not yet calculated

    # Identify game column if present
    game_col = None
    for candidate in ['GameNumber', 'Game', 'Set', 'SetNumber', 'game_id', 'GameID']:
        if candidate in df.columns:
            game_col = candidate
            break

    # Prefer outcomes provided by the enhanced input CSV
    has_input_outcomes = ('RallyWinner' in df.columns) and ('RallyLoser' in df.columns)
    has_input_shot_flags = ('IsWinningShot' in df.columns) and ('IsLosingShot' in df.columns)

    def parse_bool(val):
        if isinstance(val, bool):
            return val
        try:
            s = str(val).strip().lower()
            return s in ('true', '1', 'yes', 'y', 't')
        except Exception:
            return False

    # Helper: compute rally outcomes (winner/loser) per game using provided rules
    def compute_rally_outcomes(frame):
        outcomes = {}
        # Prepare ordering of rallies within the game
        rally_ids_in_order = list(pd.unique(frame['RallyNumber']))
        rally_ids_in_order.sort()
        for idx, r_id in enumerate(rally_ids_in_order):
            rally_df = frame[frame['RallyNumber'] == r_id]
            if 'StrokeNumber' in rally_df.columns:
                rally_df = rally_df.sort_values('StrokeNumber')
            else:
                rally_df = rally_df.sort_index()
            last_row = rally_df.iloc[-1]
            # Non-last rally in game: winner = next rally's first shot player
            if idx < len(rally_ids_in_order) - 1:
                next_rally_id = rally_ids_in_order[idx + 1]
                next_rally_df = frame[frame['RallyNumber'] == next_rally_id].sort_index()
                next_server = str(next_rally_df.iloc[0]['Player'])
                winner = next_server
                # Determine loser as the other player participating in current rally
                players_in_rally = list(pd.unique(rally_df['Player']))
                if len(players_in_rally) == 2 and next_server in players_in_rally:
                    loser = players_in_rally[0] if players_in_rally[1] == next_server else players_in_rally[1]
                else:
                    loser = 'P0' if winner == 'P1' else ('P1' if winner == 'P0' else None)
            else:
                # Last rally of game: derive from final score at last shot
                winner = None
                loser = None
                if ('ScoreP0' in rally_df.columns) and ('ScoreP1' in rally_df.columns):
                    try:
                        p0 = float(last_row['ScoreP0'])
                        p1 = float(last_row['ScoreP1'])
                        if p0 > p1:
                            winner, loser = 'P0', 'P1'
                        elif p1 >= p0:
                            winner, loser = 'P1', 'P0'
                    except Exception:
                        pass
                # Fallback to last shot player if scores unavailable
                if winner is None:
                    winner = str(last_row['Player'])
                    players_in_rally = list(pd.unique(rally_df['Player']))
                    if len(players_in_rally) == 2 and winner in players_in_rally:
                        loser = players_in_rally[0] if players_in_rally[1] == winner else players_in_rally[1]
                    else:
                        loser = 'P0' if winner == 'P1' else ('P1' if winner == 'P0' else None)

            outcomes[r_id] = {'winner': winner, 'loser': loser}
        return outcomes

    # Build computed outcomes per game (or entire frame) as a fallback
    if game_col is not None:
        outcomes_by_game = {}
        for g_val, g_frame in df.groupby(game_col):
            outcomes_by_game[g_val] = compute_rally_outcomes(g_frame)
    else:
        outcomes_by_game = {None: compute_rally_outcomes(df)}

    timeline_data = []

    # Group by RallyNumber (scoped within game if available)
    if game_col is not None:
        group_iter = df.groupby([game_col, 'RallyNumber'])
    else:
        group_iter = [((None, rid), grp) for rid, grp in df.groupby('RallyNumber')]

    for group_key, rally in group_iter:
        if game_col is not None:
            game_val, rally_num = group_key
            # Create composite rally_id: GameNumber_RallyNumber
            rally_id = f"{game_val}_{rally_num}"
        else:
            game_val = None
            _, rally_num = group_key
            rally_id = str(rally_num)
        
        if 'StrokeNumber' in rally.columns:
            rally = rally.sort_values('StrokeNumber')
        else:
            rally = rally.sort_index()
        rally = rally.reset_index(drop=True)
        
        # Identify rally boundaries based on StrokeNumber resets within each GameNumber-RallyNumber group
        rally_boundaries = []
        if 'StrokeNumber' in rally.columns:
            for i in range(len(rally)):
                if i == 0 or rally.iloc[i]['StrokeNumber'] == 1:
                    rally_boundaries.append(i)
        else:
            rally_boundaries = [0]
        
        # Process each rally segment separately
        for segment_idx in range(len(rally_boundaries)):
            start_idx = rally_boundaries[segment_idx]
            end_idx = rally_boundaries[segment_idx + 1] if segment_idx + 1 < len(rally_boundaries) else len(rally)
            
            rally_segment = rally.iloc[start_idx:end_idx].copy()
            rally_segment = rally_segment.reset_index(drop=True)
            rally_segment['rally_position'] = range(1, len(rally_segment) + 1)
            
            # Create unique rally ID for this segment: GameNumber_RallyNumber_SegmentNumber
            segment_rally_id = f"{rally_id}_seg{segment_idx + 1}"
        
            # Calculate quality-adjusted scores for all shots in this rally segment
            for i, shot in rally_segment.iterrows():
                if i < len(rally_segment) - 1:  # Not the last shot
                    opponent_response, opponent_index = get_next_opponent_shot(rally_segment, i, shot['Player'], exclude_serves=True)
                    if opponent_response is not None:
                        # Look for player follow-up after opponent response
                        player_follow_up = None
                        for k in range(opponent_index + 1, len(rally_segment)):
                            cand = rally_segment.iloc[k]
                            if cand['Player'] == shot['Player'] and (not bool(cand.get('is_serve', False))):
                                player_follow_up = cand
                                break
                        if player_follow_up is not None:
                            quality_adjusted_score, quality_score = calculate_shot_quality(
                                shot['Stroke'],
                                opponent_response['Stroke'],
                                player_follow_up['Stroke'],
                                rules, shot_to_cat, triple_cat_rules
                            )
                            rally_segment.loc[i, 'quality_adjusted_score'] = quality_adjusted_score
                            rally_segment.loc[i, 'quality_score'] = quality_score
                        else:
                            # FS-1 case: opponent ended rally immediately; compute quality with neutral transition
                            if opponent_index == len(rally_segment) - 1:
                                base_quality = get_quality_from_rules(
                                    shot['Stroke'],
                                    opponent_response['Stroke'],
                                    rules
                                )
                                transition_quality = 0.5
                                final_quality = (0.6 * base_quality) + (0.4 * transition_quality)
                                quality_adjusted_score = shot['base_score'] * final_quality
                                rally_segment.loc[i, 'quality_adjusted_score'] = quality_adjusted_score
                                rally_segment.loc[i, 'quality_score'] = final_quality
                                # If opponent's last shot is an error and classified UNFORCED, override FS-1 effectiveness later
                            # If not FS-1, leave defaults (no follow-up inside rally)

            # Calculate quality for last shot (no follow-up) before band calculation
            if len(rally_segment) >= 2:
                last_idx = len(rally_segment) - 1
                last_shot = rally_segment.iloc[last_idx]
                second_to_last = rally_segment.iloc[last_idx - 1]
                if not bool(last_shot.get('is_serve', False)):
                    # Opponent response to second-to-last shot is the last shot itself (by definition)
                    # But for quality of last shot, we need opponent's previous stroke to last shot
                    # Find opponent shot immediately before last shot
                    prev_opponent = None
                    for j in range(last_idx - 1, -1, -1):
                        cand = rally_segment.iloc[j]
                        if cand['Player'] != last_shot['Player'] and (not bool(cand.get('is_serve', False))):
                            prev_opponent = cand
                            break
                    if prev_opponent is not None:
                        q_last = calculate_last_shot_quality(
                            last_shot['Stroke'], prev_opponent['Stroke'], rules, shot_to_cat, triple_cat_rules
                        )
                        rally_segment.loc[last_idx, 'quality_adjusted_score'] = last_shot['base_score'] * q_last
                        rally_segment.loc[last_idx, 'quality_score'] = q_last
            
            # Now compute bands including last-shot updated quality
            rally_segment['band'] = rally_segment['quality_adjusted_score'].apply(get_score_band)
            last_shot_index = len(rally_segment) - 1
            rally_outputs = []  # collect shot_data per rally to allow last-shot adjustments
        
            # Determine rally outcome: prefer input CSV columns, fallback to computed
            rally_outcome = {'winner': None, 'loser': None}
            if has_input_outcomes:
                try:
                    rw = rally_segment.iloc[0].get('RallyWinner')
                    rl = rally_segment.iloc[0].get('RallyLoser')
                    rw = None if pd.isna(rw) else str(rw)
                    rl = None if pd.isna(rl) else str(rl)
                    if rw is not None and rl is not None:
                        rally_outcome = {'winner': rw, 'loser': rl}
                    else:
                        rally_outcome = outcomes_by_game.get(game_val, {}).get(rally_num, {'winner': None, 'loser': None})
                except Exception:
                    rally_outcome = outcomes_by_game.get(game_val, {}).get(rally_num, {'winner': None, 'loser': None})
            else:
                # For segmented rallies, determine outcome based on the next rally segment
                if segment_idx + 1 < len(rally_boundaries):
                    # There's a next segment - winner is the first player of next segment
                    next_start_idx = rally_boundaries[segment_idx + 1]
                    next_segment = rally.iloc[next_start_idx:next_start_idx + 1]
                    if len(next_segment) > 0:
                        winner = str(next_segment.iloc[0]['Player'])
                        # Loser is the other player in current segment
                        players_in_segment = list(pd.unique(rally_segment['Player']))
                        loser = players_in_segment[0] if players_in_segment[1] == winner else players_in_segment[1] if len(players_in_segment) == 2 else None
                        rally_outcome = {'winner': winner, 'loser': loser}
                    else:
                        rally_outcome = {'winner': None, 'loser': None}
                else:
                    # This is the last segment - use computed outcomes
                    rally_outcome = outcomes_by_game.get(game_val, {}).get(rally_num, {'winner': None, 'loser': None})
            
            # Pre-calculate effectiveness for non-last shots to avoid duplication
            effectiveness_cache = {}
            for i2 in range(len(rally_segment) - 1):
                shot2 = rally_segment.iloc[i2]
                if bool(shot2.get('is_serve', False)):
                    effectiveness_cache[i2] = None
                    continue
                opp2, opp_idx2 = get_next_opponent_shot(rally_segment, i2, shot2['Player'], exclude_serves=True)
                if opp2 is None:
                    effectiveness_cache[i2] = None
                    continue
                # Find follow-up
                follow2 = None
                for k in range(opp_idx2 + 1, len(rally_segment)):
                    cand = rally_segment.iloc[k]
                    if cand['Player'] == shot2['Player'] and (not bool(cand.get('is_serve', False))):
                        follow2 = cand
                        break
                rally_weight2 = get_rally_weight(shot2['rally_position'])
                if follow2 is None:
                    # FS-1 case if opponent ended rally immediately
                    if opp_idx2 == len(rally_segment) - 1:
                        # Determine if opponent's final shot was error or winner
                        is_err, _ = detect_if_error(rally_segment.iloc[opp_idx2], rally_outcome)
                        if is_err:
                            # Classify forced vs unforced using FS-1 quality
                            fs_q2 = shot2.get('quality_score', 0.5)
                            try:
                                if pd.isna(fs_q2):
                                    fs_q2 = 0.5
                            except Exception:
                                fs_q2 = 0.5
                            err_cls2 = classify_error_forced_vs_unforced(
                                shot2.get('Stroke'), opp2.get('Stroke'), fs_q2, shot_to_cat
                            )
                            if err_cls2 == 'FORCED':
                                base_eff = calculate_tactical_effectiveness(
                                    shot2['band'], opp2['band'], opp2['band'], rally_weight2
                                )
                                effectiveness_cache[i2] = max(0, min(100, base_eff))
                            else:
                                fs1_q_adj = shot2.get('quality_adjusted_score', shot2.get('base_score', 0.5) * (fs_q2 if fs_q2 is not None else 0.5))
                                effectiveness_cache[i2] = calculate_effectiveness_from_quality(fs1_q_adj)
                        else:
                            # Opponent won on next shot: penalize via tactical relationship
                            base_eff = calculate_tactical_effectiveness(
                                shot2['band'], opp2['band'], opp2['band'], rally_weight2
                            )
                            effectiveness_cache[i2] = max(0, min(100, base_eff))
                    else:
                        effectiveness_cache[i2] = None
                else:
                    eff2 = calculate_effectiveness(
                        shot2['quality_adjusted_score'], opp2, follow2, rally_weight2
                    )
                    effectiveness_cache[i2] = eff2

            for i, shot in rally_segment.iterrows():
                shot_data = {**shot.to_dict()}  # Start with all original columns
                # Build shot data and prefer IsWinningShot/IsLosingShot from input
                shot_data.update({
                    'base_score': shot['base_score'],
                    'quality_adjusted_score': shot['quality_adjusted_score'],
                    'quality_score': shot['quality_score'],
                    'band': shot['band'],
                    'rally_id': segment_rally_id,
                    'rally_position': int(shot['rally_position']),
                    'is_serve': bool(shot['is_serve']),
                    'rally_winner': rally_outcome['winner'],
                    'rally_loser': rally_outcome['loser']
                })

                # Prefer shot-level flags from input; fallback to positional logic
                if has_input_shot_flags:
                    try:
                        shot_data['is_winning_shot'] = parse_bool(shot.get('IsWinningShot'))
                        shot_data['is_losing_shot'] = parse_bool(shot.get('IsLosingShot'))
                    except Exception:
                        shot_data['is_winning_shot'] = bool((i == last_shot_index) and (str(shot['Player']) == str(rally_outcome['winner'])))
                        shot_data['is_losing_shot'] = bool((i == last_shot_index) and (str(shot['Player']) == str(rally_outcome['loser'])))
                else:
                    shot_data['is_winning_shot'] = bool((i == last_shot_index) and (str(shot['Player']) == str(rally_outcome['winner'])))
                    shot_data['is_losing_shot'] = bool((i == last_shot_index) and (str(shot['Player']) == str(rally_outcome['loser'])))
                
                if shot['is_serve']:
                    # Serve-specific overrides per requirements
                    # 1) If the serve is an error -> mark red
                    serve_error = False
                    # Detect explicit serve fault keywords in Stroke
                    try:
                        stroke_text = str(shot['Stroke']).lower()
                        if ('fault' in stroke_text) or ('serve_error' in stroke_text) or ('service_fault' in stroke_text):
                            serve_error = True
                    except Exception:
                        pass
                    if 'reason' in rally_segment.columns:
                        try:
                            serve_error = isinstance(shot['reason'], str) and ('error' in shot['reason'].lower())
                        except Exception:
                            serve_error = False
                    if not serve_error and 'effectiveness_label' in rally_segment.columns:
                        try:
                            lbl = shot.get('effectiveness_label')
                            serve_error = isinstance(lbl, str) and ('error' in lbl.lower())
                        except Exception:
                            pass

                    if serve_error:
                        shot_data.update({
                            'color': 'red',
                            'effectiveness': None,
                            'effectiveness_label': 'Serve Error',
                            'reason': 'Serve fault/error'
                        })
                        rally_outputs.append(shot_data)
                        continue

                    # 2) If the serve leads to a winner in the same shot or the next shot
                    # Honor Step-7: do not score serve effectiveness for rallies of length <= 2
                    segment_len = len(rally_segment)
                    # Same shot (ace): serve is last shot of rally and no opponent response
                    if i == last_shot_index:
                        if segment_len <= 2:
                            shot_data.update({
                                'color': 'gray',
                                'effectiveness': None,
                                'effectiveness_label': 'Serve',
                                'reason': 'Serve - not analyzed (≤2-shot rally)'
                            })
                            # Reflect no effectiveness scoring
                            rally_outputs.append(shot_data)
                            continue
                        shot_data.update({
                            'color': 'green',
                            'effectiveness': 100,
                            'effectiveness_label': 'Ace Serve',
                            'reason': 'Won the rally on serve'
                        })
                        # Reflect in segment so downstream logic can see serve effectiveness
                        rally_segment.loc[i, 'effectiveness'] = 100
                        rally_outputs.append(shot_data)
                        continue

                    # Next shot winner: server's immediate follow-up ends the rally
                    opponent_shots = rally_segment[(rally_segment.index > i) & (rally_segment['Player'] != shot['Player']) & (~rally_segment['is_serve'])]
                    if len(opponent_shots) > 0:
                        opponent_response = opponent_shots.iloc[0]
                        opponent_index = rally_segment[rally_segment.index == opponent_response.name].index[0]
                        # If opponent's return ends the rally and server is winner, credit the serve
                        if opponent_index == last_shot_index and rally_outcome.get('winner') == shot['Player']:
                            if segment_len <= 2:
                                shot_data.update({
                                    'color': 'gray',
                                    'effectiveness': None,
                                    'effectiveness_label': 'Serve',
                                    'reason': 'Serve - not analyzed (≤2-shot rally)'
                                })
                                rally_outputs.append(shot_data)
                                continue
                            shot_data.update({
                                'color': 'green',
                                'effectiveness': 100,
                                'effectiveness_label': 'Serve Led to Error',
                                'reason': f"Serve → {opponent_response['Stroke']} (opponent error on return)"
                            })
                            # Reflect in segment so FS-1 classification (final shot) can consider serve effectiveness
                            rally_segment.loc[i, 'effectiveness'] = 100
                            rally_outputs.append(shot_data)
                            continue
                        server_follow_up = rally_segment[(rally_segment.index > opponent_index) & (rally_segment['Player'] == shot['Player']) & (~rally_segment['is_serve'])]
                        if len(server_follow_up) > 0:
                            server_follow_up = server_follow_up.iloc[0]
                            server_follow_up_index = rally_segment[rally_segment.index == server_follow_up.name].index[0]
                            if server_follow_up_index == last_shot_index:
                                if segment_len <= 2:
                                    shot_data.update({
                                        'color': 'gray',
                                        'effectiveness': None,
                                        'effectiveness_label': 'Serve',
                                        'reason': 'Serve - not analyzed (≤2-shot rally)'
                                    })
                                    rally_outputs.append(shot_data)
                                    continue
                                shot_data.update({
                                    'color': 'green',
                                    'effectiveness': 100,
                                    'effectiveness_label': 'Serve Led to Winner',
                                    'reason': f"Serve → {opponent_response['Stroke']} → Winner ({server_follow_up['Stroke']})"
                                })
                                # Reflect in segment for completeness
                                rally_segment.loc[i, 'effectiveness'] = 100
                                rally_outputs.append(shot_data)
                                continue

                    # Default serve rendering if no override matched
                    shot_data.update({
                        'color': 'gray',
                        'effectiveness': None,
                        'effectiveness_label': 'Serve',
                        'reason': 'Serve - not analyzed'
                    })
                elif i == last_shot_index:
                    # This is the final shot - classify how rally ended
                    # First, calculate effectiveness for FS-1 if it exists
                    if i > 0:
                        fs_minus_1 = rally_segment.iloc[i - 1]
                        if 'effectiveness' not in fs_minus_1 or pd.isna(fs_minus_1['effectiveness']):
                            # Calculate effectiveness for FS-1
                            opponent_shots = rally_segment[(rally_segment.index > i - 1) & (rally_segment['Player'] != fs_minus_1['Player']) & (~rally_segment['is_serve'])]
                            if len(opponent_shots) > 0:
                                opponent_response = opponent_shots.iloc[0]
                                player_follow_up = rally_segment[(rally_segment.index > opponent_shots.index[0]) & (rally_segment['Player'] == fs_minus_1['Player']) & (~rally_segment['is_serve'])]
                                if len(player_follow_up) > 0:
                                    player_follow_up = player_follow_up.iloc[0]
                                    rally_weight = get_rally_weight(fs_minus_1['rally_position'])
                                    base_eff = calculate_tactical_effectiveness(
                                        fs_minus_1['band'],
                                        opponent_response['band'],
                                        player_follow_up['band'],
                                        rally_weight
                                    )
                                    effectiveness = max(0, min(100, base_eff))
                                    rally_segment.loc[i - 1, 'effectiveness'] = effectiveness
                                else:
                                    # No follow-up exists (opponent ended rally). Decide based on error type.
                                    rally_weight = get_rally_weight(fs_minus_1['rally_position'])
                                    is_err, _ = detect_if_error(rally_segment.iloc[i], rally_outcome)
                                    if is_err:
                                        # Classify forced vs unforced using FS-1 quality
                                        fs_q = fs_minus_1.get('quality_score', 0.5)
                                        try:
                                            if pd.isna(fs_q):
                                                fs_q = 0.5
                                        except Exception:
                                            fs_q = 0.5
                                        err_class = classify_error_forced_vs_unforced(
                                            fs_minus_1.get('Stroke'), opponent_response.get('Stroke'), fs_q, shot_to_cat
                                        )
                                        if err_class == 'FORCED':
                                            base_eff = calculate_tactical_effectiveness(
                                                fs_minus_1['band'],
                                                opponent_response['band'],
                                                opponent_response['band'],
                                                rally_weight
                                            )
                                            effectiveness = max(0, min(100, base_eff))
                                            rally_segment.loc[i - 1, 'effectiveness'] = effectiveness
                                        else:
                                            # UNFORCED: use intrinsic FS-1 quality only
                                            fs1_quality_adj = fs_minus_1.get('quality_adjusted_score', fs_minus_1.get('base_score', 0.5) * (fs_q if fs_q is not None else 0.5))
                                            intrinsic_eff = calculate_effectiveness_from_quality(fs1_quality_adj)
                                            rally_segment.loc[i - 1, 'effectiveness'] = intrinsic_eff
                                    else:
                                        # Opponent winner: penalize via FS-1 formula (optionally small bias later)
                                        base_eff = calculate_tactical_effectiveness(
                                            fs_minus_1['band'],
                                            opponent_response['band'],
                                            opponent_response['band'],
                                            rally_weight
                                        )
                                        effectiveness = max(0, min(100, base_eff))
                                        rally_segment.loc[i - 1, 'effectiveness'] = effectiveness
                    
                    ending_label, ending_reason = classify_rally_ending_simple(rally_segment, i, rally_outcome, shot_to_cat)
                    
                    # Determine color based on ending type
                    if ending_label == 'Rally Winner':
                        color = 'green'
                        effectiveness = 100
                    elif ending_label == 'Forced Error':
                        color = 'green'
                        # Keep FS-1 effectiveness already computed; final shot itself has no effectiveness
                        effectiveness = None
                    else:  # Unforced Error
                        color = 'red'
                        effectiveness = None
                    
                    shot_data.update({
                        'color': color,
                        'effectiveness': effectiveness,
                        'effectiveness_label': ending_label,
                        'reason': ending_reason
                    })
                else:
                    opponent_response = None
                    player_follow_up = []
                    opponent_shots = rally_segment[(rally_segment.index > i) & (rally_segment['Player'] != shot['Player']) & (~rally_segment['is_serve'])]
                    if len(opponent_shots) == 0:
                        shot_data.update({
                            'color': 'gray',
                            'effectiveness': None,
                            'effectiveness_label': 'Incomplete',
                            'reason': 'No opponent response'
                        })
                    else:
                        opponent_response, opponent_index = get_next_opponent_shot(rally_segment, i, shot['Player'], exclude_serves=True)
                        player_follow_up = []
                        if opponent_response is not None:
                            for k in range(opponent_index + 1, len(rally_segment)):
                                cand = rally_segment.iloc[k]
                                if cand['Player'] == shot['Player'] and (not bool(cand.get('is_serve', False))):
                                    player_follow_up = [cand]
                                    break
                    # Use pre-calculated effectiveness if available (covers both follow-up and FS-1)
                    effectiveness = effectiveness_cache.get(i)
                    if effectiveness is not None:
                        lbl, clr = label_from_effectiveness(effectiveness)
                        # Compose reason based on whether we detected a follow-up
                        if opponent_response is not None:
                            if len(player_follow_up) > 0:
                                follow_stroke = player_follow_up[0]['Stroke']
                                reason_text = f"{shot['Stroke']} -> {opponent_response['Stroke']} -> {follow_stroke}"
                            else:
                                reason_text = f"{shot['Stroke']} -> {opponent_response['Stroke']} -> [next shot]"
                        else:
                            reason_text = 'No opponent response'
                        shot_data.update({
                            'color': clr,
                            'effectiveness': effectiveness,
                            'effectiveness_label': f"{lbl} ({effectiveness}%)",
                            'reason': reason_text
                        })
                    else:
                        shot_data.update({
                            'color': 'gray',
                            'effectiveness': None,
                            'effectiveness_label': 'Incomplete',
                            'reason': 'No follow-up shot'
                        })
                    
            
                rally_outputs.append(shot_data)
            
            timeline_data.extend(rally_outputs)
    return timeline_data

if __name__ == '__main__':
    import sys
    import os
    # Flags
    debug_flag = False
    argv = []
    for a in sys.argv[1:]:
        if a.strip().lower() == '--debug':
            debug_flag = True
        else:
            argv.append(a)
    # Allow running with only input.csv by deriving the standard output name
    if len(argv) < 1 or len(argv) > 6:
        print('Usage: python compute_effectiveness_v2_hybrid.py input.csv [output.csv] [target_player] [rules_json] [shot_categories_json] [triple_category_rules_json] [--debug]')
        sys.exit(1)
    input_csv = argv[0]
    # Derive standard output path: *_detailed_effectiveness.csv next to input
    in_dir = os.path.dirname(input_csv)
    in_base = os.path.basename(input_csv)
    if in_base.endswith('_detailed.csv'):
        derived_name = in_base[:-len('_detailed.csv')] + '_detailed_effectiveness.csv'
    elif in_base.endswith('.csv'):
        derived_name = os.path.splitext(in_base)[0] + '_detailed_effectiveness.csv'
    else:
        derived_name = in_base + '_detailed_effectiveness.csv'
    derived_output = os.path.join(in_dir, derived_name) if in_dir else derived_name
    # If an explicit output was passed, still normalize to the standard name
    output_csv = derived_output
    # Positional args shift since output is optional now
    arg_offset = 2 if len(argv) >= 2 else 1
    target_player = argv[arg_offset - 1] if len(argv) >= arg_offset else 'P0'
    rules_path = argv[arg_offset] if len(argv) >= (arg_offset + 1) else None
    shot_cats_path = argv[arg_offset + 1] if len(argv) >= (arg_offset + 2) else None
    triple_cat_path = argv[arg_offset + 2] if len(argv) >= (arg_offset + 3) else None
    rules = None
    if rules_path and load_rules is not None:
        try:
            rules = load_rules(rules_path)
        except Exception:
            rules = None
    shot_to_cat = None
    if shot_cats_path and load_shot_categories is not None:
        try:
            shot_to_cat = load_shot_categories(shot_cats_path)
        except Exception:
            shot_to_cat = None
    triple_cat_rules = None
    if triple_cat_path and load_triple_category_rules is not None:
        try:
            triple_cat_rules = load_triple_category_rules(triple_cat_path)
        except Exception:
            triple_cat_rules = None
    df = pd.read_csv(input_csv)
    timeline_data = create_shot_timeline(df, target_player=target_player, rules=rules, shot_to_cat=shot_to_cat, triple_cat_rules=triple_cat_rules)
    out_df = pd.DataFrame(timeline_data)
    # Prune redundant columns, always keeping rally_id; retain internal calc cols only in debug mode
    redundant_cols = [
        'Frame', 'Phase', 'CrucialReason', 'ScoreDiff', 'StreakP0', 'StreakP1', 'PointsToInterval',
        'PointsToGame', 'LeadStatus', 'LeadMagnitude', 'rally_position', 'rally_winner', 'rally_loser',
        'is_winning_shot', 'is_losing_shot'
    ]
    internal_calc_cols = ['base_score', 'quality_adjusted_score', 'quality_score']
    cols_to_drop = list(redundant_cols)
    if not debug_flag:
        cols_to_drop += internal_calc_cols
    # Never drop rally_id
    cols_to_drop = [c for c in cols_to_drop if c != 'rally_id']
    existing = [c for c in cols_to_drop if c in out_df.columns]
    if existing:
        out_df = out_df.drop(columns=existing)
    out_df.to_csv(output_csv, index=False)
    print(f'Output written to {output_csv}')
