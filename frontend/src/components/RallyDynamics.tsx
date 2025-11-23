import React, { useMemo, useState, useEffect, useRef } from 'react';
import {
  CLUTCH_FILTERS,
  EFFECTIVENESS_FILTERS,
  LENGTH_FILTERS,
  TEMPO_FILTERS,
  type RallyTags,
} from '../utils/rallyTags';

type Point = {
  frame: number;
  time_sec: number;
  stroke_no: number;
  player: 'P0' | 'P1' | string;
  stroke: string;
  effectiveness: number | null;
};

type TurningPoint = {
  player: 'P0' | 'P1' | string;
  stroke_no: number;
  frame: number;
  time_sec: number;
  swing: number;
  stroke: string;
};

export type RallyItem = {
  frame_start: number;
  frame_end: number;
  winner: string | null;
  score_label?: string;
  score_key?: string;
  shot_sequence: string;
  points: Point[];
  turning_points: TurningPoint[];
  rally_dynamics?: {
    P0?: { slope: number; delta: number; category: 'incline'|'decline'|'flat' };
    P1?: { slope: number; delta: number; category: 'incline'|'decline'|'flat' };
    combined_category?: 'both_incline'|'both_decline'|'mixed'|'flat';
  };
};

export type DynamicsPayload = {
  fps: number;
  threshold: number;
  rallies: Record<string, RallyItem>;
  indices?: { by_score?: Record<string, string[]> };
  summaries?: AnySummary;
};

type AnySummary = Record<string, any>;

type Props = {
  data: DynamicsPayload;
  videoRef: React.RefObject<HTMLVideoElement>;
  fps: number;
  fullWidth?: boolean;
  rallyTags?: Record<string, RallyTags>;
};

const H = 220;
const PAD = 28;
const filterSelectStyle: React.CSSProperties = {
  padding: '4px 8px',
  borderRadius: 6,
  border: '1px solid #2c2c34',
  background: '#0f0f15',
  color: '#e5e7eb',
};

