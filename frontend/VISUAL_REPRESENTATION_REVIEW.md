# Visual Representation Review - Current vs. Expected

## Current Implementation Status

### 1. Service → Receive (`sr`)
**StatsPanel (v1)**: ✅ Shows text with jump links for top patterns (P0 and P1)
**StatsPanelV2 (v2)**: ❌ **MISSING** - No graph appears when section expanded

### 2. Shot Effectiveness (`eff`)
**StatsPanel (v1)**: ✅ Shows:
- Most effective shots (green) by P0 and P1
- Most ineffective shots (red) by P0 and P1
- Forced errors (final shots) by P0 and P1  
- Unforced errors (final shots) by P0 and P1

**StatsPanelV2 (v2)**: ⚠️ **INCOMPLETE** - Only shows:
- Effective vs Ineffective (diverging bars)
- ❌ Missing: Forced/Unforced errors (these are under 'errors' section)

**Issue**: Shot effectiveness should contain BOTH effective/ineffective AND forced/unforced errors, but currently errors are separate.

### 3. Winners (`winners`)
**StatsPanel (v1)**: ✅ Shows top 4 winners by stroke for P0 and P1
**StatsPanelV2 (v2)**: ✅ Uses BarCompare component - consistent P0/P1 comparison

### 4. Errors (`errors`)
**StatsPanel (v1)**: ✅ Shows top 4 errors by stroke for P0 and P1
**StatsPanelV2 (v2)**: ⚠️ Shows forced vs unforced (diverging bars) - but this data comes from effectiveness CSV, not the errors CSV

**Issue**: There's confusion - StatsPanel shows errors from `p0Errors`/`p1Errors` CSVs, but StatsPanelV2 shows errors from `effectiveness` CSV (forced/unforced).

### 5. Zones (`zones`)
**StatsPanel (v1)**: ✅ Shows most effective/ineffective corners with jump links
**StatsPanelV2 (v2)**: ✅ Shows heatmap - consistent

---

## Identified Inconsistencies

1. **Service → Receive**: Not implemented in v2
2. **Shot Effectiveness**: Should contain 4 subsections:
   - Effective shots (P0)
   - Ineffective shots (P0)
   - Forced errors (P0)
   - Unforced errors (P0)
   - Same for P1
3. **Errors section**: Currently showing forced/unforced from effectiveness CSV, but should show errors from errors CSV files OR clarify the distinction
4. **Data source mismatch**: StatsPanel uses separate error CSVs, StatsPanelV2 uses effectiveness CSV for errors

---

## Proposed Structure

### Section 1: Service → Receive
- **Visualization**: Sankey-style flow diagram or matrix showing Serve → Receive patterns
- **Data**: `p0SrPatterns`, `p1SrPatterns`
- **Show**: Top patterns as flow from serve to receive

### Section 2: Shot Effectiveness (Combined)
- **Visualization**: Multi-part view:
  - **Part 1**: Effective vs Ineffective (diverging bars) - current non-terminal shots
  - **Part 2**: Forced vs Unforced Errors (diverging bars) - terminal error shots
- **Data**: `effectiveness` CSV filtered appropriately
- **Show**: P0 and P1 side-by-side with toggle

### Section 3: Winners
- **Visualization**: BarCompare (current implementation) ✅
- **Data**: `p0Winners`, `p1Winners`
- **Show**: Top winners by stroke for P0 and P1

### Section 4: Errors  
- **Visualization**: BarCompare (similar to winners)
- **Data**: `p0Errors`, `p1Errors`
- **Show**: Top errors by stroke for P0 and P1 (from dedicated errors CSV)

---

## Questions to Clarify

1. Should "Shot Effectiveness" section show:
   - Effective/Ineffective shots (non-terminal) AND Forced/Unforced errors (terminal) together?
   - Or keep them separate?

2. For "Errors" section - should it use:
   - Dedicated errors CSV files (`p0Errors`, `p1Errors`)?
   - Or the forced/unforced errors from effectiveness CSV?

3. Service → Receive visualization preference:
   - Sankey flow diagram?
   - Matrix/heatmap (serve type × receive type)?
   - Simple bar chart showing pattern frequencies?
