import type { RallyTempoPayload, RallyTempoShot } from '../components/RallyTempoVisualization';
import type { DynamicsPayload } from '../components/RallyDynamics';
import type { RallyMetricsRow } from '../components/RallyPace';

export type LengthTag = 'quick' | 'standard' | 'grind';
export type TempoStoryTag = 'p0_dominant' | 'p1_dominant' | 'swing' | 'neutral';
export type EffectivenessTag = 'surge' | 'clutch_save' | 'collapse' | 'scramble' | 'steady';
export type ClutchTag = 'final_rally' | 'run_stopper' | 'momentum' | 'normal';

export type RallyTags = {
  length: LengthTag;
  tempo: TempoStoryTag;
  effectiveness: EffectivenessTag;
  clutch: ClutchTag;
};

export const LENGTH_FILTERS: Array<{ value: 'all' | LengthTag; label: string }> = [
  { value: 'all', label: 'All lengths' },
  { value: 'quick', label: 'Quick (≤4 shots)' },
  { value: 'standard', label: 'Standard (5-12)' },
  { value: 'grind', label: 'Grind (13+)' },
];

export const TEMPO_FILTERS: Array<{ value: 'all' | TempoStoryTag; label: string }> = [
  { value: 'all', label: 'All tempo stories' },
  { value: 'p0_dominant', label: 'P0 dominant' },
  { value: 'p1_dominant', label: 'P1 dominant' },
  { value: 'swing', label: 'Momentum swings' },
  { value: 'neutral', label: 'Neutral tug-of-war' },
];

export const EFFECTIVENESS_FILTERS: Array<{ value: 'all' | EffectivenessTag; label: string }> = [
  { value: 'all', label: 'All effectiveness arcs' },
  { value: 'surge', label: 'Surge to win' },
  { value: 'clutch_save', label: 'Clutch save' },
  { value: 'collapse', label: 'Collapse' },
  { value: 'scramble', label: 'Low-quality scramble' },
  { value: 'steady', label: 'Steady' },
];

export const CLUTCH_FILTERS: Array<{ value: 'all' | ClutchTag; label: string }> = [
  { value: 'all', label: 'All clutch contexts' },
  { value: 'final_rally', label: 'Final rally' },
  { value: 'run_stopper', label: 'Run stopper (long streak)' },
  { value: 'momentum', label: 'Momentum swing' },
  { value: 'normal', label: 'Standard' },
];

type CombinedShot = RallyTempoShot & { player: 'P0' | 'P1' };

type MetricsSummary = {
  longestRun: number;
};

export function resolveTempoDominance(
  player: 'P0' | 'P1' | string,
  tempoControl?: string
): { dominant: 'P0' | 'P1' | null; label: string } {
  const control = String(tempoControl || '').toLowerCase();
  const shooter = player === 'P0' || player === 'P1' ? player : null;
  let dominant: 'P0' | 'P1' | null = null;
  if (control.startsWith('player') && shooter) {
    dominant = shooter;
  } else if (control.startsWith('opponent') && shooter) {
    dominant = shooter === 'P0' ? 'P1' : 'P0';
  }
  let label: string;
  if (dominant) {
    label = `${dominant} dominant`;
  } else if (control) {
    label = control === 'neutral' ? 'Neutral tempo' : control.replace(/_/g, ' ');
  } else {
    label = 'Neutral tempo';
  }
  return { dominant, label };
}

const getLengthTag = (shots: number): LengthTag => {
  if (!Number.isFinite(shots)) return 'standard';
  if (shots <= 4) return 'quick';
  if (shots <= 12) return 'standard';
  return 'grind';
};

const combineShots = (rally: RallyTempoPayload['rallies'][number]): CombinedShot[] => {
  const withPlayer = (shots: RallyTempoShot[], player: 'P0' | 'P1') =>
    shots.map(shot => ({ ...shot, player }));
  return [
    ...withPlayer(rally.p0_shots || [], 'P0'),
    ...withPlayer(rally.p1_shots || [], 'P1'),
  ].sort((a, b) => a.stroke_number - b.stroke_number);
};

const determineTempoTag = (shots: CombinedShot[]): TempoStoryTag => {
  if (!shots.length) return 'neutral';
  let p0 = 0;
  let p1 = 0;
  const sequence: Array<'P0' | 'P1'> = [];
  for (const shot of shots) {
    const info = resolveTempoDominance(shot.player, shot.tempo_control);
    if (info.dominant === 'P0') {
      p0 += 1;
      if (sequence[sequence.length - 1] !== 'P0') sequence.push('P0');
    } else if (info.dominant === 'P1') {
      p1 += 1;
      if (sequence[sequence.length - 1] !== 'P1') sequence.push('P1');
    }
  }
  const total = p0 + p1;
  if (total === 0) return 'neutral';
  const p0Share = p0 / total;
  if (p0Share >= 0.6) return 'p0_dominant';
  if (p0Share <= 0.4) return 'p1_dominant';
  const switches = sequence.length > 1 ? sequence.length - 1 : 0;
  if (switches >= 2) return 'swing';
  return 'neutral';
};

const averageSegment = (values: number[], segment: 'start' | 'mid' | 'end'): number | null => {
  if (!values.length) return null;
  const segSize = Math.max(1, Math.floor(values.length / 3));
  if (segment === 'start') {
    return values.slice(0, segSize).reduce((a, b) => a + b, 0) / segSize;
  }
  if (segment === 'mid') {
    const start = Math.floor((values.length - segSize) / 2);
    return values.slice(start, start + segSize).reduce((a, b) => a + b, 0) / segSize;
  }
  return values.slice(-segSize).reduce((a, b) => a + b, 0) / segSize;
};