export const RallyDynamics: React.FC<Props> = ({ data, videoRef, fps: _fps, fullWidth = false, rallyTags }) => {
  const rallyIds = useMemo(() => Object.keys(data?.rallies || {}).sort(), [data]);
  const [selectedRally, setSelectedRally] = useState<string>(rallyIds[0] || '');
  const [showP0, setShowP0] = useState<boolean>(true);
  const [showP1, setShowP1] = useState<boolean>(true);
  const [containerWidth, setContainerWidth] = useState<number>(fullWidth ? 800 : 520);
  const [lengthFilter, setLengthFilter] = useState<(typeof LENGTH_FILTERS)[number]['value']>('all');
  const [tempoFilter, setTempoFilter] = useState<(typeof TEMPO_FILTERS)[number]['value']>('all');
  const [effectFilter, setEffectFilter] = useState<(typeof EFFECTIVENESS_FILTERS)[number]['value']>('all');
  const [clutchFilter, setClutchFilter] = useState<(typeof CLUTCH_FILTERS)[number]['value']>('all');
  
  // Measure container width for fullWidth mode
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    if (fullWidth && containerRef.current) {
      const updateWidth = () => {
        if (containerRef.current) {
          // Get the actual video width or container width
          const container = containerRef.current;
          const video = container.closest('.video-area')?.querySelector('video');
          const targetWidth = video ? video.offsetWidth : (container.offsetWidth - 24);
          setContainerWidth(Math.max(520, targetWidth)); // Min 520px
        }
      };
      // Use ResizeObserver if available for better performance
      updateWidth();
      window.addEventListener('resize', updateWidth);
      let resizeObserver: ResizeObserver | null = null;
      if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
        resizeObserver = new ResizeObserver(updateWidth);
        resizeObserver.observe(containerRef.current);
      }
      return () => {
        if (resizeObserver) resizeObserver.disconnect();
        window.removeEventListener('resize', updateWidth);
      };
    }
  }, [fullWidth]);

  const filteredRallyIds = useMemo(() => {
    return rallyIds.filter(rid => {
      const tag = rallyTags?.[rid];
      if (!tag) {
        return (
          lengthFilter === 'all' &&
          tempoFilter === 'all' &&
          effectFilter === 'all' &&
          clutchFilter === 'all'
        );
      }
      if (lengthFilter !== 'all' && tag.length !== lengthFilter) return false;
      if (tempoFilter !== 'all' && tag.tempo !== tempoFilter) return false;
      if (effectFilter !== 'all' && tag.effectiveness !== effectFilter) return false;
      if (clutchFilter !== 'all' && tag.clutch !== clutchFilter) return false;
      return true;
    });
  }, [rallyIds, rallyTags, lengthFilter, tempoFilter, effectFilter, clutchFilter]);

  useEffect(() => {
    if (!filteredRallyIds.length) {
      setSelectedRally('');
      return;
    }
    if (!selectedRally || !filteredRallyIds.includes(selectedRally)) {
      setSelectedRally(filteredRallyIds[0]);
    }
  }, [filteredRallyIds, selectedRally]);

  const W = fullWidth ? containerWidth : 520;
  const activeRallyId =
    selectedRally && filteredRallyIds.includes(selectedRally) ? selectedRally : (filteredRallyIds[0] || '');
  const rally = data?.rallies?.[activeRallyId] as RallyItem | undefined;
  const pointsP0 = useMemo(() => (rally?.points || []).filter(p => p.player === 'P0' && p.effectiveness != null), [rally]);
  const pointsP1 = useMemo(() => (rally?.points || []).filter(p => p.player === 'P1' && p.effectiveness != null), [rally]);

  const [tMin, tMax] = useMemo(() => {
    const pts = (rally?.points || []).map(p => p.time_sec).filter(t => Number.isFinite(t));
    if (!pts.length) return [0, 1] as const;
    const minVal = Math.min(...pts);
    const maxVal = Math.max(...pts);
    return [minVal, Math.max(minVal + 1e-6, maxVal)] as const;
  }, [rally]);
  const yMin = 0; // effectiveness min
  const yMax = 100; // effectiveness max

  const scaleX = (t: number) => {
    const a = (t - tMin) / Math.max(1e-6, (tMax - tMin));
    return PAD + a * (W - 2 * PAD);
  };
  const scaleY = (e: number) => {
    const a = (e - yMin) / Math.max(1e-6, (yMax - yMin));
    return H - PAD - a * (H - 2 * PAD);
  };

  const toPolyline = (pts: Point[]) => pts.map(p => `${scaleX(p.time_sec)},${scaleY(p.effectiveness as number)}`).join(' ');

  const onJump = (sec: number) => {
    const v = videoRef.current; if (!v) return;
    v.currentTime = Math.max(0, sec - 1);
    v.play().catch(() => {});
  };

  if (!filteredRallyIds.length) {
    return <div style={{ opacity: 0.7 }}>No rallies match the selected filters.</div>;
  }

  if (!rally) {
    return <div style={{ opacity: 0.7 }}>Load a rally_timeseries.json to view dynamics.</div>;
  }

  return (
    <div ref={containerRef} style={{ width: fullWidth ? '100%' : 'auto' }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <select value={lengthFilter} onChange={e => setLengthFilter(e.target.value as any)} style={filterSelectStyle}>
          {LENGTH_FILTERS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select value={tempoFilter} onChange={e => setTempoFilter(e.target.value as any)} style={filterSelectStyle}>
          {TEMPO_FILTERS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select value={effectFilter} onChange={e => setEffectFilter(e.target.value as any)} style={filterSelectStyle}>
          {EFFECTIVENESS_FILTERS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select value={clutchFilter} onChange={e => setClutchFilter(e.target.value as any)} style={filterSelectStyle}>
          {CLUTCH_FILTERS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <label style={{ fontSize: 13 }}>Rally:</label>
        <select value={activeRallyId} onChange={e => setSelectedRally(e.target.value)} style={{ padding: '4px 6px', background: '#0f0f15', color: '#e5e7eb', border: '1px solid #2c2c34', borderRadius: 6 }}>
          {filteredRallyIds.map(rid => {
            const item = data.rallies[rid] as RallyItem;
            const label = item?.score_label ? `${item.score_label} (${rid})` : rid;
            return (<option key={rid} value={rid}>{label}</option>);
          })}
        </select>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
          <label style={{ fontSize: 12 }}><input type="checkbox" checked={showP0} onChange={e => setShowP0(e.target.checked)} /> P0</label>
          <label style={{ fontSize: 12 }}><input type="checkbox" checked={showP1} onChange={e => setShowP1(e.target.checked)} /> P1</label>
        </div>
      </div>

      <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 6 }}>Winner: {rally.winner || '—'} {rally.score_label ? `| Score: ${rally.score_label}` : ''}</div>
      <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 8 }}>Sequence: {rally.shot_sequence}</div>

      {/* Optional: trend summary */}
      {rally.rally_dynamics && (
        <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 8, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div>Dynamics: {rally.rally_dynamics.combined_category || '—'}</div>
          <div>P0: {rally.rally_dynamics.P0?.category || '—'} (slope {rally.rally_dynamics.P0?.slope?.toFixed(1)}, Δ {rally.rally_dynamics.P0?.delta?.toFixed(1)})</div>
          <div>P1: {rally.rally_dynamics.P1?.category || '—'} (slope {rally.rally_dynamics.P1?.slope?.toFixed(1)}, Δ {rally.rally_dynamics.P1?.delta?.toFixed(1)})</div>
        </div>
      )}

      <svg width={W} height={H} style={{ width: fullWidth ? '100%' : W, height: H, maxWidth: '100%', background: '#0b0b12', border: '1px solid #2c2c34', borderRadius: 8 }}>
        {/* Axes */}
        <line x1={PAD} y1={H-PAD} x2={W-PAD} y2={H-PAD} stroke="#334155" strokeWidth={1} />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H-PAD} stroke="#334155" strokeWidth={1} />
        {/* Grid ticks */}
        {[0,20,40,60,80,100].map(v => (
          <g key={`y-${v}`}>
            <line x1={PAD} y1={scaleY(v)} x2={W-PAD} y2={scaleY(v)} stroke="#1f2937" strokeWidth={1} />
            <text x={4} y={scaleY(v)+4} fontSize={10} fill="#94a3b8">{v}</text>
          </g>
        ))}

        {/* Lines */}
        {showP0 && pointsP0.length > 1 && (
          <polyline fill="none" stroke="#22c55e" strokeWidth={2} points={toPolyline(pointsP0)} />
        )}
        {showP1 && pointsP1.length > 1 && (
          <polyline fill="none" stroke="#60a5fa" strokeWidth={2} points={toPolyline(pointsP1)} />
        )}

        {/* Points */}
        {(showP0 ? pointsP0 : []).map((p, i) => (
          <circle key={`p0-${i}`} cx={scaleX(p.time_sec)} cy={scaleY(p.effectiveness as number)} r={3} fill="#22c55e" />
        ))}
        {(showP1 ? pointsP1 : []).map((p, i) => (
          <circle key={`p1-${i}`} cx={scaleX(p.time_sec)} cy={scaleY(p.effectiveness as number)} r={3} fill="#60a5fa" />
        ))}

        {/* Turning points */}
        {(rally.turning_points || []).map((tp, i) => (
          <g key={`tp-${i}`}>
            <rect x={scaleX(tp.time_sec)-4} y={PAD-2} width={8} height={H-2*PAD+4} fill={tp.swing >= 0 ? '#16653433' : '#7f1d1d33'} />
            <circle cx={scaleX(tp.time_sec)} cy={tp.player==='P0' ? PAD+8 : PAD+22} r={3} fill={tp.swing >= 0 ? '#22c55e' : '#ef4444'} />
          </g>
        ))}

        {/* Click zones */}
        {(rally.points || []).map((p, i) => (
          <rect key={`cz-${i}`} x={scaleX(p.time_sec)-4} y={PAD} width={8} height={H-2*PAD}
            fill="transparent"
            onClick={() => onJump(p.time_sec)}
            style={{ cursor: 'pointer' }}
          />
        ))}
      </svg>

      {rally.turning_points?.length ? (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {rally.turning_points.map((tp, i) => (
            <div key={`tp-chip-${i}`} onClick={() => onJump(tp.time_sec)}
              style={{ padding: '0.3rem 0.55rem', background: '#eef2ff22', border: '1px solid #334155', borderRadius: 999, fontSize: 12, color: '#cbd5e1', cursor: 'pointer', userSelect: 'none' }}
              title={`${tp.player} swing ${tp.swing>0?'+':''}${tp.swing.toFixed(1)} @ stroke #${tp.stroke_no}`}>
              {tp.player} {tp.swing>0?'+':''}{tp.swing.toFixed(0)} ({tp.stroke})
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export default RallyDynamics;


