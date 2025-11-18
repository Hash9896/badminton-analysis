# 3-Shot Sequence Visualization Proposal

## Current Data Structure

**CSV Columns**:
- `SequenceShots`: The shot sequence (e.g., "serve_middle -> forehand_dribble -> forehand_netkeep_cross -> forehand_lift_cross")
- `Count`: Frequency of occurrence
- `InstancesFrames`: Frame references (e.g., "First22210-Target22289|First62283-Target62360")

**Current Display**:
- Simple text list showing sequence and jump links
- Top 10 sequences shown

---

## Visualization Options

### Option 1: **Sankey Flow Diagram** (Recommended) ⭐
**Visualization**: Flow diagram showing shot-to-shot transitions

**Layout**:
```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Serve     │ ───> │   Receive   │ ───> │   Target    │
│  (middle)   │      │ (dribble)   │      │  (netkeep)  │
│   [50%]     │      │   [50%]     │      │   [50%]     │
└─────────────┘      └─────────────┘      └─────────────┘
```

**Pros**:
- ✅ Visual flow representation - shows sequence progression
- ✅ Natural for sequential data
- ✅ Can show multiple sequences side-by-side
- ✅ Width/color can represent frequency
- ✅ Similar to Service→Receive (consistent UX)

**Cons**:
- ⚠️ Can get complex with many sequences
- ⚠️ May need filtering/top-N view

**Implementation**:
- Use same Sankey component as Service→Receive
- Show top 5-8 sequences
- Width of flow = count
- Click to jump to instances

---

### Option 2: **Node Graph / Network Diagram**
**Visualization**: Nodes (shots) connected by edges (transitions)

**Layout**:
```
    [serve_middle] ───> [forehand_dribble] ───> [forehand_netkeep]
           │                    │                       │
           └────────────────────┴──────────────────────┘
                        [forehand_lift]
```

**Pros**:
- ✅ Shows all possible paths
- ✅ Good for discovering patterns
- ✅ Can highlight frequent paths

**Cons**:
- ❌ Can get cluttered with many sequences
- ❌ More complex to implement
- ❌ May not scale well

---

### Option 3: **Hierarchical Tree**
**Visualization**: Tree structure showing sequence branches

**Layout**:
```
┌─ serve_middle ─────────────────┐
│                                 │
├─> forehand_dribble ────────────┤
│                                 │
│  ├─> forehand_netkeep [count:3] │
│  └─> backhand_netkeep [count:2] │
│                                 │
└─> backhand_netkeep ────────────┘
```

**Pros**:
- ✅ Clear hierarchy
- ✅ Shows branching patterns
- ✅ Easy to see alternatives

**Cons**:
- ⚠️ Takes vertical space
- ⚠️ Less compact than flow diagram

---

### Option 4: **Bar Chart with Sequence Labels**
**Visualization**: Horizontal bar chart, one bar per sequence

**Layout**:
```
serve_middle → forehand_dribble → forehand_netkeep
[████████████████████] 5 instances

serve_middle → backhand_netkeep → backhand_lift
[████████████] 3 instances
```

**Pros**:
- ✅ Simple and clear
- ✅ Easy to compare frequencies
- ✅ Compact display

**Cons**:
- ⚠️ Less visual than flow diagram
- ⚠️ Doesn't emphasize sequential nature

---

### Option 5: **Timeline Strip with Sequence Segments**
**Visualization**: Timeline showing when sequences occur, with segments showing each shot

**Layout**:
```
Timeline:  ────[serve][receive][target]───[serve][receive][target]───
           00:10                        02:30
```

**Pros**:
- ✅ Shows temporal context
- ✅ Integrates with existing timeline markers
- ✅ Shows distribution across match

**Cons**:
- ⚠️ May be hard to distinguish sequences
- ⚠️ Needs clustering for overlapping sequences

---

## Recommended Approach: **Option 1 - Enhanced Sankey Flow**

### Design Details

**Component**: `SequenceFlowDiagram`
- Shows top 5-8 most frequent sequences
- Each sequence = one flow path
- Width of path = count (normalized)
- Color coding by sequence type (serve type, target shot type)
- Clickable to jump to instances

**Visual Layout**:
```
Top 3-Shot Sequences

┌─────────────────────────────────────────────────┐
│                                                 │
│  [serve_middle] ────> [forehand_dribble] ────> │
│        │                      │                │
│        │                      └───> [netkeep]  │
│        │                                      [3]│
│        │                                         │
│        └───> [backhand_netkeep] ────> [lift]   │
│                         [2]                     │
└─────────────────────────────────────────────────┘
```

**Features**:
1. **Top Sequences View**: Show most frequent sequences
2. **Frequency Bars**: Width represents count
3. **Color Coding**: 
   - By serve type (serve_middle = blue, serve_wide = green, etc.)
   - Or by target shot category (Attacking = red, Placement = blue, etc.)
4. **Instance Markers**: Small markers below showing instance count
5. **Click to Jump**: Click on flow or instance markers to jump to video
6. **Player Toggle**: Show P0 sequences, P1 sequences, or both

**Alternative Simple View**:
- If Sankey is too complex, use **Option 4 (Bar Chart)** with sequence as labels
- More compact, easier to read
- Still shows frequency clearly

---

## Implementation Considerations

### Data Parsing
- Parse `SequenceShots` to extract individual shots
- Parse `InstancesFrames` to get frame ranges
- Extract first frame and target frame for each instance

### Integration
- Add to StatsPanelV2 when `activeSection === 'threeShot'`
- Show below video (same as other graphs)
- Keep summary list in right panel

### Color Coding Options
1. **By First Shot (Serve)**: Different colors for serve types
2. **By Target Shot**: Different colors for target shot categories
3. **By Frequency**: Gradient from low to high count
4. **Single Color**: Use section color (e.g., purple for sequences)

---

## Recommendation

I recommend **Option 1 (Sankey Flow)** with **Option 4 (Bar Chart)** as fallback:

**Primary**: Sankey flow diagram (reuse existing component from Service→Receive)
- Shows flow naturally
- Consistent with existing UX
- Most visually appealing

**Fallback**: If Sankey is too complex, use horizontal bar chart
- Simpler implementation
- Still clear and readable
- Faster to render

**Both options should**:
- Show top 5-8 sequences
- Display count for each
- Be clickable to jump to instances
- Support player toggle (P0/P1/Both)
- Use timeline markers below video for instances

Which approach would you prefer? I can implement either option.