const extractEffectValues = (
  dynRally: DynamicsPayload['rallies'][string] | undefined,
  player: 'P0' | 'P1'
): number[] => {
  if (!dynRally?.points) return [];
  return dynRally.points
    .filter(pt => {
      const shooter = (pt as any).Player ?? (pt as any).player;
      return shooter === player && Number.isFinite(pt.effectiveness);
    })
    .map(pt => Number(pt.effectiveness));
};

const determineEffectivenessTag = (
  rally: RallyTempoPayload['rallies'][number],
  dynRally: DynamicsPayload['rallies'][string] | undefined
): EffectivenessTag => {
  const winner = (rally.rally_winner || dynRally?.rally_winner || dynRally?.winner) as 'P0' | 'P1' | undefined;
  if (!winner) return 'steady';
  const loser = winner === 'P0' ? 'P1' : 'P0';

  const winnerVals = dynRally ? extractEffectValues(dynRally, winner) : combineShots(rally)
    .filter(s => s.player === winner && Number.isFinite(s.effectiveness))
    .map(s => Number(s.effectiveness));

  const loserVals = dynRally ? extractEffectValues(dynRally, loser) : combineShots(rally)
    .filter(s => s.player === loser && Number.isFinite(s.effectiveness))
    .map(s => Number(s.effectiveness));

  const totalVals = dynRally
    ? (
      dynRally.points?.filter(pt => Number.isFinite(pt.effectiveness)).map(pt => Number(pt.effectiveness)) ?? []
    )
    : combineShots(rally)
      .filter(s => Number.isFinite(s.effectiveness))
      .map(s => Number(s.effectiveness));

  if (!winnerVals.length && !loserVals.length) return 'steady';
  const winnerStart = averageSegment(winnerVals, 'start');
  const winnerMid = averageSegment(winnerVals, 'mid');
  const winnerEnd = averageSegment(winnerVals, 'end');
  const loserStart = averageSegment(loserVals, 'start');
  const loserMid = averageSegment(loserVals, 'mid');
  const loserEnd = averageSegment(loserVals, 'end');
  if (
    winnerStart != null &&
    winnerMid != null &&
    winnerEnd != null &&
    winnerStart < winnerMid &&
    winnerMid < winnerEnd
  ) {
    return 'surge';
  }
  if (
    loserStart != null &&
    loserMid != null &&
    loserEnd != null &&
    loserStart > loserMid &&
    loserMid > loserEnd
  ) {
    return 'collapse';
  }
  if (
    winnerStart != null &&
    winnerMid != null &&
    winnerEnd != null &&
    winnerStart > winnerMid &&
    winnerMid > winnerEnd
  ) {
    return 'clutch_save';
  }
  const overallAvg =
    totalVals.length > 0 ? totalVals.reduce((a, b) => a + b, 0) / totalVals.length : null;
  if ((overallAvg ?? 100) < 45 && (rally.total_shots ?? 0) >= 5) {
    return 'scramble';
  }
  return 'steady';
};

const determineClutchTag = (
  rally: RallyTempoPayload['rallies'][number],
  tempoTag: TempoStoryTag,
  effectTag: EffectivenessTag,
  metrics: MetricsSummary | undefined,
  isFinalRally: boolean
): ClutchTag => {
  if (isFinalRally) return 'final_rally';
  if ((metrics?.longestRun ?? 0) >= 4) return 'run_stopper';
  if (tempoTag === 'swing' && (effectTag === 'surge' || effectTag === 'clutch_save' || effectTag === 'collapse')) {
    return 'momentum';
  }
  return 'normal';
};

const buildMetricsMap = (rows: RallyMetricsRow[]): Record<string, MetricsSummary> => {
  const map: Record<string, MetricsSummary> = {};
  for (const row of rows || []) {
    if (!row.rally_id) continue;
    if (!map[row.rally_id]) {
      map[row.rally_id] = { longestRun: 0 };
    }
    map[row.rally_id].longestRun = Math.max(map[row.rally_id].longestRun, row.longest_run || 0);
  }
  return map;
};

export const computeRallyTags = (
  rallyTempoData: RallyTempoPayload | null,
  rallyMetrics: RallyMetricsRow[],
  dynData: DynamicsPayload | null
): Record<string, RallyTags> => {
  if (!rallyTempoData || !rallyTempoData.rallies) return {};
  const tags: Record<string, RallyTags> = {};
  const metricsMap = buildMetricsMap(rallyMetrics || []);
  const maxGame = rallyTempoData.rallies.reduce((max, r) => Math.max(max, r.game_number || 0), 0);
  const maxRallyByGame = new Map<number, number>();
  for (const rally of rallyTempoData.rallies) {
    const game = rally.game_number || 0;
    const current = maxRallyByGame.get(game) ?? 0;
    if (rally.rally_number > current) {
      maxRallyByGame.set(game, rally.rally_number);
    }
  }
  for (const rally of rallyTempoData.rallies) {
    const lengthTag = getLengthTag(rally.total_shots || 0);
    const tempoTag = determineTempoTag(combineShots(rally));
    const dynRally = dynData?.rallies?.[rally.rally_id];
    const effectivenessTag = determineEffectivenessTag(rally, dynRally);
    const isFinal =
      rally.game_number === maxGame &&
      rally.rally_number === (maxRallyByGame.get(rally.game_number || 0) ?? rally.rally_number);
    const clutchTag = determineClutchTag(
      rally,
      tempoTag,
      effectivenessTag,
      metricsMap[rally.rally_id],
      isFinal
    );
    tags[rally.rally_id] = {
      length: lengthTag,
      tempo: tempoTag,
      effectiveness: effectivenessTag,
      clutch: clutchTag,
    };
  }
  return tags;
};


