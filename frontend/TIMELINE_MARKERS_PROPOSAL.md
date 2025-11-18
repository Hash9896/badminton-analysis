# Timeline Markers on Video Player - Proposal

## Current Implementation
- Each stat section shows jump links as clickable chips (e.g., `[00:15]`, `[01:23]`)
- Chips are displayed in lists, sometimes quite long
- Takes up vertical space
- Multiple clicks to find specific moments

## Proposed: Timeline Markers

### Option 1: **Custom Timeline Overlay Below Video** (Recommended)
**Visualization**:
- Horizontal timeline strip positioned below video controls
- Shows match duration from start to end
- Colored markers at each instance position
- Click markers to jump to that time
- Markers can be stacked/clustered when multiple instances at same time

**Pros**:
- ✅ Much cleaner UI - no long lists of chips
- ✅ Visual pattern recognition - see clusters, distribution across match
- ✅ At-a-glance view of all instances
- ✅ Standard video player UX pattern
- ✅ Takes less vertical space
- ✅ Better for understanding temporal patterns

**Cons**:
- ⚠️ Need to calculate video total duration
- ⚠️ May need to handle overlapping markers (stacking/clustering)
- ⚠️ Timeline might be small on smaller screens

**Layout**:
```
┌─────────────────────────────┐
│        [Video Player]       │
│     [Video Controls]        │
├─────────────────────────────┤
│ ──────────────●────●──●──── │  ← Timeline with markers
│  00:00      01:23  02:45    │
└─────────────────────────────┘
```

### Option 2: **Native Timeline Integration**
**Visualization**:
- Try to add markers to browser's native video timeline
- Problem: HTML5 video controls are not easily customizable
- Would require custom video controls entirely

**Pros**:
- Native feel

**Cons**:
- ❌ Browser limitations - native controls are hard to modify
- ❌ Would need to build custom video player from scratch
- ❌ More complex implementation
- ❌ Accessibility concerns

### Option 3: **Hybrid: Timeline + Expandable List**
**Visualization**:
- Timeline strip shows markers
- Click on timeline region to expand and see list of instances in that region
- Or toggle between timeline view and list view

**Pros**:
- ✅ Visual overview with detailed drill-down
- ✅ Best of both worlds

**Cons**:
- ⚠️ More complex interaction
- ⚠️ May be overkill

---

## Recommended Implementation: Option 1 (Timeline Overlay)

### Visual Design

**Timeline Strip Component**:
- Width: Matches video width
- Height: ~40-50px
- Background: Dark (matches video area)
- Time axis: Shows major time markers (0:00, 1:00, 2:00, etc.)
- Markers: 
  - Small colored dots/lines at instance positions
  - Color coding per subcategory (e.g., different colors for different shot types)
  - Hover shows details (shot type, frame number, time)
  - Click jumps to video

**Marker Types by Section**:
1. **Winners**: Green dots - one per winner instance
2. **Errors**: Red dots - one per error instance  
3. **Shot Effectiveness (Effective)**: Green markers
4. **Shot Effectiveness (Ineffective)**: Red markers
5. **Shot Effectiveness (Forced/Unforced Errors)**: Orange/Yellow markers
6. **Service→Receive**: Blue markers at serve-receive moments
7. **Zone Effectiveness**: Colored by zone type

**Marker Clustering**:
- If multiple instances at same time: show stacked indicator or small vertical lines
- Tooltip shows count: "5 instances at 01:23"

### Example Visual

```
Winners Timeline (P0):
│─────────────────●────────●───●─────────●────│
 00:00          00:45   01:23  02:10  03:30
                  ▲
              Hover: "forehand_smash @ 00:45:123"
              Click: Jump to 00:45
```

### Implementation Details

**Component**: `VideoTimelineMarker`
- Props: `instances: Array<{time: number, label: string, category?: string}>, videoDuration: number, onJump: (time)=>void`
- Calculates marker positions based on time
- Handles clustering when multiple instances overlap
- Color codes by category/section

**Integration**:
- Show below video when a stats section is expanded
- Positioned right under video controls
- Scrollable if timeline is wider than container
- Responsive width (matches video)

---

## UX Comparison

### Current (Jump Links):
```
Winners (top 4 by stroke)
  forehand_smash (12)
    [00:15] [00:45] [01:23] [02:10] [03:30] ...
  overhead_smash (8)
    [00:30] [01:45] [02:20] [03:15] ...
```
- **Pros**: Explicit, clear labels
- **Cons**: Takes space, harder to see patterns, many clicks

### Proposed (Timeline):
```
Winners (top 4 by stroke)
  ──────────●─────●──●────●──●─────│
   00:00  00:30  01:00  02:00  03:00
  
  forehand_smash: [12 instances]
  overhead_smash: [8 instances]
```
- **Pros**: Visual patterns, space efficient, temporal context
- **Cons**: Need hover/click to see details, less explicit labels

---

## Decision Points

1. **Replace or complement chips?**
   - Option A: Replace chips entirely with timeline
   - Option B: Show timeline + keep small summary list (shot type, count)
   - Option C: Toggle between timeline and list view

2. **Marker density handling?**
   - Clustering algorithm when many instances close together?
   - Zoom in/out for timeline?
   - Show as bands instead of points?

3. **Multiple subcategories in one section?**
   - Different colors per subcategory (e.g., different shot types)?
   - Stacked timeline strips (one per subcategory)?
   - Toggle which subcategories to show?

4. **Integration with existing graphs?**
   - Timeline below video (where jump links currently are)?
   - Replace jump links section entirely?
   - Show alongside graphs in StatsPanelV2 area?

---

## Recommendation

I recommend **Option A with enhancement**: 
- Replace jump link chips with interactive timeline markers
- Keep summary counts per subcategory (e.g., "forehand_smash: 12 instances")
- Add hover tooltips showing details
- Use color coding to differentiate subcategories
- Position timeline directly below video controls

**Benefits**:
- Much cleaner UI
- Better pattern recognition
- More professional look
- Better use of space
- Standard UX pattern users expect

**Implementation effort**: Medium
- Need to create timeline component
- Calculate positions from frame numbers → time
- Handle clustering/overlapping
- Color coding system
- Video duration calculation

Would you like me to proceed with this approach?
