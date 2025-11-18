import React, { useMemo, useState } from 'react';
import { formatMs } from '../utils/timecode';

export type ZoneBucketRow = {
  bucket: string;
  player: string;
  role: string;
  count: number;
  min_rt: number;
  p10: number | null;
  median: number | null;
  p90: number | null;
  max_rt: number;
  fast_rate: number;
  slow_rate: number;
  times_sec: number[];
};

const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current; if (!v) return; const s = Math.max(0, sec - 2); v.currentTime = s; v.play().catch(() => {});
};

const ZoneBuckets: React.FC<{ data: ZoneBucketRow[]; videoRef: React.RefObject<HTMLVideoElement | null> }> = ({ data, videoRef }) => {
  const [player, setPlayer] = useState<'both'|'P0'|'P1'>('both');
  const [role, setRole] = useState<'both'|'attacking'|'defensive'>('both');
  const [bucket, setBucket] = useState<string>('all');

  const buckets = useMemo(()=>Array.from(new Set(data.map(d=>d.bucket))), [data]);
  const filtered = useMemo(()=>{
    return data.filter(d => (player==='both' || d.player===player) && (role==='both' || d.role===role) && (bucket==='all' || d.bucket===bucket));
  }, [data, player, role, bucket]);

  return (
    <div>
      <div style={{ display:'flex', gap:8, marginBottom: 8 }}>
        <select value={player} onChange={e=>setPlayer(e.target.value as any)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="both">Both</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
        </select>
        <select value={role} onChange={e=>setRole(e.target.value as any)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="both">Both roles</option>
          <option value="attacking">Attacking</option>
          <option value="defensive">Defensive</option>
        </select>
        <select value={bucket} onChange={e=>setBucket(e.target.value)} style={{ padding:'4px 6px', borderRadius:6, border:'1px solid #2c2c34', background:'#0f0f15', color:'#e5e7eb' }}>
          <option value="all">All buckets</option>
          {buckets.map(b => (<option key={b} value={b}>{b}</option>))}
        </select>
      </div>
      {filtered.length === 0 ? (
        <div style={{ opacity: 0.7 }}>No zone data loaded.</div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12 }}>
          {filtered.map((row, i) => (
            <div key={`${row.bucket}-${row.player}-${row.role}-${i}`} style={{ border:'1px solid #2c2c34', borderRadius:8, padding:10 }}>
              <div style={{ fontWeight:700, marginBottom:6 }}>{row.player} · {row.role} · {row.bucket}</div>
              <div style={{ fontSize:12, opacity:0.85, marginBottom:6 }}>
                Count {row.count} · p10 {row.p10?.toFixed(3) ?? '—'} · median {row.median?.toFixed(3) ?? '—'} · p90 {row.p90?.toFixed(3) ?? '—'}
              </div>
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {row.times_sec.slice(0, 500).map((sec, j) => (
                  <div key={`zb-${i}-${j}`} onClick={()=>seek(videoRef, sec)} style={{ padding:'0.35rem 0.6rem', background:'#eef2ff22', border:'1px solid #334155', borderRadius:999, fontSize:12, color:'#cbd5e1', cursor:'pointer', userSelect:'none' }} title={`@${formatMs(sec*1000)}`}>
                    [{formatMs(sec*1000)}]
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ZoneBuckets;


