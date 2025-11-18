# Tempo Classification Logic - Explanation

## Overview

Tempo events are classified as **fast/normal/slow** based on comparing a player's response time to statistical thresholds. The thresholds are calculated using percentile-based statistics (p10 and p90) from historical data.

## Step 1: Calculate Response Time

**Formula:**
```python
response_time_sec = (current_frame - opponent_prev_frame) / fps
```

**Code (lines 241-243):**
```python
response_time_sec_raw: Optional[float] = None
if opp_prev_frame is not None:
    response_time_sec_raw = (frame - opp_prev_frame) / (fps if fps > 0 else 30.0)
```

See `RESPONSE_TIME_CALCULATION_EXPLANATION.md` for details.

## Step 2: Clamp Response Times

**Purpose:** Remove outliers before calculating statistics

**Code (line 356):**
```python
df_valid["rt_clamped"] = df_valid["response_time_sec_raw"].astype(float).clip(lower=lower_cap, upper=upper_cap)
```

**Default values:**
- `lower_cap = 0.15` seconds (minimum reasonable response time)
- `upper_cap = 4.0` seconds (maximum reasonable response time)

**Example:**
- Raw response time: 0.05s → Clamped to 0.15s
- Raw response time: 5.0s → Clamped to 4.0s
- Raw response time: 1.0s → Stays 1.0s

## Step 3: Build Statistical Thresholds

**Method:** Calculate percentiles (p10 and p90) for different grouping levels

**Code (lines 157-165):**
```python
def compute_stats(values: List[float]) -> ComboStats:
    med = median(values)
    return ComboStats(
        count=len(values),
        median=med,
        p10=percentile(values, 10.0),  # 10th percentile = fast threshold
        p90=percentile(values, 90.0),  # 90th percentile = slow threshold
        mad=mad(values, med),
    )
```

**Threshold Levels (6 levels, in priority order):**

1. **Combo with Quality** (`combo_key_q`): `P0|opp:forehand_smash|resp:backhand_defense|q:high`
   - Most specific: Player + Opponent Shot + Response Shot + Incoming Shot Quality
   - Requires: `min_combo_n` (default: 30) instances

2. **Opponent-Only with Quality** (`opp_only_key_q`): `P0|opp:forehand_smash|q:high`
   - Less specific: Player + Opponent Shot + Incoming Shot Quality
   - Requires: `min_opp_stroke_n` (default: 30) instances

3. **Baseline with Quality** (`baseline_stats_q`): `P0|q:high`
   - General: Player + Incoming Shot Quality
   - No minimum required

4. **Combo** (`combo_key`): `P0|opp:forehand_smash|resp:backhand_defense`
   - Specific: Player + Opponent Shot + Response Shot
   - Requires: `min_combo_n` (default: 30) instances

5. **Opponent-Only** (`opp_only_key`): `P0|opp:forehand_smash|resp:*`
   - Less specific: Player + Opponent Shot (any response)
   - Requires: `min_opp_stroke_n` (default: 30) instances

6. **Baseline** (`baseline_stats`): `P0`
   - Most general: Player only (all shots)
   - No minimum required

**Code (lines 341-419):**
```python
def build_thresholds(...):
    # Clamp response times
    df_valid["rt_clamped"] = df_valid["response_time_sec_raw"].clip(lower=lower_cap, upper=upper_cap)
    
    # Calculate stats for each level
    combo_stats = {}  # Level 4
    combo_stats_q = {}  # Level 1
    opp_only_stats = {}  # Level 5
    opp_only_stats_q = {}  # Level 2
    baseline_stats = {}  # Level 6
    baseline_stats_q = {}  # Level 3
    
    # Null out thresholds if insufficient samples
    null_if_insufficient(combo_stats, min_combo_n)  # Requires 30+ instances
    null_if_insufficient(opp_only_stats, min_opp_stroke_n)  # Requires 30+ instances
```

## Step 4: Choose Threshold for Each Event

**Method:** Use fallback hierarchy - try most specific first, fall back to more general

