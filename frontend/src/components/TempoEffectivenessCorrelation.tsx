import React, { useMemo, useState } from 'react';
import { type RallyTempoPayload } from './RallyTempoVisualization';
import { type DynamicsPayload } from './RallyDynamics';

type TempoRally = RallyTempoPayload['rallies'][number];

type Props = {
  tempoData: RallyTempoPayload | null;
  dynamicsData: DynamicsPayload | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
};

type TempoPoint = {
  player: 'P0' | 'P1';
  time: number;
  response: number;
  classification: string;
  tempo_control: string;
  control_type: string;
  stroke: string;
  time_abs: number;
};

type EffPoint = {
  player: 'P0' | 'P1';
  time: number;
  effectiveness: number;
  stroke_no: number;
  stroke: string;
  time_abs: number;
};

const PAD = 48;
const H = 360;
const W = 960;

const classificationColors: Record<'P0' | 'P1', Record<'fast' | 'normal' | 'slow', string>> = {
  P0: { fast: '#06b6d4', normal: '#3b82f6', slow: '#1e40af' },
  P1: { fast: '#f97316', normal: '#ef4444', slow: '#dc2626' },
};

const classificationSizes: Record<'fast' | 'normal' | 'slow', number> = {
  fast: 8,
  normal: 6,
  slow: 5,
};

const normalizeClassification = (classification?: string): 'fast' | 'normal' | 'slow' => {
  const c = (classification || '').toLowerCase().trim();
  if (c === 'fast' || c === 'slow') return c;
  return 'normal';
};

const getClassificationColor = (player: 'P0' | 'P1', classification?: string) =>
  classificationColors[player][normalizeClassification(classification)];

const getClassificationRadius = (classification?: string) =>
  classificationSizes[normalizeClassification(classification)];

const resolveTempoDominance = (
  player: 'P0' | 'P1' | string,
  tempoControl?: string
): { dominant: 'P0' | 'P1' | null; label: string } => {
  const control = (tempoControl || '').toLowerCase();
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
};

const formatControlType = (controlType?: string) => {
  if (!controlType) return '';
  return controlType
    .split('_')
    .map(part => (part ? part[0].toUpperCase() + part.slice(1) : part))
    .join(' ');
};

