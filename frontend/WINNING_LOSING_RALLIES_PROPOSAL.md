# Winning & Losing Rallies - Visualization Proposal

## Current Implementation (UI v1)
- **Structure**: Grouped by last shot category (Attacking, Defense, NetBattle, Placement, Reset, Other)
- **Data**: Each rally has: `GameNumber`, `RallyNumber`, `StartFrame`, `EndFrame`, `LastShot`
- **Display**: Text lists grouped by category with clickable time chips

## Available Data Fields
From the code, each rally CSV row likely contains:
- `GameNumber`, `RallyNumber` 
- `StartFrame`, `EndFrame` (can calculate duration)
- `LastShot` / `LastShotName` / `LastShotType` (shot category bucket)
- Possibly: `Winner`, `Loser`, `Phase`, etc.

## Proposed Visualizations for UI v2

### Option 1: **Stacked Bar Chart - Last Shot Categories** (Recommended)
**Purpose**: Show which shot categories most often end winning/losing rallies

**Visualization**:
- X-axis: Shot categories (Attacking, Defense, NetBattle, Placement, Reset, Other)
- Y-axis: Count of rallies
- Two grouped bars per category: "Winning" (green) and "Losing" (red)
- Split by P0 and P1
- Click bars to jump to representative rallies

**Data Processing**:
- Group winning/losing rallies by last shot category
- Count occurrences per category
- Show top categories (limit to top 5-6)

**Layout**:
```
┌─────────────────────────────────────┐
│ Winning vs Losing Rallies          │
│ (by Last Shot Category)             │
├─────────────────────────────────────┤
│ P0                                  │
│ [Stacked bars: Winning | Losing]    │
│                                     │
│ P1                                  │
│ [Stacked bars: Winning | Losing]   │
└─────────────────────────────────────┘
```

### Option 2: **Rally Duration Distribution**
**Purpose**: Show if winning rallies are shorter/longer than losing rallies

**Visualization**:
- X-axis: Rally duration buckets (0-5s, 5-10s, 10-20s, 20-30s, 30s+)
- Y-axis: Count of rallies
- Grouped bars: Winning vs Losing
- Side-by-side: P0 and P1

**Insight**: Do winning rallies tend to be shorter (quick points) or longer (grind it out)?

### Option 3: **Timeline Strip Chart**
**Purpose**: Show rally outcomes across match time

**Visualization**:
- X-axis: Match time (from start to end)
- Y-axis: Two rows (P0 wins, P1 wins)
- Colored dots/bars: Green for winning rallies, Red for losing rallies
- Hover shows rally details (duration, last shot, game/rally number)
- Click to jump to video

**Insight**: Visual pattern of when each player wins/loses

### Option 4: **Pie/Donut Chart - Category Distribution**
**Purpose**: Quick visual of what shot types end rallies

**Visualization**:
- Pie/donut chart for winning rallies (by last shot category)
- Separate pie/donut for losing rallies
- Compare the two to see patterns

---

## Recommended Combination

I recommend **Option 1 (Stacked Bar)** as the primary visualization because:
1. ✅ Shows the most actionable insight (which shot types end rallies)
2. ✅ Directly related to coaching (what works/doesn't work)
3. ✅ Clear comparison between winning/losing patterns
4. ✅ Easy to understand at a glance
5. ✅ Supports player toggle (Both/P0/P1)

**Optional Addition**: Option 2 (Duration Distribution) as a secondary view if there's space, showing temporal patterns.

---

## Implementation Details

### Section Structure
- **Two separate sections**: "Winning rallies" (`winRallies`) and "Losing rallies" (`loseRallies`)
- Each section shows visualization when expanded
- Player toggle applies to both sections

### Data Processing
1. Parse rally CSVs (`p0WinningRallies`, `p1WinningRallies`, `p0LosingRallies`, `p1LosingRallies`)
2. Categorize last shot using existing `mapShotToBucket` function
3. Count rallies per category per player
4. Calculate rally duration: `(EndFrame - StartFrame) / fps`

### Visual Component
- New component: `RallyCategoryStacked` or reuse/extend existing bar components
- Color scheme: Green for winning, Red for losing
- Interactive: Click bar segment to jump to representative rally

---

## Questions for Discussion

1. Should we combine "Winning" and "Losing" into one graph (stacked bars) or keep them separate sections?
2. Should we show rally duration as a secondary metric (tooltip or separate mini-chart)?
3. Do we want timeline visualization as well, or is category distribution enough?
4. Should we show total rally counts per player as summary stats?

---

## Next Steps (After Approval)

1. Implement data parsing for rally CSVs
2. Create `RallyCategoryStacked` component
3. Add to `StatsPanelV2` for `winRallies` and `loseRallies` sections
4. Ensure click-to-video functionality works
5. Test with sample data
