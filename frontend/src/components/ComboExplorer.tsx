import React, { useMemo, useState } from 'react';
import { formatMs } from '../utils/timecode';

export type ComboSummaryBandRow = {
  combo_key_band: string;
  player: string;
  opp_prev_stroke: string;
  opp_band: string;
  resp_stroke: string;
  resp_band: string;
  count: number;
  min_rt: number;
  p10: number | null;
  median: number | null;
  p90: number | null;
  max_rt: number;
};

export type ComboInstanceBandRow = {
  combo_key_band: string;
  rally_id: string;
  player: string;
  time_sec: number;
  opp_prev_stroke: string;
  opp_band: string;
  resp_stroke: string;
  resp_band: string;
  response_time_sec: number;
  position_band: 'near_min' | 'typical' | 'near_max' | string;
};

const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current; if (!v) return; const s = Math.max(0, sec - 2); v.currentTime = s; v.play().catch(() => {});
};

const ComboExplorer: React.FC<{ summary: ComboSummaryBandRow[]; instances: ComboInstanceBandRow[]; videoRef: React.RefObject<HTMLVideoElement | null>; }> = ({ summary, instances, videoRef }) => {
  const [player, setPlayer] = useState<'both'|'P0'|'P1'>('both');
  const [oppBand, setOppBand] = useState<string>('all');
  const [respBand, setRespBand] = useState<string>('all');
  const [search, setSearch] = useState<string>('');

  const bandsOpp = useMemo(()=>Array.from(new Set(summary.map(s=>s.opp_band))).filter(Boolean), [summary]);
  const bandsResp = useMemo(()=>Array.from(new Set(summary.map(s=>s.resp_band))).filter(Boolean), [summary]);

  const filtered = useMemo(()=>{
    return summary.filter(s => (player==='both' || s.player===player) &&
      (oppBand==='all' || s.opp_band===oppBand) &&
      (respBand==='all' || s.resp_band===respBand) &&
      (!search || (s.opp_prev_stroke.includes(search) || s.resp_stroke.includes(search))));
  }, [summary, player, oppBand, respBand, search]);

  const groupInstances = useMemo(()=>{
    const map: Record<string, ComboInstanceBandRow[]> = {};
    for (const r of instances) {
      if (!map[r.combo_key_band]) map[r.combo_key_band] = [];
      map[r.combo_key_band].push(r);
    }
    return map;
  }, [instances]);

  return (
    <div>
      <div style={{ display:'flex', gap:8, marginBottom: 8 }}>
        <select value={player} onChange={e=>setPlayer(e.target.value as any)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="both">Both</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
        </select>
        <select value={oppBand} onChange={e=>setOppBand(e.target.value)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="all">Opp band: all</option>
          {bandsOpp.map(b => (<option key={b} value={b}>{b}</option>))}
        </select>
        <select value={respBand} onChange={e=>setRespBand(e.target.value)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="all">Resp band: all</option>
          {bandsResp.map(b => (<option key={b} value={b}>{b}</option>))}
        </select>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search shot" style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb', flex:1 }} />
      </div>
      {filtered.length === 0 ? (
        <div style={{ opacity: 0.7 }}>No combos loaded.</div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
          {filtered.map((s, i) => {
            const inst = (groupInstances[s.combo_key_band] || []).slice().sort((a,b)=>a.time_sec - b.time_sec);
            return (
              <div key={`${s.combo_key_band}-${i}`} style={{ border:'1px solid #2c2c34', borderRadius:8, padding:10 }}>
                <div style={{ fontWeight:700, marginBottom:6 }}>
                  {s.player} | opp:{s.opp_prev_stroke} ({s.opp_band}) → resp:{s.resp_stroke} ({s.resp_band})
                </div>
                <div style={{ fontSize:12, opacity:0.85, marginBottom:6 }}>
                  Count {s.count} · min {s.min_rt.toFixed(3)} · p10 {s.p10?.toFixed(3) ?? '—'} · median {s.median?.toFixed(3) ?? '—'} · p90 {s.p90?.toFixed(3) ?? '—'} · max {s.max_rt.toFixed(3)}
                </div>
                <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                  {inst.map((r, j)=>(
                    <div key={`ci-${i}-${j}`} onClick={()=>seek(videoRef, r.time_sec)}
                      title={`${r.rally_id} @${formatMs(r.time_sec*1000)} | ${r.position_band} | rt=${r.response_time_sec.toFixed(3)}s`}
                      style={{ padding:'0.35rem 0.6rem', background: r.position_band==='near_min' ? '#0f5132' : r.position_band==='near_max' ? '#5c2d31' : '#1f2937', border:'1px solid #334155', borderRadius:999, fontSize:12, color:'#cbd5e1', cursor:'pointer', userSelect:'none' }}>
                      [{formatMs(r.time_sec*1000)}]
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ComboExplorer;


