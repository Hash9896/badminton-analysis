#!/usr/bin/env python3
"""
Refined Badminton Match Analyzer
=================================
Generates 13 streamlined insights with frame references.

Usage:
    python badminton_analyzer_refined.py --input match_data.csv --output results/
"""

import pandas as pd
import numpy as np
import json
import os
import argparse
from collections import defaultdict, Counter
from datetime import datetime


class RefinedBadmintonAnalyzer:
    """Streamlined analyzer for 13 key insights."""
    
    def __init__(self, csv_path):
        """Initialize analyzer with match data."""
        print(f"Loading data from {csv_path}...")
        self.df = pd.read_csv(csv_path)  # Comma-separated
        self.validate_data()
        self.prepare_data()
        print(f"✓ Loaded {len(self.df)} shots from {self.df['GameNumber'].nunique()} game(s)")
    
    def validate_data(self):
        """Validate required columns exist."""
        required_cols = ['GameNumber', 'RallyNumber', 'StrokeNumber', 'FrameNumber',
                        'Player', 'Stroke', 'effectiveness', 'RallyWinner', 'IsWinningShot',
                        'IsLosingShot', 'is_serve', 'IsCrucial', 'reason']
        missing = [col for col in required_cols if col not in self.df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        print("✓ Data validation passed")
    
    def prepare_data(self):
        """Add derived fields."""
        # Create rally_id
        self.df['rally_id'] = (self.df['GameNumber'].astype(str) + '_' + 
                               self.df['RallyNumber'].astype(str))
        
        # Rally position categorization
        def categorize_position(stroke_num):
            if stroke_num <= 3:
                return 'early'
            elif stroke_num <= 6:
                return 'mid'
            else:
                return 'late'
        
        self.df['rally_position'] = self.df['StrokeNumber'].apply(categorize_position)
        
        # Rally length per rally
        rally_lengths = self.df.groupby('rally_id')['StrokeNumber'].max()
        self.df['rally_length'] = self.df['rally_id'].map(rally_lengths)
        
        # Analyzed shots filter (exclude serves and unforced errors)
        self.df['is_analyzed'] = (
            (self.df['effectiveness'].notna()) & 
            (~self.df['is_serve']) &
            (self.df['reason'] != 'Unforced error')
        )
        
        print("✓ Data preparation complete")
    
    def get_frame_refs(self, df_filtered, max_frames=10):
        """Extract frame numbers from filtered dataframe."""
        frames = df_filtered['FrameNumber'].astype(int).tolist()
        if len(frames) > max_frames:
            # Sample approach: show count + first N frames
            sample_frames = ','.join(map(str, frames[:max_frames]))
            return f"{len(frames)} shots: [{sample_frames}...]"
        return ','.join(map(str, frames))
    
    def get_rally_frame_ranges(self, rally_ids, max_ranges=10):
        """Get frame ranges for rallies, capped at max_ranges entries."""
        ranges = []
        for rid in rally_ids:
            rally_data = self.df[self.df['rally_id'] == rid]
            start = int(rally_data['FrameNumber'].min())
            end = int(rally_data['FrameNumber'].max())
            ranges.append(f"[{start}-{end}]")
        if len(ranges) > max_ranges:
            ranges = ranges[:max_ranges]
        return ','.join(ranges)
    
    def analyze_top_bottom_shots(self):
        """
        Insight 1: Top/Bottom 3 shots by weighted score.
        weighted_score = (effectiveness * 0.7) + (count_normalized * 0.3)
        """
        print("\n[1/13] Analyzing top/bottom shots...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        # Exclude terminal shots (winners and errors) to focus on in-rally effectiveness
        try:
            analyzed = analyzed[(analyzed['IsWinningShot'] != True) & (analyzed['IsLosingShot'] != True)]
        except Exception:
            # If columns are missing or malformed, proceed with existing filter
            pass
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            if len(player_data) == 0:
                continue
            
            # Calculate stats per shot
            shot_stats = player_data.groupby('Stroke').agg({
                'effectiveness': 'mean',
                'FrameNumber': 'count'
            }).round(2)
            shot_stats.columns = ['avg_effectiveness', 'count']
            
            # Normalize count to 0-100 scale
            max_count = shot_stats['count'].max()
            if max_count > 0:
                shot_stats['count_normalized'] = (shot_stats['count'] / max_count) * 100
            else:
                shot_stats['count_normalized'] = 0
            
            # Weighted score: 70% quality, 30% frequency
            shot_stats['weighted_score'] = (
                shot_stats['avg_effectiveness'] * 0.7 + 
                shot_stats['count_normalized'] * 0.3
            ).round(2)
            
            # Get frame references for each shot
            frames_dict = {}
            for shot in shot_stats.index:
                shot_data = player_data[player_data['Stroke'] == shot]
                frames_dict[shot] = self.get_frame_refs(shot_data, max_frames=10)
            
            shot_stats = shot_stats.reset_index()
            
            # Top 3 (minimum 2 attempts)
            eligible_top = shot_stats[shot_stats['count'] >= 2]
            if len(eligible_top) > 0:
                top_shots = eligible_top.nlargest(3, 'weighted_score')
                for rank, (idx, row) in enumerate(top_shots.iterrows(), 1):
                    results.append({
                        'player': player,
                        'rank': rank,
                        'shot_name': row['Stroke'],
                        'avg_effectiveness': row['avg_effectiveness'],
                        'count': int(row['count']),
                        'weighted_score': row['weighted_score'],
                        'shot_category': 'top',
                        'frame_references': frames_dict[row['Stroke']]
                    })
            
            # Bottom 3 (all shots)
            bottom_shots = shot_stats.nsmallest(3, 'weighted_score')
            for rank, (idx, row) in enumerate(bottom_shots.iterrows(), 1):
                results.append({
                    'player': player,
                    'rank': -rank,  # Negative for bottom
                    'shot_name': row['Stroke'],
                    'avg_effectiveness': row['avg_effectiveness'],
                    'count': int(row['count']),
                    'weighted_score': row['weighted_score'],
                    'shot_category': 'bottom',
                    'frame_references': frames_dict[row['Stroke']]
                })
        
        print(f"  ✓ Extracted {len(results)} shot rankings")
        return results
    
    def analyze_rally_position_effectiveness(self):
        """Insight 2: Effectiveness by rally position."""
        print("\n[2/13] Analyzing rally position effectiveness...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            for position in ['early', 'mid', 'late']:
                pos_data = player_data[player_data['rally_position'] == position]
                
                if len(pos_data) > 0:
                    results.append({
                        'player': player,
                        'rally_position': position,
                        'avg_effectiveness': round(pos_data['effectiveness'].mean(), 2),
                        'shot_count': len(pos_data),
                'sample_frame_references': self.get_frame_refs(pos_data, max_frames=10)
                    })
        
        print(f"  ✓ Extracted {len(results)} position metrics")
        return results
    
    def analyze_rally_length(self):
        """Insight 3: Rally length analysis."""
        print("\n[3/13] Analyzing rally lengths...")
        results = []
        
        # Get rally-level data
        rally_data = self.df.groupby('rally_id').agg({
            'StrokeNumber': 'max',
            'RallyWinner': 'first'
        })
        rally_data.columns = ['rally_length', 'winner']
        
        for player in ['P0', 'P1']:
            # Overall
            all_rallies = rally_data.index.tolist()
            results.append({
                'player': player,
                'metric': 'overall',
                'avg_rally_length': round(rally_data['rally_length'].mean(), 2),
                'rally_count': len(all_rallies),
                'rally_frame_ranges': self.get_rally_frame_ranges(all_rallies, max_ranges=10)
            })
            
            # Winning
            won_rallies = rally_data[rally_data['winner'] == player].index.tolist()
            if won_rallies:
                won_data = rally_data[rally_data['winner'] == player]
                results.append({
                    'player': player,
                    'metric': 'winning',
                    'avg_rally_length': round(won_data['rally_length'].mean(), 2),
                    'rally_count': len(won_rallies),
                    'rally_frame_ranges': self.get_rally_frame_ranges(won_rallies, max_ranges=10)
                })
            
            # Losing
            lost_rallies = rally_data[rally_data['winner'] != player].index.tolist()
            if lost_rallies:
                lost_data = rally_data[rally_data['winner'] != player]
                results.append({
                    'player': player,
                    'metric': 'losing',
                    'avg_rally_length': round(lost_data['rally_length'].mean(), 2),
                    'rally_count': len(lost_rallies),
                    'rally_frame_ranges': self.get_rally_frame_ranges(lost_rallies, max_ranges=10)
                })
        
        print(f"  ✓ Extracted {len(results)} rally length metrics")
        return results
    
    def analyze_domination_periods(self):
        """Insight 4: Rally position dominance."""
        print("\n[4/13] Analyzing domination periods...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            # Calculate avg effectiveness per position
            position_stats = {}
            for position in ['early', 'mid', 'late']:
                pos_data = player_data[player_data['rally_position'] == position]
                if len(pos_data) > 0:
                    position_stats[position] = {
                        'avg_eff': round(pos_data['effectiveness'].mean(), 2),
                        'frames': self.get_frame_refs(pos_data, max_frames=10)
                    }
            
            if len(position_stats) >= 2:
                # Find strongest and weakest
                strongest = max(position_stats.items(), key=lambda x: x[1]['avg_eff'])
                weakest = min(position_stats.items(), key=lambda x: x[1]['avg_eff'])
                
                results.append({
                    'player': player,
                    'strongest_phase': strongest[0],
                    'strongest_effectiveness': strongest[1]['avg_eff'],
                    'weakest_phase': weakest[0],
                    'weakest_effectiveness': weakest[1]['avg_eff'],
                    'differential': round(strongest[1]['avg_eff'] - weakest[1]['avg_eff'], 2),
                    'frame_ref_strongest': strongest[1]['frames'],
                    'frame_ref_weakest': weakest[1]['frames']
                })
        
        print(f"  ✓ Extracted {len(results)} domination metrics")
        return results
    
    def analyze_serve_return_patterns(self):
        """Insight 5: Serve-return effectiveness patterns."""
        print("\n[5/13] Analyzing serve-return patterns...")
        results = []
        
        # Get serve-return pairs
        serve_returns = []
        for rally_id, group in self.df.groupby('rally_id'):
            rally_shots = group.sort_values('StrokeNumber')
            if len(rally_shots) >= 2:
                serve = rally_shots.iloc[0]
                return_shot = rally_shots.iloc[1]
                
                if serve['is_serve']:
                    serve_returns.append({
                        'server': serve['Player'],
                        'serve_type': serve['Stroke'],
                        'serve_frame': int(serve['FrameNumber']),
                        'return_shot': return_shot['Stroke'],
                        'return_frame': int(return_shot['FrameNumber']),
                        'return_effectiveness': return_shot['effectiveness'] if return_shot['is_analyzed'] else None
                    })
        
        if not serve_returns:
            return results
        
        serve_df = pd.DataFrame(serve_returns)
        serve_df = serve_df[serve_df['return_effectiveness'].notna()]
        
        for server in ['P0', 'P1']:
            server_data = serve_df[serve_df['server'] == server]
            
            if len(server_data) == 0:
                continue
            
            # Group by serve-return combo
            combos = server_data.groupby(['serve_type', 'return_shot']).agg({
                'return_effectiveness': ['mean', 'count'],
                'serve_frame': 'first',
                'return_frame': 'first'
            }).round(2)
            combos.columns = ['return_effectiveness', 'frequency', 'serve_frame', 'return_frame']
            combos = combos.reset_index()
            
            # Top 2
            if len(combos) > 0:
                top_2 = combos.nlargest(2, 'return_effectiveness')
                for rank, (idx, row) in enumerate(top_2.iterrows(), 1):
                    results.append({
                        'server': server,
                        'rank': rank,
                        'serve_type': row['serve_type'],
                        'return_shot': row['return_shot'],
                        'return_effectiveness': row['return_effectiveness'],
                        'frequency': int(row['frequency']),
                        'serve_frame': int(row['serve_frame']),
                        'return_frame': int(row['return_frame'])
                    })
                
                # Bottom 2
                bottom_2 = combos.nsmallest(2, 'return_effectiveness')
                for rank, (idx, row) in enumerate(bottom_2.iterrows(), 1):
                    results.append({
                        'server': server,
                        'rank': -rank,
                        'serve_type': row['serve_type'],
                        'return_shot': row['return_shot'],
                        'return_effectiveness': row['return_effectiveness'],
                        'frequency': int(row['frequency']),
                        'serve_frame': int(row['serve_frame']),
                        'return_frame': int(row['return_frame'])
                    })
        
        print(f"  ✓ Extracted {len(results)} serve-return patterns")
        return results
    
    def analyze_risk_reward_top3(self):
        """Insight 6: Top 3 risk-reward shots."""
        print("\n[6/13] Analyzing risk-reward...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            # Calculate risk-reward stats
            shot_stats = player_data.groupby('Stroke').agg({
                'effectiveness': ['mean', 'std', 'count']
            }).round(2)
            shot_stats.columns = ['avg_effectiveness', 'risk_score', 'frequency']
            shot_stats = shot_stats[shot_stats['frequency'] >= 3]  # Min 3 for variance
            shot_stats['risk_score'] = shot_stats['risk_score'].fillna(0)
            
            # Combined score: higher effectiveness, lower risk = better
            shot_stats['combined_score'] = (
                shot_stats['avg_effectiveness'] - (shot_stats['risk_score'] * 0.3)
            )
            
            if len(shot_stats) == 0:
                continue
            
            # Get top 3
            top_3 = shot_stats.nlargest(3, 'combined_score')
            
            for rank, (shot, row) in enumerate(top_3.iterrows(), 1):
                shot_data = player_data[player_data['Stroke'] == shot]
                
                # Check if used in crucial moments
                used_in_crucial = shot_data['IsCrucial'].any()
                
                results.append({
                    'player': player,
                    'rank': rank,
                    'shot_name': shot,
                    'avg_effectiveness': row['avg_effectiveness'],
                    'risk_score': row['risk_score'],
                    'frequency': int(row['frequency']),
                    'used_in_crucial': bool(used_in_crucial),
                    'frame_references': self.get_frame_refs(shot_data)
                })
        
        print(f"  ✓ Extracted {len(results)} risk-reward metrics")
        return results
    
    def analyze_forced_unforced_errors(self):
        """Insight 7: Top 4 error-causing shots."""
        print("\n[7/13] Analyzing errors...")
        results = []
        
        # Get all losing shots
        errors = self.df[self.df['IsLosingShot'] == True].copy()
        
        for player in ['P0', 'P1']:
            player_errors = errors[errors['Player'] == player]
            
            # Separate forced vs unforced
            unforced = player_errors[player_errors['reason'] == 'Unforced error']
            forced = player_errors[player_errors['reason'] != 'Unforced error']
            
            # Count by shot type
            unforced_counts = unforced.groupby('Stroke').agg({
                'FrameNumber': ['count', list],
                'IsCrucial': 'any'
            })
            
            forced_counts = forced.groupby('Stroke').agg({
                'FrameNumber': ['count', list],
                'IsCrucial': 'any'
            })
            
            # Unforced errors
            if len(unforced_counts) > 0:
                unforced_counts.columns = ['error_count', 'frames', 'in_crucial']
                unforced_counts = unforced_counts.sort_values('error_count', ascending=False).head(4)
                
                for rank, (shot, row) in enumerate(unforced_counts.iterrows(), 1):
                    frames_vals = list(row['frames']) if isinstance(row['frames'], list) else []
                    frame_list = ','.join(map(str, frames_vals[:10]))
                    results.append({
                        'player': player,
                        'rank': rank,
                        'shot_name': shot,
                        'error_type': 'unforced',
                        'error_count': int(row['error_count']),
                        'in_crucial_phase': bool(row['in_crucial']),
                        'frame_references': frame_list
                    })
            
            # Forced errors
            if len(forced_counts) > 0:
                forced_counts.columns = ['error_count', 'frames', 'in_crucial']
                forced_counts = forced_counts.sort_values('error_count', ascending=False).head(4)
                
                for rank, (shot, row) in enumerate(forced_counts.iterrows(), 1):
                    frames_vals = list(row['frames']) if isinstance(row['frames'], list) else []
                    frame_list = ','.join(map(str, frames_vals[:10]))
                    results.append({
                        'player': player,
                        'rank': rank,
                        'shot_name': shot,
                        'error_type': 'forced',
                        'error_count': int(row['error_count']),
                        'in_crucial_phase': bool(row['in_crucial']),
                        'frame_references': frame_list
                    })
        
        print(f"  ✓ Extracted {len(results)} error metrics")
        return results
    
    def analyze_avoid_list(self):
        """Insight 8: Top 2 shots to avoid."""
        print("\n[8/13] Analyzing avoid list...")
        results = []
        
        for player in ['P0', 'P1']:
            player_shots = self.df[(self.df['Player'] == player) & (~self.df['is_serve'])]
            
            avoid_list = []
            for stroke in player_shots['Stroke'].unique():
                stroke_shots = player_shots[player_shots['Stroke'] == stroke]
                total = len(stroke_shots)
                
                if total >= 2:  # Minimum 2 attempts
                    errors = len(stroke_shots[stroke_shots['IsLosingShot'] == True])
                    error_rate = errors / total
                    
                    if error_rate >= 0.3:  # 30% threshold
                        # Get all attempt frames (capped)
                        attempt_frames = ','.join(map(str, stroke_shots['FrameNumber'].tolist()[:10]))
                        # Get error frames (capped)
                        error_frames = ','.join(map(str, stroke_shots[stroke_shots['IsLosingShot']==True]['FrameNumber'].tolist()[:10]))
                        
                        avoid_list.append({
                            'player': player,
                            'shot_name': stroke,
                            'total_attempts': total,
                            'errors': errors,
                            'error_rate': round(error_rate, 2),
                            'frame_attempts': attempt_frames,
                            'frame_errors': error_frames
                        })
            
            # Sort by error rate and get top 2
            avoid_list = sorted(avoid_list, key=lambda x: x['error_rate'], reverse=True)[:2]
            
            for rank, item in enumerate(avoid_list, 1):
                item['rank'] = rank
                results.append(item)
        
        print(f"  ✓ Extracted {len(results)} avoid list entries")
        return results
    
    def analyze_winning_shots(self):
        """Insight 9: Top 3 winning shots."""
        print("\n[9/13] Analyzing winning shots...")
        results = []
        
        winners = self.df[self.df['IsWinningShot'] == True]
        
        for player in ['P0', 'P1']:
            player_winners = winners[winners['Player'] == player]
            
            if len(player_winners) == 0:
                results.append({
                    'player': player,
                    'rank': 1,
                    'shot_name': 'none',
                    'winner_count': 0,
                    'avg_effectiveness': 0.0,
                    'court_position_band': 0,
                    'frame_references': ''
                })
                continue
            
            # Group by shot type
            winner_stats = player_winners.groupby('Stroke').agg({
                'FrameNumber': ['count', list],
                'effectiveness': 'mean',
                'band': lambda x: x.mode()[0] if len(x) > 0 else 0
            })
            winner_stats.columns = ['winner_count', 'frames', 'avg_effectiveness', 'band']
            winner_stats = winner_stats.sort_values('winner_count', ascending=False).head(3)
            
            for rank, (shot, row) in enumerate(winner_stats.iterrows(), 1):
                frame_list = ','.join(map(str, list(row['frames'])[:10]))
                results.append({
                    'player': player,
                    'rank': rank,
                    'shot_name': shot,
                    'winner_count': int(row['winner_count']),
                    'avg_effectiveness': round(row['avg_effectiveness'], 2) if pd.notna(row['avg_effectiveness']) else 100.0,
                    'court_position_band': int(row['band']),
                    'frame_references': frame_list
                })
        
        print(f"  ✓ Extracted {len(results)} winning shot metrics")
        return results
    
    def analyze_pressure_performance(self):
        """Insight 10: Performance under pressure."""
        print("\n[10/13] Analyzing pressure performance...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            crucial = player_data[player_data['IsCrucial'] == True]
            normal = player_data[player_data['IsCrucial'] == False]
            
            crucial_eff = crucial['effectiveness'].mean() if len(crucial) > 0 else 0
            normal_eff = normal['effectiveness'].mean() if len(normal) > 0 else 0
            
            results.append({
                'player': player,
                'crucial_avg_effectiveness': round(crucial_eff, 2),
                'crucial_shot_count': len(crucial),
                'normal_avg_effectiveness': round(normal_eff, 2),
                'normal_shot_count': len(normal),
                'pressure_differential': round(crucial_eff - normal_eff, 2),
                'crucial_frames': self.get_frame_refs(crucial, max_frames=10),
                'normal_frames': self.get_frame_refs(normal, max_frames=10)
            })
        
        print(f"  ✓ Extracted {len(results)} pressure performance metrics")
        return results
    
    def analyze_endurance(self):
        """Insight 11: Endurance indicators."""
        print("\n[11/13] Analyzing endurance...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            short = player_data[player_data['rally_length'] < 10]
            long = player_data[player_data['rally_length'] >= 10]
            
            short_eff = short['effectiveness'].mean() if len(short) > 0 else 0
            long_eff = long['effectiveness'].mean() if len(long) > 0 else 0
            
            results.append({
                'player': player,
                'short_rally_effectiveness': round(short_eff, 2),
                'short_rally_count': len(short),
                'long_rally_effectiveness': round(long_eff, 2),
                'long_rally_count': len(long),
                'endurance_differential': round(long_eff - short_eff, 2),
                'short_rally_frames': self.get_frame_refs(short, max_frames=10),
                'long_rally_frames': self.get_frame_refs(long, max_frames=10)
            })
        
        print(f"  ✓ Extracted {len(results)} endurance metrics")
        return results
    
    def analyze_risk_tolerance(self):
        """Insight 12: Risk tolerance."""
        print("\n[12/13] Analyzing risk tolerance...")
        results = []
        analyzed = self.df[self.df['is_analyzed']].copy()
        
        # Calculate median std dev across all shots to define "high risk"
        all_shot_variance = analyzed.groupby('Stroke')['effectiveness'].std()
        median_variance = all_shot_variance.median()
        
        for player in ['P0', 'P1']:
            player_data = analyzed[analyzed['Player'] == player]
            
            # Calculate variance per shot
            shot_variance = player_data.groupby('Stroke')['effectiveness'].std()
            high_risk_shots = shot_variance[shot_variance > median_variance].index.tolist()
            
            # Count high-risk shots used
            high_risk_data = player_data[player_data['Stroke'].isin(high_risk_shots)]
            
            total_shots = len(player_data)
            high_risk_count = len(high_risk_data)
            risk_pct = (high_risk_count / total_shots * 100) if total_shots > 0 else 0
            
            results.append({
                'player': player,
                'high_risk_shot_count': high_risk_count,
                'total_shots': total_shots,
                'risk_tolerance_pct': round(risk_pct, 2),
                'high_risk_shots_list': ','.join(high_risk_shots),
                'high_risk_frames': self.get_frame_refs(high_risk_data, max_frames=10)
            })
        
        print(f"  ✓ Extracted {len(results)} risk tolerance metrics")
        return results
    
    def analyze_crucial_conversions(self):
        """Insight 13: Crucial point conversion rates."""
        print("\n[13/13] Analyzing crucial point conversions...")
        results = []
        
        # Identify crucial rallies (any shot with IsCrucial = TRUE)
        crucial_rallies = self.df[self.df['IsCrucial'] == True]['rally_id'].unique()
        
        for player in ['P0', 'P1']:
            won_crucial = []
            lost_crucial = []
            
            for rally_id in crucial_rallies:
                rally_data = self.df[self.df['rally_id'] == rally_id]
                winner = rally_data['RallyWinner'].iloc[0]
                
                if winner == player:
                    won_crucial.append(rally_id)
                else:
                    lost_crucial.append(rally_id)
            
            total_crucial = len(crucial_rallies)
            won_count = len(won_crucial)
            conversion_rate = (won_count / total_crucial) if total_crucial > 0 else 0
            
            results.append({
                'player': player,
                'crucial_points_won': won_count,
                'crucial_points_total': total_crucial,
                'conversion_rate': round(conversion_rate, 2),
                'crucial_point_frames_won': self.get_rally_frame_ranges(won_crucial, max_ranges=10),
                'crucial_point_frames_lost': self.get_rally_frame_ranges(lost_crucial, max_ranges=10)
            })
        
        print(f"  ✓ Extracted {len(results)} crucial conversion metrics")
        return results
    
    def generate_all_insights(self):
        """Generate all 13 insights."""
        print("\n" + "="*80)
        print("GENERATING REFINED INSIGHTS")
        print("="*80)
        
        insights = {
            '01_top_bottom_shots': self.analyze_top_bottom_shots(),
            '02_rally_position_effectiveness': self.analyze_rally_position_effectiveness(),
            '03_rally_length': self.analyze_rally_length(),
            '04_domination_periods': self.analyze_domination_periods(),
            '05_serve_return_patterns': self.analyze_serve_return_patterns(),
            '06_risk_reward_top3': self.analyze_risk_reward_top3(),
            '07_forced_unforced_errors': self.analyze_forced_unforced_errors(),
            '08_avoid_list': self.analyze_avoid_list(),
            '09_winning_shots': self.analyze_winning_shots(),
            '10_pressure_performance': self.analyze_pressure_performance(),
            '11_endurance': self.analyze_endurance(),
            '12_risk_tolerance': self.analyze_risk_tolerance(),
            '13_crucial_conversions': self.analyze_crucial_conversions()
        }
        
        return insights
    
    def save_outputs(self, output_dir):
        """Save tiered outputs: summary CSV, detailed JSON, frame references."""
        os.makedirs(output_dir, exist_ok=True)
        print("\n" + "-"*80)
        print("SAVING OUTPUTS")
        print("-"*80)
        
        insights = self.generate_all_insights()
        
        # 1. Summary CSV (long format)
        summary_rows = []
        for category, data in insights.items():
            category_name = category.replace('_', ' ').title()
            
            for item in data:
                # Flatten the item into a row
                row = {
                    'insight_category': category_name,
                    'player': item.get('player', item.get('server', '')),
                }
                
                # Add all other fields
                for key, value in item.items():
                    if key not in ['player', 'server']:
                        row[key] = value
                
                summary_rows.append(row)
        
        summary_df = pd.DataFrame(summary_rows)
        summary_path = os.path.join(output_dir, 'refined_insights_summary.csv')
        summary_df.to_csv(summary_path, index=False)
        print(f"✓ Saved {summary_path}")
        
        # 2. Detailed JSON
        json_path = os.path.join(output_dir, 'refined_insights_detailed.json')
        with open(json_path, 'w') as f:
            json.dump(insights, f, indent=2)
        print(f"✓ Saved {json_path}")
        
        # 3. Frame Reference Map
        frame_rows = []
        for category, data in insights.items():
            category_name = category.replace('_', ' ').title()
            
            for item in data:
                player = item.get('player', item.get('server', ''))
                
                # Extract frame reference fields
                for key, value in item.items():
                    if 'frame' in key.lower() and value:
                        frame_rows.append({
                            'insight_category': category_name,
                            'player': player,
                            'detail': key,
                            'frame_references': str(value)
                        })
        
        frame_df = pd.DataFrame(frame_rows)
        frame_path = os.path.join(output_dir, 'frame_references.csv')
        frame_df.to_csv(frame_path, index=False)
        print(f"✓ Saved {frame_path}")
        
        # 4. Summary report
        self.generate_summary_report(insights, output_dir)
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE!")
        print("="*80)
        print(f"\nAll outputs saved to: {output_dir}")
        print("\nGenerated files:")
        print("  1. refined_insights_summary.csv - Quick overview (long format)")
        print("  2. refined_insights_detailed.json - Full structured data")
        print("  3. frame_references.csv - Video frame lookup")
        print("  4. summary_report.txt - Human-readable summary")
    
    def generate_summary_report(self, insights, output_dir):
        """Generate human-readable summary report."""
        report = []
        report.append("="*80)
        report.append("REFINED BADMINTON MATCH ANALYSIS SUMMARY")
        report.append("="*80)
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"\nMatch Data: {len(self.df)} total shots across {self.df['rally_id'].nunique()} rallies")
        
        # Quick stats
        report.append("\n" + "-"*80)
        report.append("QUICK STATS")
        report.append("-"*80)
        
        final_scores = self.df.groupby('rally_id').first()[['ScoreP0', 'ScoreP1']].iloc[-1]
        report.append(f"Final Score: P0 {int(final_scores['ScoreP0'])} - {int(final_scores['ScoreP1'])} P1")
        
        rally_wins = self.df.groupby('rally_id')['RallyWinner'].first().value_counts()
        report.append(f"Rallies Won: P0 {rally_wins.get('P0', 0)} | P1 {rally_wins.get('P1', 0)}")
        
        # Insights summary
        report.append("\n" + "-"*80)
        report.append("INSIGHTS GENERATED")
        report.append("-"*80)
        
        for category, data in insights.items():
            category_name = category.replace('_', ' ').title()
            report.append(f"✓ {category_name}: {len(data)} metrics")
        
        report.append("\n" + "="*80)
        report.append("For detailed insights, see CSV and JSON files.")
        report.append("="*80)
        
        summary_path = os.path.join(output_dir, 'summary_report.txt')
        with open(summary_path, 'w') as f:
            f.write('\n'.join(report))
        print(f"✓ Saved {summary_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Refined Badminton Match Analyzer')
    parser.add_argument('--input', required=True, help='Path to input CSV file')
    parser.add_argument('--output', default='refined_outputs', help='Output directory')
    
    args = parser.parse_args()
    
    try:
        analyzer = RefinedBadmintonAnalyzer(args.input)
        analyzer.save_outputs(args.output)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())



