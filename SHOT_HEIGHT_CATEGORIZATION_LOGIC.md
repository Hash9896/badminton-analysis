# Shot Height Categorization Logic

## Overview
Shots are categorized as **high/medium/flat** based on two metrics:
1. **Flight Time** (time from shot execution to opponent's response) - indicates shot height
2. **Response Time** (player's response time to incoming shot) - indicates setup time

## Threshold Calculation Method

**Percentile-based thresholds** calculated from ALL clears/lifts in the dataset:
- **p25** (25th percentile) = Lower threshold
- **p50** (50th percentile / median) = Middle threshold  
- **p75** (75th percentile) = Upper threshold

### Example Thresholds (from your data):
```
Flight Time:
  p25 = 0.88 seconds
  p50 = 1.08 seconds (median)
  p75 = 1.28 seconds

Response Time:
  p25 = 0.88 seconds
  p50 = 1.04 seconds (median)
  p75 = 1.24 seconds
```

## Categorization Rules

### Step 1: Classify Flight Time
- **High**: `flight_time >= p75` (≥ 1.28s in your data)
- **Low**: `flight_time <= p25` (≤ 0.88s in your data)
- **Medium**: `p25 < flight_time < p75` (0.88s < time < 1.28s)

### Step 2: Classify Response Time
- **Slow**: `response_time >= p75` (≥ 1.24s in your data)
- **Fast**: `response_time <= p25` (≤ 0.88s in your data)
- **Medium**: `p25 < response_time < p75` (0.88s < time < 1.24s)

### Step 3: Combine for Final Category

**HIGH** (shot executed high/slow):
- Flight time is **high** (≥ p75), OR
- Flight time is **medium** AND response time is **slow** (≥ p75)

**FLAT** (shot executed flat/fast):
- Flight time is **low** (≤ p25) AND response time is **fast** (≤ p25)

**MEDIUM** (everything else):
- All other combinations

## Decision Tree

```
Is flight_time >= p75?
  YES → HIGH
  NO → Is flight_time <= p25?
    YES → Is response_time <= p25?
      YES → FLAT
      NO → MEDIUM
    NO → Is response_time >= p75?
      YES → HIGH
      NO → MEDIUM
```

## Examples from Your Data

### High Shot Example:
- Flight time: 1.36s (≥ 1.28s p75) → **HIGH**
- OR: Flight time: 1.0s (medium), Response time: 1.32s (≥ 1.24s p75) → **HIGH**

### Flat Shot Example:
- Flight time: 0.64s (≤ 0.88s p25) AND Response time: 0.72s (≤ 0.88s p25) → **FLAT**

### Medium Shot Example:
- Flight time: 1.0s (between p25 and p75), Response time: 1.0s (between p25 and p75) → **MEDIUM**

## Why Percentile-Based?

**Advantages:**
- ✅ Adapts to each match/player's style
- ✅ No arbitrary fixed thresholds
- ✅ Handles different playing speeds automatically

**Disadvantages:**
- ⚠️ Requires sufficient data (needs multiple clears/lifts)
- ⚠️ Relative to dataset, not absolute physical measurements
- ⚠️ May not work well for very small datasets (<20 shots)

## Alternative Approaches

If you want **fixed thresholds** instead:

```python
# Fixed thresholds (in seconds)
FLIGHT_TIME_HIGH = 1.3  # High if flight time >= 1.3s
FLIGHT_TIME_LOW = 0.9   # Low if flight time <= 0.9s
RESPONSE_TIME_SLOW = 1.2  # Slow if response time >= 1.2s
RESPONSE_TIME_FAST = 0.8  # Fast if response time <= 0.8s
```

## Current Distribution (from your data)

From 243 clears/lifts processed:
- **High**: 96 (39.5%)
- **Medium**: 133 (54.7%)
- **Flat**: 14 (5.8%)

This suggests most shots are in the medium range, with a good distribution of high shots but relatively few flat shots.

## Potential Issues

1. **Small dataset**: If you have <30 clears/lifts, percentiles may be unreliable
2. **Mixed shot types**: Currently aggregates all clears/lifts together. Different shot types (forehand_clear vs backhand_lift) may have different natural flight times
3. **Player differences**: P0 and P1 may have different baselines, but currently using combined percentiles

## Recommendations

1. **Consider per-shot-type thresholds**: Calculate percentiles separately for forehand_clear, backhand_lift, etc.
2. **Consider per-player thresholds**: Calculate percentiles separately for P0 vs P1
3. **Add confidence indicators**: Mark categories as "high confidence" (far from thresholds) vs "borderline" (near thresholds)
4. **Hybrid approach**: Use percentiles for relative ranking, but also report absolute flight times for physical interpretation