const TempoEffectivenessCorrelation: React.FC<Props> = ({ tempoData, dynamicsData, videoRef }) => {
  const tempoMap = useMemo(() => {
    const map = new Map<string, TempoRally>();
    tempoData?.rallies?.forEach(r => map.set(r.rally_id, r));
    return map;
  }, [tempoData]);

  const dynEntries = useMemo(() => Object.entries(dynamicsData?.rallies || {}), [dynamicsData]);
  const pairedRallies = useMemo(() => dynEntries.filter(([rid]) => tempoMap.has(rid)), [dynEntries, tempoMap]);
  const [selectedRally, setSelectedRally] = useState<string>(pairedRallies[0]?.[0] || '');

  if (!pairedRallies.length) {
    return (
      <div style={{ padding: 16, color: '#94a3b8' }}>
        Load both *_tempo_analysis_new.csv (for tempo) and rally_timeseries.json (for effectiveness) to view the merged chart.
      </div>
    );
  }

  const rallyId = pairedRallies.find(([rid]) => rid === selectedRally)?.[0] || pairedRallies[0][0];
  const tempoRally = tempoMap.get(rallyId);
  const dynRally = dynamicsData?.rallies?.[rallyId];

  if (!tempoRally || !dynRally) {
    return <div style={{ padding: 16, color: '#94a3b8' }}>Selected rally data not available.</div>;
  }

  const tempoPoints: TempoPoint[] = useMemo(() => {
    const combine = (shots: typeof tempoRally.p0_shots, player: 'P0' | 'P1'): TempoPoint[] =>
      shots
        .filter(s => s.response_time_sec != null && Number.isFinite(s.response_time_sec))
        .map(s => ({
          player,
          time: s.time_in_rally ?? (s.time_sec - tempoRally.rally_start_time),
          response: s.response_time_sec ?? 0,
          classification: s.classification || 'normal',
          tempo_control: s.tempo_control || 'neutral',
          control_type: s.control_type || 'balanced',
          stroke: s.stroke,
          time_abs: s.time_sec,
        }));
    return [...combine(tempoRally.p0_shots, 'P0'), ...combine(tempoRally.p1_shots, 'P1')].sort((a, b) => a.time - b.time);
  }, [tempoRally]);

  const effPointsP0: EffPoint[] = useMemo(() => {
    const pts = (dynRally.points || []).filter(p => p.player === 'P0' && Number.isFinite(p.effectiveness));
    if (!pts.length) return [];
    const base = pts[0].time_sec;
    return pts.map(p => ({
      player: 'P0',
      time: p.time_sec - base,
      effectiveness: p.effectiveness ?? 0,
      stroke_no: p.stroke_no,
      stroke: p.stroke,
      time_abs: p.time_sec,
    }));
  }, [dynRally]);

  const effPointsP1: EffPoint[] = useMemo(() => {
    const pts = (dynRally.points || []).filter(p => p.player === 'P1' && Number.isFinite(p.effectiveness));
    if (!pts.length) return [];
    const base = pts[0].time_sec;
    return pts.map(p => ({
      player: 'P1',
      time: p.time_sec - base,
      effectiveness: p.effectiveness ?? 0,
      stroke_no: p.stroke_no,
      stroke: p.stroke,
      time_abs: p.time_sec,
    }));
  }, [dynRally]);

  const xMin = 0;
  const xMax = Math.max(
    1.0,
    tempoPoints.length ? Math.max(...tempoPoints.map(p => p.time)) : 0,
    effPointsP0.length ? Math.max(...effPointsP0.map(p => p.time)) : 0,
    effPointsP1.length ? Math.max(...effPointsP1.map(p => p.time)) : 0
  );
  const responseMax = Math.max(1.5, ...tempoPoints.map(p => p.response), 0) + 0.2;
  const responseMin = 0;
  const effMin = 0;
  const effMax = 100;

  const scaleX = (t: number) => PAD + ((t - xMin) / Math.max(xMax - xMin, 1e-6)) * (W - 2 * PAD);
  const scaleYLeft = (v: number) => H - PAD - ((v - responseMin) / Math.max(responseMax - responseMin, 1e-6)) * (H - 2 * PAD);
  const scaleYRight = (v: number) => H - PAD - ((v - effMin) / Math.max(effMax - effMin, 1e-6)) * (H - 2 * PAD);

  const toPolyline = (pts: EffPoint[]) =>
    pts.sort((a, b) => a.time - b.time).map(p => `${scaleX(p.time)},${scaleYRight(p.effectiveness)}`).join(' ');

  const seek = (sec: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, sec - 1.5);
    v.play().catch(() => {});
  };

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <strong>Tempo vs Effectiveness Correlation</strong>
        <select
          value={rallyId}
          onChange={e => setSelectedRally(e.target.value)}
          style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2c2c34', background: '#0f0f15', color: '#e5e7eb' }}
        >
          {pairedRallies.map(([rid]) => {
            const label = dynamicsData?.rallies?.[rid]?.score_label ? `${dynamicsData.rallies[rid].score_label} (${rid})` : rid;
            return (
              <option key={rid} value={rid}>
                {label}
              </option>
            );
          })}
        </select>
        <div style={{ fontSize: 12, color: '#94a3b8' }}>
          Winner: {dynRally.winner || '—'} · Shots: {tempoRally.total_shots}
        </div>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ maxWidth: '100%', background: '#090912', borderRadius: 10, border: '1px solid #1f2937' }}>
        {/* Grid */}
        {Array.from({ length: 5 }).map((_, i) => {
          const t = xMin + (i * (xMax - xMin)) / 4;
          const x = scaleX(t);
          return (
            <g key={`grid-x-${i}`}>
              <line x1={x} y1={PAD} x2={x} y2={H - PAD} stroke="#1f2937" strokeDasharray="4,6" />
              <text x={x} y={H - PAD + 16} textAnchor="middle" fontSize={11} fill="#94a3b8">
                {t.toFixed(1)}s
              </text>
            </g>
          );
        })}

        {Array.from({ length: 5 }).map((_, i) => {
          const v = responseMin + (i * (responseMax - responseMin)) / 4;
          const y = scaleYLeft(v);
          return (
            <g key={`grid-y-left-${i}`}>
              <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#0f172a" strokeDasharray="2,4" />
              <text x={PAD - 6} y={y + 4} textAnchor="end" fontSize={11} fill="#60a5fa">
                {v.toFixed(2)}s
              </text>
            </g>
          );
        })}

        {Array.from({ length: 5 }).map((_, i) => {
          const v = effMin + (i * (effMax - effMin)) / 4;
          const y = scaleYRight(v);
          return (
            <g key={`grid-y-right-${i}`}>
              <text x={W - PAD + 6} y={y + 4} textAnchor="start" fontSize={11} fill="#fbbf24">
                {v.toFixed(0)}%
              </text>
            </g>
          );
        })}

        {/* Effectiveness polylines */}
        {effPointsP0.length > 1 && (
          <polyline fill="none" stroke="#fbbf24" strokeWidth={2} opacity={0.85} points={toPolyline(effPointsP0)} />
        )}
        {effPointsP1.length > 1 && (
          <polyline fill="none" stroke="#fde047" strokeWidth={2} opacity={0.65} points={toPolyline(effPointsP1)} />
        )}

        {/* Tempo points */}
        {tempoPoints.map((point, idx) => {
          const x = scaleX(point.time);
          const y = scaleYLeft(point.response);
          const color = getClassificationColor(point.player, point.classification);
          const radius = getClassificationRadius(point.classification);
          const controlInfo = resolveTempoDominance(point.player, point.tempo_control);
          return (
            <g key={`tempo-${idx}`} onClick={() => seek(point.time_abs)} style={{ cursor: 'pointer' }}>
              {point.player === 'P0' ? (
                <circle cx={x} cy={y} r={radius} fill={color} stroke="#0f172a" strokeWidth={1.2} />
              ) : (
                <rect
                  x={x - radius}
                  y={y - radius}
                  width={radius * 2}
                  height={radius * 2}
                  fill={color}
                  stroke="#0f172a"
                  strokeWidth={1.2}
                  transform={`rotate(45 ${x} ${y})`}
                />
              )}
              <title>
                {`${point.player} ${point.stroke}\nResp: ${point.response.toFixed(3)}s (${point.classification})\nControl: ${controlInfo.label}${
                  point.control_type ? ` (${formatControlType(point.control_type)})` : ''
                }\nTime: ${point.time.toFixed(2)}s`}
              </title>
            </g>
          );
        })}

        {/* Effectiveness click zones */}
        {[...effPointsP0, ...effPointsP1].map((point, idx) => (
          <rect
            key={`eff-${idx}`}
            x={scaleX(point.time) - 4}
            y={PAD}
            width={8}
            height={H - 2 * PAD}
            fill="transparent"
            onClick={() => seek(point.time_abs)}
            style={{ cursor: 'pointer' }}
          >
            <title>{`${point.player} effectiveness ${point.effectiveness.toFixed(1)}% @ stroke ${point.stroke_no}`}</title>
          </rect>
        ))}

        {/* Axis labels */}
        <text x={W / 2} y={H - 10} textAnchor="middle" fill="#cbd5f5" fontSize={12}>
          Time within rally (seconds)
        </text>
        <text x={PAD - 30} y={H / 2} transform={`rotate(-90 ${PAD - 30} ${H / 2})`} fill="#60a5fa" fontSize={12}>
          Response time (s)
        </text>
        <text x={W - PAD + 30} y={H / 2} transform={`rotate(90 ${W - PAD + 30} ${H / 2})`} fill="#fbbf24" fontSize={12}>
          Effectiveness (%)
        </text>
      </svg>

      <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 3, background: '#fbbf24' }} />
          <span>Effectiveness P0</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 3, background: '#fde047' }} />
          <span>Effectiveness P1</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#06b6d4' }} />
          <span>P0 tempo (circle)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 12, height: 12, background: '#f97316', transform: 'rotate(45deg)' }} />
          <span>P1 tempo (diamond)</span>
        </div>
      </div>
    </div>
  );
};

export default TempoEffectivenessCorrelation;

