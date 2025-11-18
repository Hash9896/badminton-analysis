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
    if shot in ['forehand_smash', 'overhead_smash', 'forehand_dribble', 'backhand_dribble']:
        base = 1.0
    elif shot in ['forehand_halfsmash', 'overhead_halfsmash', 'forehand_netkeep', 'backhand_netkeep']:
        base = 0.7
    elif shot == 'flat_game':
        base = 0.65
    elif shot == 'forehand_drive':
        base = 0.6
    elif shot == 'forehand_pulldrop':
        base = 0.5
    elif shot in ['forehand_clear', 'overhead_clear']:
        base = 0.45
    elif shot in ['forehand_lift', 'backhand_lift']:
        base = 0.4
    elif shot in ['backhand_drop', 'backhand_pulldrop', 'overhead_drop', 'forehand_drop']:
        base = 0.3
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

def create_shot_timeline(df, target_player='P0', rules: Optional['Rules']=None, shot_to_cat=None, triple_cat_rules=None):
    df['is_serve'] = df['Stroke'].str.contains('serve', case=False, na=False)
    df['score'] = df['Stroke'].apply(get_shot_score)

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
        rally['rally_position'] = range(1, len(rally) + 1)
        rally['band'] = rally['score'].apply(get_score_band)
        last_shot_index = len(rally) - 1
        rally_outputs = []  # collect shot_data per rally to allow last-shot adjustments
        # Determine rally outcome: prefer input CSV columns, fallback to computed
        rally_outcome = {'winner': None, 'loser': None}
        if has_input_outcomes:
            try:
                rw = rally.iloc[0].get('RallyWinner')
                rl = rally.iloc[0].get('RallyLoser')
                rw = None if pd.isna(rw) else str(rw)
                rl = None if pd.isna(rl) else str(rl)
                if rw is not None and rl is not None:
                    rally_outcome = {'winner': rw, 'loser': rl}
                else:
                    rally_outcome = outcomes_by_game.get(game_val, {}).get(rally_num, {'winner': None, 'loser': None})
            except Exception:
                rally_outcome = outcomes_by_game.get(game_val, {}).get(rally_num, {'winner': None, 'loser': None})
        else:
            # Use computed outcomes when input columns not present
            rally_outcome = outcomes_by_game.get(game_val, {}).get(rally_num, {'winner': None, 'loser': None})
        for i, shot in rally.iterrows():
            shot_data = {**shot.to_dict()}  # Start with all original columns
            # Build shot data and prefer IsWinningShot/IsLosingShot from input
            shot_data.update({
                'score': shot['score'],
                'band': shot['band'],
                'rally_id': rally_id,
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
                if 'reason' in rally.columns:
                    try:
                        serve_error = isinstance(shot['reason'], str) and ('error' in shot['reason'].lower())
                    except Exception:
                        serve_error = False
                if not serve_error and 'effectiveness_label' in rally.columns:
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
                # Same shot (ace): serve is last shot of rally and no opponent response
                if i == last_shot_index:
                    shot_data.update({
                        'color': 'green',
                        'effectiveness': 100,
                        'effectiveness_label': 'Ace Serve',
                        'reason': 'Won the rally on serve'
                    })
                    rally_outputs.append(shot_data)
                    continue

                # Next shot winner: server's immediate follow-up ends the rally
                opponent_shots = rally[(rally.index > i) & (rally['Player'] != shot['Player']) & (~rally['is_serve'])]
                if len(opponent_shots) > 0:
                    opponent_response = opponent_shots.iloc[0]
                    opponent_index = rally[rally.index == opponent_response.name].index[0]
                    # If opponent's return ends the rally and server is winner, credit the serve
                    if opponent_index == last_shot_index and rally_outcome.get('winner') == shot['Player']:
                        shot_data.update({
                            'color': 'green',
                            'effectiveness': 100,
                            'effectiveness_label': 'Serve Led to Error',
                            'reason': f"Serve → {opponent_response['Stroke']} (opponent error on return)"
                        })
                        rally_outputs.append(shot_data)
                        continue
                    server_follow_up = rally[(rally.index > opponent_index) & (rally['Player'] == shot['Player']) & (~rally['is_serve'])]
                    if len(server_follow_up) > 0:
                        server_follow_up = server_follow_up.iloc[0]
                        server_follow_up_index = rally[rally.index == server_follow_up.name].index[0]
                        if server_follow_up_index == last_shot_index:
                            shot_data.update({
                                'color': 'green',
                                'effectiveness': 100,
                                'effectiveness_label': 'Serve Led to Winner',
                                'reason': f"Serve → {opponent_response['Stroke']} → Winner ({server_follow_up['Stroke']})"
                            })
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
                shot_data.update({
                    'color': 'green',
                    'effectiveness': 100,
                    'effectiveness_label': 'Rally Winner',
                    'reason': 'Won the rally'
                })
            else:
                opponent_shots = rally[(rally.index > i) & (rally['Player'] != shot['Player']) & (~rally['is_serve'])]
                if len(opponent_shots) == 0:
                    shot_data.update({
                        'color': 'gray',
                        'effectiveness': None,
                        'effectiveness_label': 'Incomplete',
                        'reason': 'No opponent response'
                    })
                else:
                    opponent_response = opponent_shots.iloc[0]
                    opponent_index = rally[rally.index == opponent_response.name].index[0]
                    player_follow_up = rally[(rally.index > opponent_index) & (rally['Player'] == shot['Player']) & (~rally['is_serve'])]
                    if len(player_follow_up) == 0:
                        # If opponent immediately ends the rally, score and penalize this shot
                        if opponent_index == last_shot_index:
                            rally_weight = get_rally_weight(shot['rally_position'])
                            base_eff = calculate_tactical_effectiveness(
                                shot['band'],
                                opponent_response['band'],
                                opponent_response['band'],
                                rally_weight
                            )
                            effectiveness = max(0, min(100, base_eff - 15))
                            lbl, clr = label_from_effectiveness(effectiveness)
                            shot_data.update({
                                'color': clr,
                                'effectiveness': effectiveness,
                                'effectiveness_label': f"{lbl} ({effectiveness}%)",
                                'reason': f"{shot['Stroke']} -> {opponent_response['Stroke']} (opponent ended rally)"
                            })
                        else:
                            shot_data.update({
                                'color': 'gray',
                                'effectiveness': None,
                                'effectiveness_label': 'Incomplete',
                                'reason': 'No follow-up shot'
                            })
                    else:
                        player_follow_up = player_follow_up.iloc[0]
                        rally_weight = get_rally_weight(shot['rally_position'])
                        base_effectiveness = calculate_tactical_effectiveness(
                            shot['band'],
                            opponent_response['band'],
                            player_follow_up['band'],
                            rally_weight
                        )
                        # Apply dynamic quality score from rules (pair-based)
                        quality_score = 0.5
                        if rules is not None:
                            try:
                                atk = str(shot['Stroke'])
                                rsp = str(opponent_response['Stroke'])
                                rule = rules.lookup(atk, rsp)
                                if rule is not None:
                                    quality_score = float(rule.get('quality_score', 0.5))
                            except Exception:
                                quality_score = 0.5
                        # Compute end-category quality (q_end) based on immediate next own shot category
                        q_end = 0.5
                        if classify_category is not None and shot_to_cat is not None and triple_cat_rules is not None:
                            try:
                                start_cat = classify_category(str(shot['Stroke']), shot_to_cat)
                                end_cat = classify_category(str(player_follow_up['Stroke']), shot_to_cat)
                                entry = triple_cat_rules.get((start_cat, end_cat))
                                if entry is not None:
                                    q_end = float(entry.get('q_end', 0.5))
                            except Exception:
                                q_end = 0.5
                        # Blend pair and end-category qualities
                        q_final = (0.6 * quality_score) + (0.4 * q_end)
                        effectiveness = max(0, min(100, base_effectiveness + (q_final - 0.5) * 20))
                        if effectiveness >= 75:
                            color = 'green'
                            label = 'Excellent'
                        elif effectiveness >= 61:
                            color = 'orange'
                            label = 'Good'
                        elif effectiveness >= 50:
                            color = 'yellow'
                            label = 'Neutral'
                        elif effectiveness >= 35:
                            color = 'red'
                            label = 'Poor'
                        else:
                            color = 'darkred'
                            label = 'Bad'
                        shot_data.update({
                            'color': color,
                            'effectiveness': effectiveness,
                            'effectiveness_label': f"{label} ({effectiveness}%)",
                            'reason': "{} -> {} -> {}".format(shot['Stroke'], opponent_response['Stroke'], player_follow_up['Stroke'])
                        })
            # Optional: mark Unforced Error only if explicitly detected
            try:
                if bool(shot_data.get('is_losing_shot')) and is_explicit_ue(shot_data):
                    shot_data.update({'effectiveness_label': 'Unforced Error'})
            except Exception:
                pass
            rally_outputs.append(shot_data)
        # Finalize last-shot handling per rally before extending timeline_data
        if len(rally_outputs) > 0:
            last = rally_outputs[-1]
            prev = rally_outputs[-2] if len(rally_outputs) >= 2 else None
            last_player = str(last.get('Player'))
            winner = str(rally_outcome.get('winner')) if rally_outcome else None
            # Determine if last shot was explicit error by striker
            last_is_error = is_explicit_ue(last)
            if last_is_error:
                # Last shot ineffective; previous shot credited as forced error
                last.update({
                    'color': 'red',
                    'effectiveness': None,
                    'effectiveness_label': 'Error'
                })
                if prev is not None:
                    prev.update({
                        'color': 'green',
                        'effectiveness': 100,
                        'effectiveness_label': 'Forced Error'
                    })
            else:
                if winner and last_player != winner:
                    # Last shot belongs to loser without explicit error → ineffective
                    last.update({
                        'color': 'red',
                        'effectiveness': None,
                        'effectiveness_label': 'Ineffective Final Shot'
                    })
                # If last belongs to winner, keep as Rally Winner
        timeline_data.extend(rally_outputs)
    return timeline_data

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3 or len(sys.argv) > 7:
        print('Usage: python compute_effectiveness_v2.py input.csv output.csv [target_player] [rules_json] [shot_categories_json] [triple_category_rules_json]')
        sys.exit(1)
    input_csv = sys.argv[1]
    output_csv = sys.argv[2]
    target_player = sys.argv[3] if len(sys.argv) >= 4 else 'P0'
    rules_path = sys.argv[4] if len(sys.argv) >= 5 else None
    shot_cats_path = sys.argv[5] if len(sys.argv) >= 6 else None
    triple_cat_path = sys.argv[6] if len(sys.argv) == 7 else None
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
    out_df.to_csv(output_csv, index=False)
    print(f'Output written to {output_csv}')

