import React, { useMemo, useState } from 'react';

export type TempoEvent = {
  GameNumber: number;
  RallyNumber: number;
  StrokeNumber: number;
  FrameNumber: number;
  Player: 'P0' | 'P1' | string;
  Stroke: string;
  rally_id: string;
  opp_prev_stroke: string;
  response_time_sec: number;
  classification?: 'fast' | 'normal' | 'slow' | string | null;
};

export type ComboStats = {
  count: number;
  median: number | null;
  p10: number | null;
  p90: number | null;
  mad: number | null;
};

export type TempoThresholds = {
  fps: number;
  caps?: { lower?: number; upper?: number };
  min_combo_n?: number;
  min_opp_stroke_n?: number;
  baselines?: Record<'P0' | 'P1' | string, ComboStats>;
  combos?: Record<string, ComboStats>;
  opp_only?: Record<string, ComboStats>;
};

type Props = {
  events: TempoEvent[];
  thresholds: TempoThresholds | null;
  fps: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
};

const toSec = (frame: number, fps: number) => (Number.isFinite(frame) && fps > 0 ? frame / fps : 0);
const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current; if (!v) return; const s = Math.max(0, sec - 2); v.currentTime = s; v.play().catch(() => {});
};

const PAD = 28;
const H = 320;

const TempoAnalysis: React.FC<Props> = ({ events, thresholds, fps, videoRef }) => {
  const [playerView, setPlayerView] = useState<'both' | 'P0' | 'P1'>('both');
  const [rallyFilter, setRallyFilter] = useState<string>('');
  const [showFast, setShowFast] = useState<boolean>(true);
  const [showNormal, setShowNormal] = useState<boolean>(true);
  const [showSlow, setShowSlow] = useState<boolean>(true);

  const rallyIds = useMemo(() => {
    const set = new Set<string>();
    events.forEach(e => { if (e.rally_id) set.add(e.rally_id); });
    return Array.from(set);
  }, [events]);

  const filtered = useMemo(() => {
    return events.filter(e => {
      if (playerView !== 'both' && e.Player !== playerView) return false;
      if (rallyFilter && e.rally_id !== rallyFilter) return false;
      const c = String(e.classification || 'normal').toLowerCase();
      if (c === 'fast' && !showFast) return false;
      if (c === 'slow' && !showSlow) return false;
      if ((c !== 'fast' && c !== 'slow') && !showNormal) return false;
      return Number.isFinite(e.response_time_sec) && Number.isFinite(e.FrameNumber);
    });
  }, [events, playerView, rallyFilter, showFast, showNormal, showSlow]);

  const yMax = useMemo(() => {
    const vals = filtered.map(e => e.response_time_sec || 0);
    const vmax = Math.max(1.0, ...vals, thresholds?.caps?.upper || 0);
    return Math.min(5.0, Math.max(1.5, vmax + 0.2));
  }, [filtered, thresholds]);
  const yMin = 0;

  const tMin = useMemo(() => Math.min(...filtered.map(e => toSec(e.FrameNumber, fps))), [filtered, fps]);
  const tMax = useMemo(() => Math.max(...filtered.map(e => toSec(e.FrameNumber, fps))), [filtered, fps]);

  const W = 800;
  const scaleX = (t: number) => {
    if (!Number.isFinite(tMin) || !Number.isFinite(tMax) || tMax <= tMin) return PAD;
    return PAD + ((t - tMin) / (tMax - tMin)) * (W - 2 * PAD);
  };
  const scaleY = (v: number) => {
    return PAD + (1 - (v - yMin) / (yMax - yMin)) * (H - 2 * PAD);
  };

  const colorFor = (e: TempoEvent) => {
    const c = String(e.classification || 'normal').toLowerCase();
    if (c === 'fast') return e.Player === 'P0' ? '#16a34a' : '#22c55e';
    if (c === 'slow') return e.Player === 'P0' ? '#ef4444' : '#f97316';
    return e.Player === 'P0' ? '#60a5fa' : '#93c5fd';
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <strong>Tempo</strong>
        <select value={playerView} onChange={e => setPlayerView(e.target.value as any)} style={{ padding: '4px 6px', borderRadius: 6, border: '1px solid #2c2c34', background: '#0f0f15', color:'#e5e7eb' }}>
          <option value="both">Both</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
        </select>
        <select value={rallyFilter} onChange={e => setRallyFilter(e.target.value)} style={{ padding: '4px 6px', borderRadius: 6, border: '1px solid #2c2c34', background: '#0f0f15', color:'#e5e7eb' }}>
          <option value="">All rallies</option>
          {rallyIds.slice(0, 300).map(rid => (<option key={rid} value={rid}>{rid}</option>))}
        </select>
        <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:13 }}>
          <input type="checkbox" checked={showFast} onChange={e => setShowFast(e.target.checked)} />
          Fast
        </label>
        <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:13 }}>
          <input type="checkbox" checked={showNormal} onChange={e => setShowNormal(e.target.checked)} />
          Normal
        </label>
        <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:13 }}>
          <input type="checkbox" checked={showSlow} onChange={e => setShowSlow(e.target.checked)} />
          Slow
        </label>
        <div style={{ marginLeft: 'auto', fontSize: 12, opacity: 0.8 }}>
          Points: {filtered.length}
        </div>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`}>
        {/* Axes */}
        <line x1={PAD} y1={H-PAD} x2={W-PAD} y2={H-PAD} stroke="#334155" />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H-PAD} stroke="#334155" />
        {/* Y ticks */}
        {Array.from({ length: 6 }).map((_, i) => {
          const v = i * (yMax - yMin) / 5 + yMin;
          const y = scaleY(v);
          return (
            <g key={`yt-${i}`}>
              <line x1={PAD} y1={y} x2={W-PAD} y2={y} stroke="#1f2937" strokeDasharray="2,4" />
              <text x={6} y={y+4} fontSize={11} fill="#94a3b8">{v.toFixed(2)}s</text>
            </g>
          );
        })}
        {/* X ticks (time) */}
        {Number.isFinite(tMin) && Number.isFinite(tMax) && (tMax > tMin) && (
          Array.from({ length: 6 }).map((_, i) => {
            const t = i * (tMax - tMin) / 5 + tMin;
            const x = scaleX(t);
            return (
              <g key={`xt-${i}`}>
                <line x1={x} y1={PAD} x2={x} y2={H-PAD} stroke="#1f2937" strokeDasharray="2,4" />
                <text x={x-12} y={H-6} fontSize={11} fill="#94a3b8">{t.toFixed(1)}s</text>
              </g>
            );
          })
        )}

        {/* Points */}
        {filtered.map((e, i) => {
          const sec = toSec(e.FrameNumber, fps);
          const x = scaleX(sec);
          const y = scaleY(e.response_time_sec);
          const fill = colorFor(e);
          const r = e.Player === 'P0' ? 3.5 : 3;
          return (
            <g key={`pt-${i}`} onClick={() => seek(videoRef, sec)} cursor="pointer">
              <circle cx={x} cy={y} r={r} fill={fill} />
              {/* invisible hit area */}
              <rect x={x-5} y={y-5} width={10} height={10} fill="transparent" />
              <title>
                {`${e.Player} ${e.Stroke} | resp=${e.response_time_sec.toFixed(3)}s | ${e.classification || 'normal'}\n` +
                 `rally=${e.rally_id} stroke#${e.StrokeNumber} | opp:${e.opp_prev_stroke || '—'}`
                }
              </title>
            </g>
          );
        })}
      </svg>

      <div style={{ marginTop: 8, display: 'flex', gap: 8, fontSize: 12, color: '#94a3b8' }}>
        <div><span style={{ display:'inline-block', width:10, height:10, background:'#60a5fa', marginRight:6 }} />P0 normal</div>
        <div><span style={{ display:'inline-block', width:10, height:10, background:'#93c5fd', marginRight:6 }} />P1 normal</div>
        <div><span style={{ display:'inline-block', width:10, height:10, background:'#16a34a', marginRight:6 }} />P0 fast</div>
        <div><span style={{ display:'inline-block', width:10, height:10, background:'#22c55e', marginRight:6 }} />P1 fast</div>
        <div><span style={{ display:'inline-block', width:10, height:10, background:'#ef4444', marginRight:6 }} />P0 slow</div>
        <div><span style={{ display:'inline-block', width:10, height:10, background:'#f97316', marginRight:6 }} />P1 slow</div>
      </div>

      {!!thresholds && (
        <div style={{ marginTop: 10, fontSize: 12, opacity: 0.8 }}>
          Thresholds loaded. Baseline P0 median/MAD: {thresholds.baselines?.P0?.median?.toFixed(3) || '—'}/{thresholds.baselines?.P0?.mad?.toFixed(3) || '—'} |
          P1: {thresholds.baselines?.P1?.median?.toFixed(3) || '—'}/{thresholds.baselines?.P1?.mad?.toFixed(3) || '—'}
        </div>
      )}
    </div>
  );
};

export default TempoAnalysis;


