# End-to-End Data Flow: *_detailed.csv → 12 Key Takeaways

## 📊 **Complete Data Pipeline Flow**

### **STEP 1: Input Data Sources**
```
Input Files:
├── *_detailed.csv                    # Raw shot-by-shot data
├── *_detailed_effectiveness_enriched.csv  # Shot effectiveness scores
└── rally_narratives.csv (optional)   # Rally-level narratives
```

### **STEP 2: Consolidated Analysis (`consolidated_analysis.py`)**
```
Input: *_detailed.csv + *_detailed_effectiveness_enriched.csv
Output: consolidated.csv

Process:
├── Generates 5 RowTypes:
│   ├── rally_outcome (74 rows)           # Rally-level summaries
│   ├── sr_pattern_agg (40 rows)         # Serve-receive patterns
│   ├── three_shot_sequence (27 rows)    # 3-shot sequences
│   ├── shot_variation_agg_by_phase (188 rows)  # Shot variations
│   └── three_shot_summary (4 rows)      # 3-shot summaries
└── Enriches with effectiveness data
```

### **STEP 3: Topic CSV Generation (`generate_topic_csvs.py`)**
```
Input: consolidated.csv
Output: 6 topic-specific CSVs

Generated Files:
├── sr_summary.csv              # Serve-receive patterns by phase
├── sr_top_receives.csv         # Top receive shots by player
├── final_shot_top3.csv         # Top 3 winners/errors per player
├── phase_winloss_narratives.csv # Rally outcomes by phase
├── zone_success_frames.csv     # Zone effectiveness (often empty)
└── three_shot_top.csv          # Most common 3-shot sequences
```

### **STEP 4: LLM Analysis Process**
```
Input: Topic CSVs + *_detailed_effectiveness_enriched.csv
Output: Individual section analyses

LLM Analysis Steps:
├── Section 1: Serve-Receive Analysis
│   ├── Input: sr_summary.csv + sr_top_receives.csv
│   ├── LLM Prompt: Serve-receive pattern analysis
│   └── Output: Serve-receive insights
├── Section 2: Winning & Losing Shots
│   ├── Input: final_shot_totals.csv + final_shot_top3.csv
│   ├── LLM Prompt: Winner/error pattern analysis
│   └── Output: Winning/losing shot insights
├── Section 3: Rally Momentum & Turning Points
│   ├── Input: phase_winloss_narratives.csv
│   ├── LLM Prompt: Rally momentum analysis
│   └── Output: Momentum and turning point insights
├── Section 4: Shot Effectiveness
│   ├── Input: *_detailed_effectiveness_enriched.csv
│   ├── LLM Prompt: Shot effectiveness analysis
│   └── Output: Shot effectiveness insights
├── Section 5: Zones
│   ├── Input: zone_success_frames.csv
│   ├── LLM Prompt: Zone effectiveness analysis
│   └── Output: Zone insights
└── Section 6: Top-3s + Turning Points
    ├── Input: Combined insights from sections 1-5
    ├── LLM Prompt: Micro-summary analysis
    └── Output: Top-3 summary
```

### **STEP 5: Final Aggregation**
```
Input: Individual section analyses (from Step 4)
Output: 12_key_takeaways.md

LLM Aggregation Process:
├── Input: All 6 section analyses
├── LLM Prompt: Final 12 key takeaways aggregation
│   ├── Shared guard-rails (prepended to every prompt)
│   ├── Consolidate insights from sections 1-6
│   └── Group into 4 categories:
│       ├── Things that are working
│       ├── Things that absolutely don't work
│       ├── Things that could be better
│       └── Mandatory observations
└── Output: Final 12 key takeaways in natural language
```

## 🔍 **Critical Data Flow Issues Identified**

### **Issue 1: Data Aggregation Gap**
```
Problem: final_shot_top3.csv only captures RALLY-ENDING shots
├── Winners: Shots that end rallies (forehand_smash_cross, etc.)
├── Errors: Shots that end rallies (overhead_drop_cross, etc.)
└── MISSING: Intermediate shots with poor effectiveness

Impact: forehand_lift_cross (33 instances, 0-37% effectiveness) not captured
```

### **Issue 2: LLM Prompt Analysis Blind Spot**
```
What We Did:
├── Used final_shot_top3.csv as primary source for LLM prompts
├── LLM focused on rally-ending shots only
├── Shot Effectiveness section prompt didn't emphasize intermediate shots
└── Missed momentum-affecting intermediate shots in LLM analysis

What We Should Do:
├── Use *_detailed_effectiveness_enriched.csv as primary source for Section 4
├── LLM prompt should explicitly request ALL shots with effectiveness < 40%
├── Include both rally-ending AND momentum-affecting shots in prompts
└── Ensure LLM analyzes comprehensive shot effectiveness patterns
```

