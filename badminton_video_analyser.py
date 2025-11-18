#!/usr/bin/env python3
"""
Badminton Video Analysis Desktop App
Syncs video playback with tactical effectiveness analysis
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading
import time
from PIL import Image, ImageTk
import os

# Optional rules/category helpers
try:
    from rules_loader import load_shot_categories as rl_load_shot_categories, classify_category as rl_classify_category
except Exception:
    rl_load_shot_categories = None
    rl_classify_category = None

class BadmintonVideoAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("Badminton Tactical Video Analyzer")
        self.root.geometry("1400x900")
        self.root.configure(bg='#f0f0f0')
        
        # Video and data variables
        self.video_cap = None
        self.video_fps = 30
        self.video_frame_count = 0
        self.current_frame = 0
        self.is_playing = False
        self.match_data = None
        self.shot_data = []
        
        # GUI Variables
        self.video_frame_var = tk.StringVar()
        self.video_time_var = tk.StringVar(value="00:00 / 00:00")
        self.current_shot_info = tk.StringVar(value="No shot selected")
        
        # Category/navigation state (must be initialized BEFORE building UI)
        self.shot_to_cat = None
        self.selected_category_var = tk.StringVar(value="")
        self.category_status_var = tk.StringVar(value="No category selected")
        self.padding_seconds_var = tk.DoubleVar(value=1.5)
        self.matched_shots = []
        self.current_match_index = -1

        # Load categories early so the dropdown has values
        self.load_categories()

        # Create GUI
        self.create_gui()
        
    def create_gui(self):
        """Create the main GUI layout."""
        
        # Main container
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top section: File loading
        self.create_file_section(main_frame)
        
        # Middle section: Video player
        self.create_video_section(main_frame)
        
        # Timeline section
        self.create_timeline_section(main_frame)
        
        # Bottom section: Analysis dashboard
        self.create_analysis_section(main_frame)
        
    def create_file_section(self, parent):
        """Create file loading section."""
        file_frame = tk.LabelFrame(parent, text="Load Files", bg='#f0f0f0', font=('Arial', 10, 'bold'))
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Video file
        tk.Button(file_frame, text="Load Video", command=self.load_video,
                 bg='#4CAF50', fg='white', font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5, pady=5)
        
        # CSV file
        tk.Button(file_frame, text="Load Match Data (CSV)", command=self.load_csv,
                 bg='#2196F3', fg='white', font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Status
        self.status_label = tk.Label(file_frame, text="Load video and CSV files to begin analysis", 
                                   bg='#f0f0f0', fg='#666')
        self.status_label.pack(side=tk.LEFT, padx=20)
        
    def create_video_section(self, parent):
        """Create video player section."""
        video_frame = tk.LabelFrame(parent, text="Video Player", bg='#f0f0f0', font=('Arial', 10, 'bold'))
        video_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Video display
        self.video_label = tk.Label(video_frame, text="No video loaded", bg='black', fg='white',
                                  font=('Arial', 20))
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Video controls
        controls_frame = tk.Frame(video_frame, bg='#f0f0f0')
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Play/Pause button
        self.play_button = tk.Button(controls_frame, text="▶ Play", command=self.toggle_playback,
                                   bg='#FF5722', fg='white', font=('Arial', 12, 'bold'))
        self.play_button.pack(side=tk.LEFT, padx=5)
        
        # Time display
        tk.Label(controls_frame, textvariable=self.video_time_var, bg='#f0f0f0',
                font=('Arial', 10)).pack(side=tk.LEFT, padx=20)
        
        # Speed controls
        tk.Label(controls_frame, text="Speed:", bg='#f0f0f0').pack(side=tk.LEFT, padx=(20, 5))
        speed_frame = tk.Frame(controls_frame, bg='#f0f0f0')
        speed_frame.pack(side=tk.LEFT)
        
        for speed, text in [(0.5, "0.5x"), (1.0, "1x"), (2.0, "2x")]:
            tk.Button(speed_frame, text=text, command=lambda s=speed: self.set_playback_speed(s),
                     bg='#9E9E9E', fg='white', width=4).pack(side=tk.LEFT, padx=1)
        
        # Frame navigation
        nav_frame = tk.Frame(controls_frame, bg='#f0f0f0')
        nav_frame.pack(side=tk.RIGHT)
        
        tk.Button(nav_frame, text="⏮", command=lambda: self.jump_frames(-30),
                 bg='#607D8B', fg='white').pack(side=tk.LEFT, padx=1)
        tk.Button(nav_frame, text="⏪", command=lambda: self.jump_frames(-10),
                 bg='#607D8B', fg='white').pack(side=tk.LEFT, padx=1)
        tk.Button(nav_frame, text="⏩", command=lambda: self.jump_frames(10),
                 bg='#607D8B', fg='white').pack(side=tk.LEFT, padx=1)
        tk.Button(nav_frame, text="⏭", command=lambda: self.jump_frames(30),
                 bg='#607D8B', fg='white').pack(side=tk.LEFT, padx=1)
        
    def create_timeline_section(self, parent):
        """Create interactive timeline section."""
        timeline_frame = tk.LabelFrame(parent, text="Shot Effectiveness Timeline", 
                                     bg='#f0f0f0', font=('Arial', 10, 'bold'))
        timeline_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create matplotlib figure for timeline
        self.timeline_fig = Figure(figsize=(12, 3), facecolor='#f0f0f0')
        self.timeline_ax = self.timeline_fig.add_subplot(111)
        
        self.timeline_canvas = FigureCanvasTkAgg(self.timeline_fig, timeline_frame)
        self.timeline_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Connect click events
        self.timeline_canvas.mpl_connect('button_press_event', self.on_timeline_click)
        
        # Initialize empty timeline
        self.update_timeline_display()
        
    def create_analysis_section(self, parent):
        """Create analysis dashboard section."""
        analysis_frame = tk.LabelFrame(parent, text="Match Analysis Dashboard", 
                                     bg='#f0f0f0', font=('Arial', 10, 'bold'))
        analysis_frame.pack(fill=tk.X)
        
        # Create three columns
        left_frame = tk.Frame(analysis_frame, bg='#f0f0f0')
        center_frame = tk.Frame(analysis_frame, bg='#f0f0f0')
        right_frame = tk.Frame(analysis_frame, bg='#f0f0f0')
        
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # P0 Stats
        self.create_player_stats(left_frame, "P0", "#1f77b4")
        
        # P1 Stats  
        self.create_player_stats(center_frame, "P1", "#ff7f0e")
        
        # Current Shot Info
        self.create_shot_info(right_frame)
        # Category navigation controls
        self.create_category_controls(right_frame)
        
    def create_player_stats(self, parent, player, color):
        """Create player statistics display."""
        player_frame = tk.LabelFrame(parent, text=f"{player} Statistics", bg='#f0f0f0',
                                   font=('Arial', 10, 'bold'), fg=color)
        player_frame.pack(fill=tk.BOTH, expand=True)
        
        # Overall effectiveness
        setattr(self, f"{player.lower()}_effectiveness", tk.StringVar(value="0%"))
        tk.Label(player_frame, text="Overall Effectiveness:", bg='#f0f0f0',
                font=('Arial', 10, 'bold')).pack(anchor=tk.W, padx=5, pady=2)
        tk.Label(player_frame, textvariable=getattr(self, f"{player.lower()}_effectiveness"),
                bg='#f0f0f0', font=('Arial', 14, 'bold'), fg=color).pack(anchor=tk.W, padx=15)
        
        # Shot breakdown
        setattr(self, f"{player.lower()}_breakdown", tk.StringVar(value="No data"))
        tk.Label(player_frame, text="Shot Breakdown:", bg='#f0f0f0',
                font=('Arial', 10, 'bold')).pack(anchor=tk.W, padx=5, pady=(10, 2))
        tk.Label(player_frame, textvariable=getattr(self, f"{player.lower()}_breakdown"),
                bg='#f0f0f0', font=('Arial', 9), justify=tk.LEFT).pack(anchor=tk.W, padx=15)
        
    def create_shot_info(self, parent):
        """Create current shot information display."""
        info_frame = tk.LabelFrame(parent, text="Current Shot Analysis", bg='#f0f0f0',
                                 font=('Arial', 10, 'bold'))
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # Shot details
        tk.Label(info_frame, textvariable=self.current_shot_info, bg='#f0f0f0',
                font=('Arial', 10), justify=tk.LEFT, wraplength=250).pack(anchor=tk.W, padx=5, pady=5)
        
        # Quick actions
        action_frame = tk.Frame(info_frame, bg='#f0f0f0')
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(action_frame, text="Previous Shot", command=self.goto_previous_shot,
                 bg='#9E9E9E', fg='white', width=12).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Next Shot", command=self.goto_next_shot,
                 bg='#9E9E9E', fg='white', width=12).pack(side=tk.LEFT, padx=2)
        
    def create_category_controls(self, parent):
        """Create controls for category-based navigation and timestamp jumping."""
        cat_frame = tk.LabelFrame(parent, text="Category Navigation", bg='#f0f0f0',
                                  font=('Arial', 10, 'bold'))
        cat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        row1 = tk.Frame(cat_frame, bg='#f0f0f0')
        row1.pack(fill=tk.X, pady=(5, 2))
        tk.Label(row1, text="Category:", bg='#f0f0f0').pack(side=tk.LEFT, padx=(5, 8))
        self.category_combo = ttk.Combobox(row1, textvariable=self.selected_category_var,
                                           values=sorted(list(self.get_all_categories())), state='readonly', width=28)
        self.category_combo.pack(side=tk.LEFT)
        self.category_combo.bind('<<ComboboxSelected>>', lambda _e: self.on_category_change())

        row2 = tk.Frame(cat_frame, bg='#f0f0f0')
        row2.pack(fill=tk.X, pady=(5, 2))
        tk.Label(row2, text="Padding (s):", bg='#f0f0f0').pack(side=tk.LEFT, padx=(5, 5))
        pad_entry = tk.Entry(row2, width=6)
        pad_entry.pack(side=tk.LEFT)
        pad_entry.insert(0, str(self.padding_seconds_var.get()))
        def on_pad_change(event):
            try:
                self.padding_seconds_var.set(float(pad_entry.get()))
            except Exception:
                pass
        pad_entry.bind('<Return>', on_pad_change)
        pad_entry.bind('<FocusOut>', on_pad_change)
        tk.Button(row2, text="Go to First", command=self.go_to_first_match,
                 bg='#4CAF50', fg='white', width=10).pack(side=tk.LEFT, padx=6)
        tk.Button(row2, text="Prev", command=self.goto_prev_match,
                 bg='#607D8B', fg='white', width=7).pack(side=tk.LEFT, padx=2)
        tk.Button(row2, text="Next", command=self.goto_next_match,
                 bg='#607D8B', fg='white', width=7).pack(side=tk.LEFT, padx=2)

        row3 = tk.Frame(cat_frame, bg='#f0f0f0')
        row3.pack(fill=tk.X, pady=(6, 8))
        tk.Label(row3, textvariable=self.category_status_var, bg='#f0f0f0', fg='#333').pack(side=tk.LEFT, padx=5)
        
    def load_video(self):
        """Load video file."""
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.")]
        )
        print(f"[DEBUG] Selected file path: {file_path}")  # Debug print
        if file_path:
            self.video_cap = cv2.VideoCapture(file_path)
            print(f"[DEBUG] VideoCapture opened: {self.video_cap.isOpened()}")  # Debug print
            if self.video_cap.isOpened():
                self.video_fps = self.video_cap.get(cv2.CAP_PROP_FPS)
                self.video_frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
                self.current_frame = 0
                print(f"[DEBUG] FPS: {self.video_fps}, Frame count: {self.video_frame_count}")  # Debug print
                self.status_label.config(text=f"Video loaded: {file_path.split('/')[-1]}")
                self.update_video_frame()
            else:
                print("[DEBUG] Could not open video file with OpenCV.")  # Debug print
                messagebox.showerror("Error", "Could not load video file")
                
    def load_csv(self):
        """Load match data CSV."""
        file_path = filedialog.askopenfilename(
            title="Select Match Data CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                self.match_data = self.load_and_process_csv(file_path)
                self.shot_data = self.create_shot_timeline()
                self.update_timeline_display()
                self.update_player_stats()
                self.status_label.config(text=f"Match data loaded: {file_path.split('/')[-1]}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not load CSV file: {str(e)}")
                
    def load_and_process_csv(self, file_path):
        """Load and process match data CSV."""
        # Try different separators
        for sep in ['\t', ',', ';']:
            try:
                df = pd.read_csv(file_path, sep=sep)
                break
            except:
                continue
        
        # Handle combined column format
        if len(df.columns) == 1:
            combined_col = df.columns[0]
            data_rows = []
            for _, row in df.iterrows():
                parts = str(row[combined_col]).split(',')
                if len(parts) >= 3:
                    data_rows.append({
                        'timestamp': int(parts[0].strip()),
                        'player': parts[1].strip(),
                        'shot_type': parts[2].strip()
                    })
            df = pd.DataFrame(data_rows)
        elif len(df.columns) >= 3:
            df.columns = ['timestamp', 'player', 'shot_type'] + list(df.columns[3:])
        
        # Add shot analysis
        df['score'] = df['shot_type'].apply(self.get_shot_score)
        df['is_serve'] = df['shot_type'].str.lower().str.contains('serve', na=False)
        
        return df
    
    def get_shot_score(self, shot_type):
        """Calculate shot attacking score."""
        shot = str(shot_type).lower().replace('_cross', '')
        
        if 'serve' in shot:
            return 0.0
        elif any(x in shot for x in ['smash']):
            return 1.0
        elif any(x in shot for x in ['dribble']):
            return 1.0
        elif any(x in shot for x in ['netkeep', 'halfsmash']):
            return 0.7
        elif 'flat_game' in shot:
            return 0.65
        elif 'drive' in shot:
            return 0.6
        elif 'pulldrop' in shot:
            return 0.5
        elif any(x in shot for x in ['clear']):
            return 0.45
        elif 'lift' in shot:
            return 0.4
        elif any(x in shot for x in ['drop']):
            return 0.3
        elif 'defense' in shot:
            return 0.1
        else:
            return 0.5
    
    def create_shot_timeline(self):
        """Create timeline data for visualization."""
        if self.match_data is None:
            return []
        
        # Ensure expected fields exist
        df = self.match_data.copy()
        if 'is_serve' not in df.columns:
            df['is_serve'] = df['shot_type'].str.lower().str.contains('serve', na=False)
        if 'timestamp' not in df.columns and 'FrameNumber' in df.columns:
            df['timestamp'] = (df['FrameNumber'] / float(self.video_fps) * 1000.0).round().astype(int)

        # Try to group by rallies if have Game/Rally numbers; else process flat
        has_rallies = all(col in df.columns for col in ['GameNumber', 'RallyNumber'])

        timeline_data = []
        if has_rallies:
            for (_, _), rally in df.groupby(['GameNumber', 'RallyNumber']):
                rally = rally.reset_index(drop=True)
                last_idx = len(rally) - 1
                for i, shot in rally.iterrows():
                    color = 'red'
                    label = 'Poor'
                    if bool(shot['is_serve']):
                        # Serve error override: detect from text if provided
                        text_cols = [c for c in ['reason', 'effectiveness_label'] if c in rally.columns]
                        serve_error = False
                        for c in text_cols:
                            try:
                                val = str(shot[c]).lower()
                                if 'error' in val:
                                    serve_error = True
                                    break
                            except Exception:
                                pass
                        if serve_error:
                            color, label = 'red', 'Serve Error'
                        elif i == last_idx:
                            color, label = 'green', 'Ace Serve'
                        else:
                            # find opponent response then server follow-up
                            opp = rally[(rally.index > i) & (rally['player'] != shot['player']) & (~rally['is_serve'])]
                            if len(opp) > 0:
                                opp_first = opp.iloc[0]
                                opp_idx = rally[rally.index == opp_first.name].index[0]
                                sv = rally[(rally.index > opp_idx) & (rally['player'] == shot['player']) & (~rally['is_serve'])]
                                if len(sv) > 0:
                                    sv_first = sv.iloc[0]
                                    sv_idx = rally[rally.index == sv_first.name].index[0]
                                    if sv_idx == last_idx:
                                        color, label = 'green', 'Serve Led to Winner'
                                    else:
                                        color, label = 'gray', 'Serve'
                                else:
                                    color, label = 'gray', 'Serve'
                            else:
                                color, label = 'gray', 'Serve'
                    else:
                        s = float(shot['score']) if 'score' in rally.columns else self.get_shot_score(shot['shot_type'])
                        if s >= 0.75:
                            color, label = 'green', 'Excellent'
                        elif s >= 0.5:
                            color, label = 'orange', 'Good'
                        elif s >= 0.3:
                            color, label = 'yellow', 'Neutral'
                        else:
                            color, label = 'red', 'Poor'

                    timeline_data.append({
                        'timestamp': int(shot['timestamp']),
                        'player': shot['player'],
                        'shot_type': shot['shot_type'],
                        'score': float(shot['score']) if 'score' in rally.columns else self.get_shot_score(shot['shot_type']),
                        'color': color,
                        'effectiveness': label,
                        'category': self.classify_shot(shot['shot_type']),
                        'y_pos': 1 if shot['player'] == 'P0' else 0
                    })
        else:
            # Fallback: flat processing without rally context
            for _, shot in df.iterrows():
                if bool(shot['is_serve']):
                    color, label = 'gray', 'Serve'
                else:
                    s = float(shot['score']) if 'score' in df.columns else self.get_shot_score(shot['shot_type'])
                    if s >= 0.75:
                        color, label = 'green', 'Excellent'
                    elif s >= 0.5:
                        color, label = 'orange', 'Good'
                    elif s >= 0.3:
                        color, label = 'yellow', 'Neutral'
                    else:
                        color, label = 'red', 'Poor'
                timeline_data.append({
                    'timestamp': int(shot['timestamp']),
                    'player': shot['player'],
                    'shot_type': shot['shot_type'],
                    'score': float(shot['score']) if 'score' in df.columns else self.get_shot_score(shot['shot_type']),
                    'color': color,
                    'effectiveness': label,
                    'category': self.classify_shot(shot['shot_type']),
                    'y_pos': 1 if shot['player'] == 'P0' else 0
                })

        return timeline_data
    
    def update_timeline_display(self):
        """Update the timeline visualization."""
        self.timeline_ax.clear()
        
        if not self.shot_data:
            self.timeline_ax.text(0.5, 0.5, 'Load match data to see timeline', 
                                ha='center', va='center', transform=self.timeline_ax.transAxes)
            self.timeline_canvas.draw()
            return
        
        # Plot shots on timeline
        for shot in self.shot_data:
            x = shot['timestamp'] / 1000  # Convert to seconds
            y = shot['y_pos']
            color = shot['color']
            
            self.timeline_ax.scatter(x, y, c=color, s=50, alpha=0.8, picker=True)
        
        # If a category is selected, highlight matches
        try:
            selected = self.selected_category_var.get().strip()
            if selected and self.shot_data:
                matched = [s for s in self.shot_data if s.get('category') == selected]
                if matched:
                    xs = [s['timestamp']/1000 for s in matched]
                    ys = [s['y_pos'] for s in matched]
                    self.timeline_ax.scatter(xs, ys, facecolors='none', edgecolors='black',
                                             s=120, linewidths=1.5, zorder=3)
        except Exception:
            pass
        
        # Customize timeline
        self.timeline_ax.set_xlabel('Match Time (seconds)')
        self.timeline_ax.set_yticks([0, 1])
        self.timeline_ax.set_yticklabels(['P1', 'P0'])
        self.timeline_ax.set_title('Click any shot to jump • Select a category to navigate matches')
        self.timeline_ax.grid(True, alpha=0.3)
        
        # Add legend
        legend_elements = [
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='green', markersize=8, label='Excellent'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='orange', markersize=8, label='Good'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='yellow', markersize=8, label='Neutral'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=8, label='Poor'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=8, label='Serve')
        ]
        self.timeline_ax.legend(handles=legend_elements, bbox_to_anchor=(1.05, 1), loc='upper left')
        
        self.timeline_fig.tight_layout()
        self.timeline_canvas.draw()
    
    def on_timeline_click(self, event):
        """Handle clicks on timeline to jump to video timestamp."""
        if event.inaxes != self.timeline_ax or not self.shot_data:
            return
        
        # Find closest shot to click
        click_time = event.xdata
        closest_shot = min(self.shot_data, key=lambda x: abs(x['timestamp']/1000 - click_time))
        
        # Jump video to this timestamp
        target_frame = int((closest_shot['timestamp'] / 1000) * self.video_fps)
        self.jump_to_frame(target_frame)
        
        # Update shot info
        self.update_shot_info(closest_shot)

    def load_categories(self):
        """Attempt to load shot categories from a JSON file; fallback to heuristics if unavailable."""
        if rl_load_shot_categories is None:
            self.shot_to_cat = None
            return
        candidate_paths = [
            'response_classifications.json',
            os.path.join(os.path.dirname(__file__), '..', 'response_classifications.json'),
            os.path.join(os.path.dirname(__file__), 'response_classifications.json')
        ]
        for p in candidate_paths:
            try:
                norm_path = os.path.abspath(p)
                if os.path.exists(norm_path):
                    self.shot_to_cat = rl_load_shot_categories(norm_path)
                    break
            except Exception:
                continue

    def classify_shot(self, shot_type: str) -> str:
        """Return a coarse category for a given shot."""
        try:
            if rl_classify_category is not None and self.shot_to_cat is not None:
                return rl_classify_category(str(shot_type), self.shot_to_cat)
        except Exception:
            pass
        s = str(shot_type or '').strip().lower()
        if 'smash' in s:
            return 'attacking_shots'
        if 'defense' in s:
            return 'defensive_shots'
        if 'nettap' in s:
            return 'net_kill'
        if 'netkeep' in s or 'dribble' in s:
            return 'net_shots'
        if 'drop' in s or 'pulldrop' in s:
            return 'placement_shots'
        if 'lift' in s or 'clear' in s:
            return 'reset_shots'
        if 'drive' in s or 'flat' in s or 'push' in s:
            return 'pressure_shots'
        return 'unknown'

    def get_all_categories(self):
        """Collect available categories from data or known set."""
        if self.shot_data:
            try:
                cats = sorted(list({s.get('category', 'unknown') for s in self.shot_data}))
                return [c for c in cats if c]
            except Exception:
                pass
        if self.shot_to_cat:
            try:
                return sorted(list(set(self.shot_to_cat.values())))
            except Exception:
                pass
        return [
            'attacking_shots', 'defensive_shots', 'net_shots', 'net_kill',
            'placement_shots', 'reset_shots', 'pressure_shots'
        ]
    
    def update_shot_info(self, shot_data):
        """Update current shot information display."""
        info_text = f"Frame: {shot_data['timestamp']}\n"
        info_text += f"Player: {shot_data['player']}\n"
        info_text += f"Shot: {shot_data['shot_type']}\n"
        info_text += f"Effectiveness: {shot_data['effectiveness']}\n"
        info_text += f"Attack Score: {shot_data['score']:.2f}"
        
        self.current_shot_info.set(info_text)
    
    def update_player_stats(self):
        """Update player statistics displays."""
        if not self.shot_data:
            return
        
        for player in ['P0', 'P1']:
            player_shots = [s for s in self.shot_data if s['player'] == player and not s['shot_type'].lower().startswith('serve')]
            
            if player_shots:
                # Calculate overall effectiveness
                avg_score = np.mean([s['score'] for s in player_shots])
                effectiveness_pct = int(avg_score * 100)
                
                # Count shot types
                excellent = len([s for s in player_shots if s['color'] == 'green'])
                good = len([s for s in player_shots if s['color'] == 'orange'])
                neutral = len([s for s in player_shots if s['color'] == 'yellow'])
                poor = len([s for s in player_shots if s['color'] == 'red'])
                
                # Update displays
                getattr(self, f"{player.lower()}_effectiveness").set(f"{effectiveness_pct}%")
                
                breakdown = f"Excellent: {excellent}\n"
                breakdown += f"Good: {good}\n"
                breakdown += f"Neutral: {neutral}\n"
                breakdown += f"Poor: {poor}\n"
                breakdown += f"Total: {len(player_shots)}"
                
                getattr(self, f"{player.lower()}_breakdown").set(breakdown)
    
    def update_video_frame(self):
        """Update video display with current frame."""
        if self.video_cap is None or not self.video_cap.isOpened():
            return
        
        self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.video_cap.read()
        
        if ret:
            # Convert frame for tkinter display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (800, 450))  # Resize for display
            
            image = Image.fromarray(frame_resized)
            photo = ImageTk.PhotoImage(image)
            
            self.video_label.configure(image=photo, text="")
            self.video_label.image = photo  # Keep a reference
            
            # Update time display
            current_time = self.current_frame / self.video_fps
            total_time = self.video_frame_count / self.video_fps
            time_str = f"{self.format_time(current_time)} / {self.format_time(total_time)}"
            self.video_time_var.set(time_str)
    
    def format_time(self, seconds):
        """Format seconds as MM:SS."""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def toggle_playback(self):
        """Toggle video playback."""
        if self.video_cap is None:
            messagebox.showwarning("Warning", "Please load a video first")
            return
            
        self.is_playing = not self.is_playing
        
        if self.is_playing:
            self.play_button.config(text="⏸ Pause")
            self.play_video()
        else:
            self.play_button.config(text="▶ Play")
    
    def play_video(self):
        """Play video in separate thread."""
        def video_loop():
            while self.is_playing and self.current_frame < self.video_frame_count - 1:
                self.current_frame += 1
                self.root.after(0, self.update_video_frame)
                time.sleep(1 / self.video_fps)
            
            if self.current_frame >= self.video_frame_count - 1:
                self.is_playing = False
                self.root.after(0, lambda: self.play_button.config(text="▶ Play"))
        
        threading.Thread(target=video_loop, daemon=True).start()
    
    def jump_frames(self, frame_delta):
        """Jump forward or backward by specified frames."""
        if self.video_cap is None:
            return
            
        self.current_frame = max(0, min(self.video_frame_count - 1, self.current_frame + frame_delta))
        self.update_video_frame()
    
    def jump_to_frame(self, target_frame):
        """Jump to specific frame."""
        if self.video_cap is None:
            return
            
        self.current_frame = max(0, min(self.video_frame_count - 1, target_frame))
        self.update_video_frame()
    
    def set_playback_speed(self, speed):
        """Set video playback speed (placeholder for future implementation)."""
        pass  # Could be implemented with frame skipping
    
    def goto_previous_shot(self):
        """Jump to previous shot in timeline."""
        if not self.shot_data:
            return
            
        current_time = self.current_frame / self.video_fps
        previous_shots = [s for s in self.shot_data if s['timestamp']/1000 < current_time]
        
        if previous_shots:
            shot = previous_shots[-1]
            target_frame = int((shot['timestamp'] / 1000) * self.video_fps)
            self.jump_to_frame(target_frame)
            self.update_shot_info(shot)
    
    def goto_next_shot(self):
        """Jump to next shot in timeline."""
        if not self.shot_data:
            return
            
        current_time = self.current_frame / self.video_fps
        next_shots = [s for s in self.shot_data if s['timestamp']/1000 > current_time]
        
        if next_shots:
            shot = next_shots[0]
            target_frame = int((shot['timestamp'] / 1000) * self.video_fps)
            self.jump_to_frame(target_frame)
            self.update_shot_info(shot)

    def on_category_change(self):
        """Handle category selection changes: compute matches and jump to first with padding."""
        self.recompute_matches()
        self.go_to_first_match()

    def recompute_matches(self):
        selected = (self.selected_category_var.get() or '').strip()
        if not selected:
            self.matched_shots = []
            self.current_match_index = -1
            self.category_status_var.set('No category selected')
            self.update_timeline_display()
            return
        shots = sorted([s for s in self.shot_data if s.get('category') == selected], key=lambda s: s['timestamp'])
        self.matched_shots = shots
        self.current_match_index = 0 if shots else -1
        count = len(shots)
        self.category_status_var.set(f"{selected}: {count} matches")
        self.update_timeline_display()

    def go_to_first_match(self):
        if not self.matched_shots:
            return
        self.current_match_index = 0
        self.jump_to_match(self.current_match_index)

    def goto_prev_match(self):
        if not self.matched_shots:
            return
        self.current_match_index = (self.current_match_index - 1) % len(self.matched_shots)
        self.jump_to_match(self.current_match_index)

    def goto_next_match(self):
        if not self.matched_shots:
            return
        self.current_match_index = (self.current_match_index + 1) % len(self.matched_shots)
        self.jump_to_match(self.current_match_index)

    def jump_to_match(self, idx: int):
        try:
            shot = self.matched_shots[idx]
        except Exception:
            return
        pad = max(0.0, float(self.padding_seconds_var.get() or 0))
        ts_sec = max(0.0, (shot['timestamp'] / 1000.0) - pad)
        target_frame = int(ts_sec * float(self.video_fps or 30))
        self.jump_to_frame(target_frame)
        self.update_shot_info(shot)
        self.category_status_var.set(f"{self.selected_category_var.get()}: {len(self.matched_shots)} matches — at {self.current_match_index+1}/{len(self.matched_shots)}")

def main():
    """Main application entry point."""
    root = tk.Tk()
    app = BadmintonVideoAnalyzer(root)
    root.mainloop()

if __name__ == "__main__":
    main()