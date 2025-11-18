# Shot Effectiveness to Flight Time Mapping - Logic Document

## Objective
Create a mapping between shot effectiveness and flight time for clears and lifts to understand how shot height (high/low) correlates with effectiveness.

## Target Shots
- **Clears**: `forehand_clear`, `forehand_clear_cross`, `backhand_clear`, `backhand_clear_cross`, `overhead_clear`, `overhead_clear_cross`
- **Lifts**: `forehand_lift`, `forehand_lift_cross`, `backhand_lift`, `backhand_lift_cross`

## Core Logic

### Flight Time Definition
**Flight time** = Time between when a clear/lift is executed and when the opponent responds to it.

### Data Source
From `*_tempo_events.csv`:
- Each row represents a shot event
- `response_time_sec` in a row = time between opponent's previous shot and current shot
- **Key insight**: For a clear/lift shot at row i, the `response_time_sec` in the NEXT row (where opponent responds) IS the flight time of that clear/lift.

### Algorithm

1. **Filter for target shots**
   - Identify rows where `Stroke` matches clear/lift patterns
   - Extract: `Player`, `FrameNumber`, `time_sec`, `effectiveness`, `effectiveness_color`, `rally_id`, `Stroke`

2. **Find opponent's response**
   - For each clear/lift shot at row i:
     - Find next row j in same `rally_id` where:
       - `Player` != clear/lift player (opponent)
       - `StrokeNumber` > clear/lift stroke number
     - Extract `response_time_sec` from row j = **flight time**