### **Issue 3: Incomplete Data Utilization**
```
Current Process:
├── consolidated_analysis.py → consolidated.csv
├── generate_topic_csvs.py → topic CSVs
└── Manual analysis → 12 key takeaways

Missing Step:
└── Effectiveness pattern analysis from detailed data
```

## 🤖 **LLM Prompt Structure Details**

### **Shared Guard-Rails (Prepended to Every Prompt)**
```
- Athlete-friendly, bullet-heavy format
- Avoid directives, use numbers sparingly
- Prefer frequent patterns over isolated incidents
- Include frame ranges for all observations
- Convert shot names to Title Case
- Include score states when relevant
- Convey limited data naturally
- Avoid "Mixed" tactical categories
- Define tactical terms subtly in-line once per item
```

### **Section-Specific Prompts:**
```
Section 1: Serve-Receive
├── Prompt: "Analyze serve-receive patterns from sr_summary.csv and sr_top_receives.csv"
├── Focus: Serve variation, receive effectiveness, frame patterns
└── Output: Natural language insights with frame references

Section 2: Winning & Losing Shots  
├── Prompt: "Analyze winning and losing shot patterns from final_shot data"
├── Focus: Most effective/ineffective shots, frequency patterns
└── Output: Shot effectiveness insights with frame examples

Section 3: Rally Momentum
├── Prompt: "Analyze rally momentum and turning points from phase narratives"
├── Focus: Momentum shifts, turning point patterns, phase performance
└── Output: Momentum insights with rally frame spans

Section 4: Shot Effectiveness
├── Prompt: "Analyze shot effectiveness patterns from detailed effectiveness data"
├── Focus: ALL shots with effectiveness < 40%, not just rally-ending shots
└── Output: Comprehensive shot effectiveness insights

Section 5: Zones
├── Prompt: "Analyze zone effectiveness from zone_success_frames.csv"
├── Focus: Most/least successful court zones, frame patterns
└── Output: Zone effectiveness insights

Section 6: Top-3s + Turning Points
├── Prompt: "Create micro-summary of top-3 patterns and turning points"
├── Focus: Key highlights from all previous sections
└── Output: Condensed summary insights

Final Aggregator:
├── Prompt: "Consolidate all section analyses into 12 key takeaways"
├── Focus: Group insights into 4 categories, maintain natural language
└── Output: Final 12 key takeaways in athlete-friendly format
```

## 📈 **Recommended Improved Flow**

### **Enhanced Step 4: Comprehensive Analysis**
```
Input: All CSVs + detailed effectiveness data
Process:
├── Primary Analysis: *_detailed_effectiveness_enriched.csv
│   ├── Identify shots with effectiveness < 40%
│   ├── Count frequency of ineffective shots
│   └── Analyze patterns (forehand_lift_cross → opponent_smash)
├── Secondary Analysis: Topic CSVs
│   ├── Validate findings against aggregated data
│   └── Add rally-ending shot patterns
└── Synthesis: Combine both analyses
    ├── Rally-ending patterns (from final_shot_top3.csv)
    ├── Momentum-affecting patterns (from effectiveness data)
    └── Complete shot effectiveness picture
```

## 🎯 **Key Files in Current Flow**

### **Primary Data Sources:**
- `*_detailed_effectiveness_enriched.csv` - **MOST IMPORTANT** (comprehensive shot data)
- `consolidated.csv` - Aggregated analysis
- `final_shot_top3.csv` - Rally-ending shots only

### **Generated Analysis Files:**
- `sr_summary.csv` - Serve-receive patterns
- `phase_winloss_narratives.csv` - Rally outcomes
- `12_key_takeaways.md` - Final analysis

### **Missing Analysis:**
- Effectiveness pattern analysis across all shots
- Intermediate shot impact on rally momentum
- Comprehensive shot effectiveness ranking

## 🔧 **Process Fix Required**

### **Current Gap:**
```
forehand_lift_cross: 33 instances, 0-37% effectiveness
├── Creates negative momentum
├── Sets up opponent attacks
├── Most frequent ineffective shot
└── COMPLETELY MISSED in current analysis
```

### **Required Fix:**
```
1. Update Section 4 LLM prompt to emphasize detailed effectiveness data
2. LLM prompt should explicitly request ALL shots with effectiveness < 40%
3. Include intermediate shot analysis in LLM prompts
4. Ensure LLM identifies momentum-affecting patterns
5. Cross-validate LLM analysis with aggregated data
6. Update final aggregator prompt to include intermediate shot insights
```

This analysis reveals that our current process has a critical blind spot in intermediate shot effectiveness analysis, leading to missed insights about momentum-affecting patterns.
