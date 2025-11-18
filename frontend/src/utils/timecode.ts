export type ParsedAnchor = {
  startSec: number;
  endSec?: number;
  label: string;
  tooltip: string;
};

export function formatMs(ms: number): string {
  if (!Number.isFinite(ms)) return '00:00';
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60).toString().padStart(2, '0');
  const s = (totalSec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

export function parseFrameAnchor(anchor: string, fps: number, videoDurationSec?: number): ParsedAnchor | null {
  const a = (anchor || '').trim();
  if (!a) return null;
  const safeFps = Number.isFinite(fps) && fps > 0 ? fps : 30;
  const dur: number | undefined = Number.isFinite(videoDurationSec as number) && (videoDurationSec as number) > 0 ? (videoDurationSec as number) : undefined;

  // Pattern 1: numeric range "start-end"
  const mRange = a.match(/^(\d+)-(\d+)$/);
  if (mRange) {
    const startF = parseInt(mRange[1], 10);
    const endF = parseInt(mRange[2], 10);
    let startSec = startF / safeFps - 2; // default padding -2s
    let endSec = endF / safeFps + 2;     // default padding +2s
    if (dur != null) {
      startSec = clamp(startSec, 0, dur);
      endSec = clamp(endSec, 0, dur);
    } else {
      startSec = Math.max(0, startSec);
      endSec = Math.max(startSec, endSec);
    }
    return {
      startSec,
      endSec,
      label: `[${formatMs(startSec * 1000)}]`,
      tooltip: `${startF}-${endF} (±2s) @${fps}fps`,
    };
  }

  // Pattern 2: rally anchor "Gx-Ry-Fz"
  const mGRF = a.match(/^G\d+-R\d+-F(\d+)$/i);
  if (mGRF) {
    const f = parseInt(mGRF[1], 10);
    let startSec = f / safeFps - 2; // default padding -2s
    if (dur != null) startSec = clamp(startSec, 0, dur);
    else startSec = Math.max(0, startSec);
    const endSec = startSec + 4;
    return {
      startSec,
      endSec,
      label: `[${formatMs(startSec * 1000)}]`,
      tooltip: `${a} (±2s) @${fps}fps`,
    };
  }

  // Pattern 3: FirstN-TargetM pair
  const mFirstTarget = a.match(/^First(\d+)-Target(\d+)$/i);
  if (mFirstTarget) {
    const firstF = parseInt(mFirstTarget[1], 10);
    const targetF = parseInt(mFirstTarget[2], 10);
    let startSec = firstF / safeFps - 2; // default padding -2s
    let endSec = targetF / safeFps + 2;  // default padding +2s
    if (dur != null) {
      startSec = clamp(startSec, 0, dur);
      endSec = clamp(endSec, 0, dur);
    } else {
      startSec = Math.max(0, startSec);
      endSec = Math.max(startSec, endSec);
    }
    return {
      startSec,
      endSec,
      label: `[${formatMs(startSec * 1000)}]`,
      tooltip: `First${firstF}-Target${targetF} (±2s) @${fps}fps`,
    };
  }

  // Fallback: single number treated as frame
  const mSingle = a.match(/^(\d+)$/);
  if (mSingle) {
    const f = parseInt(mSingle[1], 10);
    let startSec = f / safeFps - 2;
    if (dur != null) startSec = clamp(startSec, 0, dur);
    else startSec = Math.max(0, startSec);
    const endSec = startSec + 4;
    return {
      startSec,
      endSec,
      label: `[${formatMs(startSec * 1000)}]`,
      tooltip: `${f} (±2s) @${fps}fps`,
    };
  }

  // Last-chance fallback: extract last number and treat as frame
  const nums = a.match(/(\d+)/g);
  if (nums && nums.length > 0) {
    const f = parseInt(nums[nums.length - 1], 10);
    if (Number.isFinite(f)) {
      let startSec = f / safeFps - 2;
      if (dur != null) startSec = clamp(startSec, 0, dur);
      else startSec = Math.max(0, startSec);
      const endSec = startSec + 4;
      return {
        startSec,
        endSec,
        label: `[${formatMs(startSec * 1000)}]`,
        tooltip: `${a} → F${f} (±2s) @${fps}fps`,
      };
    }
  }

  return null;
}


