# Zone Effectiveness Visualization Proposal

## Current Data Structure

From `zone_effectiveness_top_vs_bottom.csv`:
- **Player**: P0 or P1
- **ZoneType**: `most_effective` or `most_ineffective`
- **AnchorHittingZone**: `back_right`, `middle_left`, `middle_right`, `front_left`, `front_right`, `back_left`, `middle_center`
- **AnchorLandingPosition**: `back court`, `mid court`, `front court`
- **Uses**: Count of shots in that zone
- **AvgEffectiveness**: Average effectiveness percentage
- **Shots**: Comma-separated list of shot types
- **AllFrames**: Pipe-separated frame references (e.g., `G1-R6-F9836|G1-R6-F9892`)

## Zone Layout (Badminton Court)

```
        [Net]
─────────────────
│     │  │     │
│ FL  │MC│ FR  │  Front court
│     │  │     │
├─────┼──┼─────┤
│     │  │     │
│ ML  │  │ MR  │  Mid court
│     │  │     │
├─────┼──┼─────┤
│     │  │     │
│ BL  │  │ BR  │  Back court
│     │  │     │
─────────────────
```

**Zones**:
- **FL**: front_left
- **FR**: front_right
- **MC**: middle_center
- **ML**: middle_left
- **MR**: middle_right
- **BL**: back_left
- **BR**: back_right

## Current Implementation Issues

1. Uses generic 3x3 grid that doesn't match badminton court zones
2. Doesn't show effectiveness percentage clearly
3. Doesn't distinguish between effective/ineffective zones visually
4. Doesn't show landing position information
5. No clickable examples to jump to video

## Proposed Visualizations

### Option 1: **Court Heatmap with Dual View** (Recommended)
**Purpose**: Show most effective and most ineffective zones on same court view

**Visualization**:
- Badminton court layout with 7 zones properly positioned
- **Green intensity** for effective zones (brighter = more effective)
- **Red intensity** for ineffective zones (brighter = more ineffective)
- Show both on same court (overlay or side-by-side)
- Click zones to show jump links to examples

**Data Display**:
- Zone label (e.g., "back_right")
- Uses count
- AvgEffectiveness percentage
- Clickable examples from AllFrames

**Layout**:
```
┌─────────────────────────────────────┐
│ Most Effective Zones                │
│ [Court with green zones]            │
│                                     │
│ Most Ineffective Zones              │
│ [Court with red zones]              │
└─────────────────────────────────────┘
```

### Option 2: **Split Court Comparison**
**Purpose**: Compare effective vs ineffective side-by-side

**Visualization**:
- Two court views: Left = Effective, Right = Ineffective
- Color intensity based on Uses count or AvgEffectiveness
- Show zone labels, uses, and effectiveness % in tooltips/labels

### Option 3: **Single Court with Color Gradient**
**Purpose**: Single court showing effectiveness gradient

**Visualization**:
- One court with all zones
- Green = effective zones (darker = more uses, higher effectiveness)
- Red = ineffective zones (darker = more uses, lower effectiveness)
- Neutral gray for zones not in top/bottom

## Recommended Implementation

**Option 1 + Enhanced Details**

### Visual Components:
1. **Badminton Court SVG**:
   - Accurate zone positioning
   - Net line at top
   - 3 rows (front, mid, back) × 3 columns (left, center, right)
   - 7 actual zones (excluding center for front/back rows)

2. **Zone Cells**:
   - Color based on effectiveness:
     - Green (effective): Intensity based on AvgEffectiveness or Uses
     - Red (ineffective): Intensity based on how low effectiveness is
   - Border highlight for zones with data
   - Hover shows: Zone name, Uses, AvgEffectiveness, Shots list

3. **Dual View**:
   - Top section: "Most Effective Zones" (green)
   - Bottom section: "Most Ineffective Zones" (red)
   - Each shows all zones, but highlights only the relevant ones

4. **Clickable Examples**:
   - Below each court view
   - Time chips from AllFrames
   - Click to jump to video

### Data Processing:
1. Parse zone CSV for each player
2. Extract: Zone, Type (effective/ineffective), Uses, AvgEffectiveness, AllFrames
3. Build zone map with effectiveness data
4. Parse frame references from AllFrames column

## Questions to Clarify

1. Should we show **both** effective and ineffective zones on the same court view, or separate?
2. What should color intensity represent?
   - AvgEffectiveness percentage?
   - Uses count?
   - Combination of both?
3. Should we show all zones (even empty ones) or only zones with data?
4. Do we want a summary metric (total uses, average effectiveness) displayed?

---

## Next Steps (After Approval)

1. Create proper BadmintonCourt SVG component with 7 zones
2. Parse zone data with Uses and AvgEffectiveness
3. Implement color mapping (green for effective, red for ineffective)
4. Add clickable examples from AllFrames
5. Support player toggle (Both/P0/P1)
6. Test with sample data