3. **Handle edge cases**
   - **Rally ends with clear/lift**: No opponent response → exclude or mark as "no_response"
   - **Multiple shots before opponent responds**: Use first opponent shot (shouldn't happen in normal rally flow)
   - **Missing effectiveness**: Exclude or mark as "no_effectiveness"
   - **Missing response_time_sec**: Exclude (data quality issue)

4. **Calculate correlations**
   - Group by shot type (forehand_clear, backhand_lift_cross, etc.)
   - Group by player (P0/P1)
   - Calculate:
     - Flight time statistics (min, max, median, mean, p25, p75)
     - Effectiveness statistics per flight time band
     - Correlation coefficient (effectiveness vs flight time)
     - Scatter plot data

## Output Structure

### Primary Output: `*_shot_effectiveness_flight_time.csv`
Columns:
- `rally_id`
- `game`
- `rally`
- `stroke_no`
- `player`
- `stroke` (clear/lift type)
- `effectiveness`
- `effectiveness_color`
- `flight_time_sec`
- `opponent_response_stroke`
- `opponent_response_frame`
- `time_sec` (for video seeking)

### Summary Output: `*_shot_effectiveness_flight_time_summary.csv`
Grouped by (player, stroke):
- `player`
- `stroke`
- `count`
- `flight_time_min`
- `flight_time_p25`
- `flight_time_median`
- `flight_time_mean`
- `flight_time_p75`
- `flight_time_max`
- `effectiveness_min`
- `effectiveness_median`
- `effectiveness_mean`
- `effectiveness_max`
- `correlation_coefficient` (effectiveness vs flight_time)
- `high_flight_effectiveness_median` (flight_time > median)
- `low_flight_effectiveness_median` (flight_time <= median)

### JSON Output: `*_shot_effectiveness_flight_time.json`
Structured data for frontend visualization:
```json
{
  "fps": 30.0,
  "summary": {
    "P0": {
      "forehand_clear": {
        "count": 15,
        "flight_time_stats": {...},
        "effectiveness_stats": {...},
        "correlation": 0.45,
        "flight_time_bands": {
          "low": {"count": 7, "effectiveness_median": 35.0},
          "high": {"count": 8, "effectiveness_median": 65.0}
        }
      }
    }
  },
  "instances": [...]
}
```

## Potential Issues & Considerations

### 1. **Flight Time vs Response Time Confusion**
- **Clarification needed**: Flight time should be pure shuttle travel time
- **Current approach**: Using opponent's `response_time_sec` includes:
  - Shuttle flight time ✓
  - Opponent's reaction time ✗
  - Opponent's movement time ✗
- **Impact**: Flight times may be slightly inflated, but this is acceptable if we're consistent

### 2. **Shot Height Interpretation**
- **Assumption**: Longer flight time = higher shot
- **Reality**: Flight time also depends on:
  - Shot power/speed
  - Shot angle (steep vs flat)
  - Court position (front vs back)
- **Mitigation**: Group by shot type and court position if available

### 3. **Effectiveness Context**
- **Question**: Should we consider:
  - Opponent's incoming shot quality? (already in tempo_events as `incoming_eff`)
  - Rally context (score, rally length)?
  - Opponent's response quality?
- **Recommendation**: Start simple (effectiveness vs flight_time), add context later if needed

### 4. **Missing Data Handling**
- **No opponent response**: Exclude (rally ended with clear/lift)
- **No effectiveness**: Exclude or use color band as proxy
- **Invalid flight times**: Filter outliers (>5s likely data error, <0.1s likely tracking error)

### 5. **Shot Type Granularity**
- **Current**: Separate clear types (forehand_clear vs forehand_clear_cross)
- **Question**: Should we aggregate (all forehand_clears together) or keep separate?
- **Recommendation**: Keep separate initially, allow aggregation in analysis

### 6. **Player-Specific vs Aggregate**
- **Question**: Should analysis be per-player or aggregate across both players?
- **Recommendation**: Both - per-player for personalized insights, aggregate for general patterns

### 7. **Effectiveness Bands vs Numeric**
- **Current**: Have both `effectiveness` (numeric) and `effectiveness_color` (band)
- **Question**: Which to use for correlation?
- **Recommendation**: Use numeric for correlation, bands for visualization

### 8. **Flight Time Bands**
- **Question**: How to define "high" vs "low" flight time?
- **Options**:
  - Absolute thresholds (e.g., >1.5s = high)
  - Relative (above/below median for that shot type)
  - Percentile-based (p25/p75)
- **Recommendation**: Start with relative (median split), add absolute thresholds as reference

## Questions to Resolve

1. **Flight time definition**: Pure shuttle travel or include opponent reaction?
   - **Current plan**: Use opponent's response_time_sec (includes reaction)
   - **Alternative**: Calculate from clear/lift frame to opponent's shot frame directly

2. **Shot filtering**: Include all clears/lifts or only defensive ones?
   - **Current plan**: All clears/lifts
   - **Alternative**: Filter by context (e.g., only when under pressure)

3. **Effectiveness source**: Use from tempo_events or recalculate?
   - **Current plan**: Use from tempo_events (already calculated)
   - **Alternative**: Recalculate with different rules

4. **Outlier handling**: How aggressive?
   - **Current plan**: Filter >5s and <0.1s
   - **Alternative**: Use IQR method (1.5 * IQR)

5. **Correlation method**: Pearson (linear) or Spearman (rank-based)?
   - **Current plan**: Pearson (assumes linear relationship)
   - **Alternative**: Spearman (more robust to outliers)

6. **Visualization needs**: What charts/graphs?
   - Scatter plot (effectiveness vs flight_time)
   - Box plots (effectiveness by flight_time bands)
   - Heatmap (shot type × flight_time band × effectiveness)
   - Time series (flight_time trends over match)

## Implementation Steps

1. ✅ Read tempo_events.csv
2. ✅ Filter for clear/lift shots
3. ✅ For each clear/lift, find next opponent response
4. ✅ Extract flight_time from opponent's response_time_sec
5. ✅ Calculate statistics and correlations
6. ✅ Generate CSV outputs
7. ✅ Generate JSON for frontend
8. ⏳ Add validation and error handling
9. ⏳ Add visualization code (if needed)

## Expected Insights

1. **Height-Effectiveness Correlation**
   - Do higher clears/lifts (longer flight time) lead to better effectiveness?
   - Is there an optimal flight time range?

2. **Shot Type Differences**
   - Do forehand clears behave differently than backhand clears?
   - Do cross shots have different patterns than straight shots?

3. **Player Patterns**
   - Does P0 have different height preferences than P1?
   - Are there consistent patterns across matches?

4. **Tactical Implications**
   - When should players hit higher vs lower?
   - What flight time leads to opponent errors?

## Next Steps

1. **Review this logic document** - Confirm approach and resolve questions
2. **Implement basic version** - Get data flowing
3. **Validate with sample data** - Check for logical errors
4. **Refine based on results** - Adjust thresholds and groupings
5. **Add visualizations** - Make insights actionable

