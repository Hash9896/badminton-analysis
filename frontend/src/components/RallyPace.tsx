import React, { useMemo, useState } from 'react';

export type RallyMetricsRow = {
  game: number;
  rally: number;
  rally_id: string;
  player: string;
  shots: number;
  median_rt: number | null;
  stddev_rt: number | null;
  iqr_rt: number | null;
  range_rt: number | null;
  transitions: number;
  longest_run: number;
  early_late_delta: number | null;
  slope_rt: number | null;
  delta_vs_baseline: number | null;
};

const RallyPace: React.FC<{ data: RallyMetricsRow[] }> = ({ data }) => {
  const [player, setPlayer] = useState<'both'|'P0'|'P1'>('both');
  const byRally = useMemo(()=>{
    const map: Record<string, { P0?: RallyMetricsRow; P1?: RallyMetricsRow }> = {};
    for (const r of data) {
      if (!map[r.rally_id]) map[r.rally_id] = {};
      (map[r.rally_id] as any)[r.player] = r;
    }
    return map;
  }, [data]);
  const rows = useMemo(()=>Object.entries(byRally).map(([rid, v]) => ({ rid, P0: v.P0, P1: v.P1 })), [byRally]);
  return (
    <div>
      <div style={{ display:'flex', gap:8, marginBottom:8 }}>
        <select value={player} onChange={e=>setPlayer(e.target.value as any)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="both">Both</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
        </select>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:8 }}>
        {rows.map((r, i) => {
          const p0 = r.P0, p1 = r.P1;
          if (player==='P0' && !p0) return null;
          if (player==='P1' && !p1) return null;
          const dict =
            (p0?.median_rt ?? Infinity) < (p1?.median_rt ?? Infinity) ? 'P0' :
            (p1?.median_rt ?? Infinity) < (p0?.median_rt ?? Infinity) ? 'P1' : '—';
          return (
            <div key={`${r.rid}-${i}`} style={{ border:'1px solid #2c2c34', borderRadius:8, padding:10 }}>
              <div style={{ fontWeight:700, marginBottom:6 }}>{r.rid} · dictates pace: {dict}</div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, fontSize:12 }}>
                <div>
                  <div style={{ fontWeight:600, marginBottom:4 }}>P0</div>
                  <div>median_rt: {p0?.median_rt?.toFixed(3) ?? '—'}</div>
                  <div>stddev: {p0?.stddev_rt?.toFixed(3) ?? '—'} · iqr: {p0?.iqr_rt?.toFixed(3) ?? '—'} · range: {p0?.range_rt?.toFixed(3) ?? '—'}</div>
                  <div>transitions: {p0?.transitions ?? '—'} · longest_run: {p0?.longest_run ?? '—'}</div>
                  <div>early→late delta: {p0?.early_late_delta?.toFixed(3) ?? '—'} · slope: {p0?.slope_rt?.toFixed(3) ?? '—'}</div>
                  <div>Δ vs baseline: {p0?.delta_vs_baseline?.toFixed(3) ?? '—'}</div>
                </div>
                <div>
                  <div style={{ fontWeight:600, marginBottom:4 }}>P1</div>
                  <div>median_rt: {p1?.median_rt?.toFixed(3) ?? '—'}</div>
                  <div>stddev: {p1?.stddev_rt?.toFixed(3) ?? '—'} · iqr: {p1?.iqr_rt?.toFixed(3) ?? '—'} · range: {p1?.range_rt?.toFixed(3) ?? '—'}</div>
                  <div>transitions: {p1?.transitions ?? '—'} · longest_run: {p1?.longest_run ?? '—'}</div>
                  <div>early→late delta: {p1?.early_late_delta?.toFixed(3) ?? '—'} · slope: {p1?.slope_rt?.toFixed(3) ?? '—'}</div>
                  <div>Δ vs baseline: {p1?.delta_vs_baseline?.toFixed(3) ?? '—'}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default RallyPace;


