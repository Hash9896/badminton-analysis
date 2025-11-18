import React, { useMemo, useState } from 'react';
import { formatMs } from '../utils/timecode';

export type IneffSlowEvent = {
  rally_id: string;
  Player: 'P0' | 'P1' | string;
  time_sec: number;
  Stroke: string;
  opp_prev_stroke: string;
  response_time_sec: number;
  classification: string;
  effectiveness: number | null;
  effectiveness_color: string | null;
  incoming_eff: number | null;
  incoming_eff_bin: string | null;
  forced_error: boolean;
  unforced_error: boolean;
  threshold_source: string;
  combo_key: string;
};

type Props = {
  events: IneffSlowEvent[];
  fps: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
};

const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current; if (!v) return; const s = Math.max(0, sec - 2); v.currentTime = s; v.play().catch(() => {});
};

const IneffectiveSlowEvents: React.FC<Props> = ({ events, fps, videoRef }) => {
  // fps parameter is required by Props but not used in this component
  void fps;
  const [groupBy, setGroupBy] = useState<'stroke' | 'combo'>('stroke');

  const byPlayer = useMemo(() => {
    const p0 = events.filter(e => e.Player === 'P0');
    const p1 = events.filter(e => e.Player === 'P1');
    return { P0: p0, P1: p1 };
  }, [events]);

  const group = (rows: IneffSlowEvent[]) => {
    if (groupBy === 'combo') {
      const map: Record<string, IneffSlowEvent[]> = {};
      rows.forEach(r => {
        const key = r.combo_key || `${r.Player}|opp:${r.opp_prev_stroke}|resp:${r.Stroke}`;
        if (!map[key]) map[key] = [];
        map[key].push(r);
      });
      return Object.entries(map).sort((a, b) => b[1].length - a[1].length);
    } else {
      const map: Record<string, IneffSlowEvent[]> = {};
      rows.forEach(r => {
        const key = r.Stroke;
        if (!map[key]) map[key] = [];
        map[key].push(r);
      });
      return Object.entries(map).sort((a, b) => b[1].length - a[1].length);
    }
  };

  const Section: React.FC<{ title: string; rows: IneffSlowEvent[] }> = ({ title, rows }) => {
    const groups = group(rows);
    if (rows.length === 0) return <div style={{ opacity: 0.7 }}>{title}: none</div>;
    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{title} ({rows.length})</div>
        <div style={{ display:'flex', gap: 8, marginBottom: 8 }}>
          <label style={{ fontSize: 12 }}>
            <input type="radio" name={`${title}-group`} checked={groupBy==='stroke'} onChange={()=>setGroupBy('stroke')} /> Group by stroke
          </label>
          <label style={{ fontSize: 12 }}>
            <input type="radio" name={`${title}-group`} checked={groupBy==='combo'} onChange={()=>setGroupBy('combo')} /> Group by combo
          </label>
        </div>
        {groups.map(([key, list]) => {
          const sample = list[0];
          const header = groupBy === 'combo'
            ? `${sample.Player} | opp:${sample.opp_prev_stroke} → resp:${sample.Stroke}`
            : `${sample.Player} | stroke:${sample.Stroke}`;
          return (
            <div key={key} style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 6, display:'flex', alignItems:'center', gap:8 }}>
                <span>{header}</span>
                <span style={{ fontSize: 12, opacity: 0.7 }}>({list.length})</span>
              </div>
              <div style={{ display:'flex', flexWrap:'wrap', gap: 6 }}>
                {list
                  .slice()
                  .sort((a, b) => a.time_sec - b.time_sec)
                  .map((r, i) => (
                  <div
                    key={`${key}-${i}-${r.time_sec}`}
                    onClick={()=>seek(videoRef, r.time_sec)}
                    title={`${r.rally_id} @${formatMs(r.time_sec * 1000)} | rt=${r.response_time_sec.toFixed(3)}s | eff=${r.effectiveness ?? '—'} (${r.effectiveness_color || ''})`}
                    style={{ padding:'0.35rem 0.6rem', background:'#fef2f222', border:'1px solid #7f1d1d', borderRadius:999, fontSize:12, color:'#e5e7eb', cursor:'pointer', userSelect:'none' }}
                  >
                    [{formatMs(r.time_sec * 1000)}]
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Ineffective + Slow (all instances)</div>
      <Section title="P0" rows={byPlayer.P0} />
      <Section title="P1" rows={byPlayer.P1} />
    </div>
  );
};

export default IneffectiveSlowEvents;


