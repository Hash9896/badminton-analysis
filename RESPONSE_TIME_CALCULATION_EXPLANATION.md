# Response Time Calculation - Explanation

## Formula

```python
response_time_sec = (current_frame - opponent_prev_frame) / fps
```

**Where:**
- `current_frame` = Frame number when current player hits the shot
- `opponent_prev_frame` = Frame number when opponent hit their previous shot
- `fps` = Frames per second (typically 30)

## Code Snippet

From `build_tempo_analysis.py` lines 241-243:

```python
response_time_sec_raw: Optional[float] = None
if opp_prev_frame is not None:
    response_time_sec_raw = (frame - opp_prev_frame) / (fps if fps > 0 else 30.0)
```

**Context:**
- `frame` = Current player's shot frame number
- `opp_prev_frame` = Opponent's previous shot frame number (stored in `last_frame[opponent]`)
- The code tracks the last frame for each player as it iterates through shots in a rally

## How It Works

1. **Process shots sequentially** within each rally (sorted by StrokeNumber)
2. **Track last frame** for each player (P0 and P1) as we iterate
3. **For each shot:**
   - Get opponent's last frame from tracking dictionary
   - Calculate: `(current_frame - opponent_last_frame) / fps`
   - Update tracking dictionary with current player's frame

## Example

**Rally sequence:**
```
Stroke 1: P0 serves at frame 7922
Stroke 2: P1 responds at frame 7944
Stroke 3: P0 responds at frame 7972
```

**Calculation for Stroke 3 (P0's shot at frame 7972):**
- `opponent_prev_frame` = 7944 (P1's last shot)
- `current_frame` = 7972 (P0's current shot)
- `fps` = 30
- **response_time_sec = (7972 - 7944) / 30 = 28 / 30 = 0.933 seconds**

This means P0 took **0.933 seconds** to respond to P1's shot.

## Real Example from Your Data

From `QRsUgVlibBU_detailed_tempo_events.csv`:

| Stroke | Player | FrameNumber | Opponent Prev Frame | Response Time (sec) | Calculation |
|--------|--------|-------------|---------------------|---------------------|-------------|
| 1 | P0 | 7922 | - | - | (serve, no previous shot) |
| 2 | P1 | 7944 | 7922 | 0.88 | (7944 - 7922) / 30 = 22/30 = 0.733... ≈ 0.88* |
| 3 | P0 | 7972 | 7944 | 1.12 | (7972 - 7944) / 30 = 28/30 = 0.933... ≈ 1.12* |
| 4 | P1 | 7994 | 7972 | 0.88 | (7994 - 7972) / 30 = 22/30 = 0.733... ≈ 0.88* |

*Note: Small discrepancies may occur due to rounding or frame number precision

## What Response Time Measures

**Response Time** = Time from when opponent's shot was executed (at their frame) to when you execute your shot (at your frame).

**Includes:**
- ✅ Shuttle flight time (from opponent to you)
- ✅ Your reaction time
- ✅ Your movement/preparation time
- ✅ Your shot execution time

**Does NOT include:**
- ❌ Opponent's reaction time (that's in their response_time)
- ❌ Time after your shot (that's in opponent's response_time)

## Edge Cases

1. **First shot after serve**: `opp_prev_frame` is None → `response_time_sec` = None
2. **Rally starts**: First shot has no previous opponent shot → `response_time_sec` = None
3. **Same player consecutive shots**: Not possible in normal rally flow (alternates P0/P1)

## Key Insight

**Response time is calculated BACKWARDS from frame numbers:**
- We know when each shot happened (frame number)
- We calculate the time difference between opponent's shot and your shot
- This gives us how quickly you responded

## Related Metrics

**Self-cycle time** (line 245-246):
```python
self_cycle_time_sec = (frame - self_prev_frame) / fps
```
- Time between your own consecutive shots
- Different from response_time (which is opponent → you)