**Code (lines 422-467):**
```python
def choose_threshold_for_event(...):
    # Try Level 1: combo with quality
    if incoming_eff_bin and combo_stats_q:
        st = combo_stats_q.get(f"{combo_key}|q:{incoming_eff_bin}")
        if st and st.p10 and st.p90:
            return st.p10, st.p90, "combo_q"
    
    # Try Level 2: opponent-only with quality
    if incoming_eff_bin and opp_only_stats_q:
        st = opp_only_stats_q.get(f"{opp_only_key}|q:{incoming_eff_bin}")
        if st and st.p10 and st.p90:
            return st.p10, st.p90, "opp_only_q"
    
    # Try Level 3: baseline with quality
    if incoming_eff_bin and baseline_stats_q:
        st = baseline_stats_q.get(f"{player}|q:{incoming_eff_bin}")
        if st and st.p10 and st.p90:
            return st.p10, st.p90, "baseline_q"
    
    # Try Level 4: combo
    if combo_key:
        st = combo_stats.get(combo_key)
        if st and st.p10 and st.p90:
            return st.p10, st.p90, "combo"
    
    # Try Level 5: opponent-only
    if opp_only_key:
        st = opp_only_stats.get(opp_only_key)
        if st and st.p10 and st.p90:
            return st.p10, st.p90, "opp_only"
    
    # Try Level 6: baseline
    st = baseline_stats.get(player)
    if st and st.p10 and st.p90:
        return st.p10, st.p90, "baseline"
    
    return None, None, "none"
```

**Example:**
- Event: P0 responds to `forehand_smash` with `backhand_defense`, incoming shot quality = `high`
- Try: `P0|opp:forehand_smash|resp:backhand_defense|q:high` (Level 1) - if count < 30, p10/p90 = None
- Fallback: `P0|opp:forehand_smash|q:high` (Level 2) - if count < 30, p10/p90 = None
- Fallback: `P0|q:high` (Level 3) - always available
- Result: Uses Level 3 thresholds, `threshold_source = "baseline_q"`

## Step 5: Classify Event

**Formula:**
```python
if response_time <= fast_threshold (p10):
    return "fast"
elif response_time >= slow_threshold (p90):
    return "slow"
else:
    return "normal"
```

**Code (lines 470-481):**
```python
def classify_event(value: Optional[float], fast_th: Optional[float], slow_th: Optional[float]) -> Optional[str]:
    if value is None or fast_th is None or slow_th is None:
        return None
    if value <= fast_th:
        return "fast"
    if value >= slow_th:
        return "slow"
    return "normal"
```

**Example:**
- Response time: 0.6 seconds
- Fast threshold (p10): 0.68 seconds
- Slow threshold (p90): 1.36 seconds
- **Classification: "fast"** (0.6 ≤ 0.68)

## Complete Example

**Scenario:** P0 responds to P1's `forehand_smash` with `backhand_defense`

**Step 1: Calculate Response Time**
- P1's shot: frame 8123
- P0's response: frame 8149
- Response time: (8149 - 8123) / 30 = 0.867 seconds

**Step 2: Clamp**
- 0.867s is within [0.15, 4.0] → Stays 0.867s

**Step 3: Build Keys**
- `combo_key`: `P0|opp:forehand_smash|resp:backhand_defense`
- `opp_only_key`: `P0|opp:forehand_smash|resp:*`
- `combo_key_q`: `P0|opp:forehand_smash|resp:backhand_defense|q:high` (if incoming shot was high quality)

**Step 4: Choose Threshold**
- Try Level 1: `combo_key_q` - if count < 30, skip
- Try Level 2: `opp_only_key_q` - if count < 30, skip
- Try Level 3: `P0|q:high` - found! p10=0.52, p90=1.096
- **Selected:** fast_th=0.52, slow_th=1.096, source="baseline_q"

**Step 5: Classify**
- Response time: 0.867s
- Fast threshold: 0.52s
- Slow threshold: 1.096s
- **Classification: "normal"** (0.52 < 0.867 < 1.096)

## Threshold Interpretation

**p10 (Fast Threshold):**
- 10% of historical instances were faster than this
- If your response time ≤ p10 → You're in the fastest 10% → **"fast"**

**p90 (Slow Threshold):**
- 90% of historical instances were faster than this
- If your response time ≥ p90 → You're in the slowest 10% → **"slow"**

**Between p10 and p90:**
- You're in the middle 80% → **"normal"**

## Key Insights

1. **Percentile-based:** Thresholds adapt to each player/match style
2. **Context-aware:** Uses most specific available threshold (combo > opponent-only > baseline)
3. **Quality-aware:** Considers incoming shot quality when available
4. **Fallback hierarchy:** Always finds a threshold (even if general)
5. **Sample size protection:** Requires 30+ instances for combo/opponent-only thresholds

## Potential Issues

1. **Most combos have <30 instances** → Falls back to baseline thresholds
2. **Threshold source may be misleading:** Labeled as "combo" but actually using "baseline"
3. **Percentiles sensitive to outliers:** One extreme value can shift p10/p90 significantly

## Output Columns in tempo_events.csv

- `response_time_sec`: The calculated response time
- `classification`: "fast", "normal", or "slow"
- `threshold_source`: Which level was used ("combo_q", "baseline_q", "combo", "opp_only", "baseline", "none")
- `fast_threshold`: The p10 value used
- `slow_threshold`: The p90 value used
- `z_score_baseline_mad`: Z-score using baseline median and MAD (for outlier detection)

