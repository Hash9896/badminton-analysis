import React, { useMemo, useState, useEffect, useRef } from 'react';
import { formatMs } from '../utils/timecode';
import type { StatsData, CsvRow } from './StatsPanel';

type Props = {
  data: StatsData;
  fps: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  activeSection?: string | null;
};

const normalizeShot = (s: string) => String(s || '').replace(/_cross$/i, '').trim();

// Export function to extract timeline instances for a section
export const extractTimelineInstances = (data: StatsData, activeSection: string | null, fps: number, playerView: 'both'|'P0'|'P1'): TimelineInstance[] => {
  if (!activeSection || !data || !Number.isFinite(fps) || fps <= 0) return [];
  const instances: TimelineInstance[] = [];
  
  try {
    // Winners
    if (activeSection === 'winners') {
      const extract = (rows?: CsvRow[]) => {
        if (!Array.isArray(rows)) return;
        for (const r of rows) {
          if (!r) continue;
          const f = parseInt(String(r.FrameNumber || r.LastShotFrame || ''), 10);
          const stroke = normalizeShot(String(r.Stroke || ''));
          if (Number.isFinite(f) && f > 0 && stroke) {
            instances.push({ timeSec: f / fps, label: stroke, category: stroke });
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract(data.p0Winners);
      if (playerView === 'both' || playerView === 'P1') extract(data.p1Winners);
      return instances;
    }
    
    // Errors
    if (activeSection === 'errors') {
      const extract = (rows?: CsvRow[]) => {
        if (!Array.isArray(rows)) return;
        for (const r of rows) {
          if (!r) continue;
          const f = parseInt(String(r.FrameNumber || r.LastShotFrame || ''), 10);
          const stroke = normalizeShot(String(r.Stroke || ''));
          if (Number.isFinite(f) && f > 0 && stroke) {
            instances.push({ timeSec: f / fps, label: stroke, category: stroke });
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract(data.p0Errors);
      if (playerView === 'both' || playerView === 'P1') extract(data.p1Errors);
      return instances;
    }
    
    // Shot Effectiveness (effective shots)
    if (activeSection === 'eff') {
      const rowsAll = Array.isArray(data.effectiveness) ? data.effectiveness.filter(r => {
        if (!r) return false;
        const stroke = String(r.Stroke || '').toLowerCase();
        const isServe = stroke.includes('serve') || String(r.is_serve || '').toLowerCase() === 'true';
        const label = String(r.effectiveness_label || r.Effectiveness_Label || '').toLowerCase();
        const isTerminal = label.includes('rally winner') || label.includes('forced error') || label.includes('unforced error') || label.startsWith('serve');
        return !isServe && !isTerminal;
      }) : [];
      const extract = (player: 'P0'|'P1') => {
        for (const r of rowsAll.filter(r => r && String(r.Player || '').toUpperCase() === player)) {
          const f = parseInt(String(r.FrameNumber || ''), 10);
          const stroke = normalizeShot(String(r.Stroke || ''));
          const color = String(r.color || '').toLowerCase();
          if (Number.isFinite(f) && f > 0 && stroke) {
            const type = color === 'green' ? 'effective' : (color === 'red' || color === 'darkred' ? 'ineffective' : '');
            instances.push({ timeSec: f / fps, label: `${stroke} (${type})`, category: stroke });
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract('P0');
      if (playerView === 'both' || playerView === 'P1') extract('P1');
      return instances;
    }
    
    // Service → Receive
    if (activeSection === 'sr') {
      const extract = (rows?: CsvRow[]) => {
        if (!Array.isArray(rows)) return;
        for (const r of rows) {
          if (!r) continue;
          const frames = String(r.Frames || '').trim();
          if (frames) {
            const parts = frames.split(',').map(s => s.trim()).filter(Boolean);
            for (const p of parts) {
              const m = p.match(/(\d+)\s*->\s*(\d+)/);
              if (m) {
                const frame = parseInt(m[1], 10);
                const serve = String(r.Serve_Shot || '').trim();
                const recv = String(r.Receive_Shot || '').trim();
                if (Number.isFinite(frame) && frame > 0) {
                  instances.push({ timeSec: frame / fps, label: `${serve} → ${recv}`, category: serve });
                }
              }
            }
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract(data.p0SrPatterns);
      if (playerView === 'both' || playerView === 'P1') extract(data.p1SrPatterns);
      return instances;
    }
    
    // Zones
    if (activeSection === 'zones') {
      const extract = (player: 'P0'|'P1') => {
        const rows = Array.isArray(data.zoneTopBottom) ? data.zoneTopBottom.filter(r => r && String(r.Player || '').toUpperCase() === player) : [];
        for (const r of rows) {
          const allFramesStr = String(r.AllFrames || '').trim();
          const zone = String(r.AnchorHittingZone || '').trim();
          if (allFramesStr) {
            const parts = allFramesStr.split('|').filter(Boolean);
            for (const part of parts) {
              const m = part.match(/F(\d+)/i);
              if (m) {
                const f = parseInt(m[1], 10);
                if (Number.isFinite(f) && f > 0 && zone) {
                  instances.push({ timeSec: f / fps, label: zone, category: zone });
                }
              }
            }
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract('P0');
      if (playerView === 'both' || playerView === 'P1') extract('P1');
      return instances;
    }
  } catch (err) {
    console.error('Error in extractTimelineInstances:', err);
    return [];
  }
  
  return instances;
};

const toSec = (frame: number, fps: number) => (Number.isFinite(frame) && fps > 0 ? frame / fps : 0);
const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current; if (!v) return; const s = Math.max(0, sec - 2); v.currentTime = s; v.play().catch(() => {});
};

// Shot categories for rally grouping (duplicated from StatsPanel)
const shotCategories = {
  Attacking: [
    'forehand_smash','overhead_smash','backhand_smash','forehand_halfsmash','overhead_halfsmash',
    'forehand_nettap','backhand_nettap',
    'forehand_drive','backhand_drive','flat_game','forehand_push','backhand_push',
  ],
  Defense: [
    'forehand_defense','backhand_defense','forehand_defense_cross','backhand_defense_cross'
  ],
  NetBattle: [
    'forehand_netkeep','backhand_netkeep','forehand_dribble','backhand_dribble'
  ],
  Placement: [
    'overhead_drop','forehand_drop','backhand_drop','forehand_pulldrop','backhand_pulldrop'
  ],
  Reset: [
    'forehand_lift','backhand_lift','forehand_clear','overhead_clear','backhand_clear'
  ],
};

const mapShotToBucket = (shot: string): keyof typeof shotCategories | 'Other' => {
  const n = normalizeShot(shot);
  for (const k of Object.keys(shotCategories) as (keyof typeof shotCategories)[]) {
    if (shotCategories[k].includes(n as any)) return k;
  }
  return 'Other';
};

const Section: React.FC<{ title: string; children?: React.ReactNode }>=({ title, children })=> (
  <div style={{ marginBottom: 12 }}>
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
    </div>
    <div style={{ marginTop: 8 }}>{children}</div>
  </div>
);

const BarCompare: React.FC<{ dataLeft: { label: string; value: number; frames: number[] }[]; dataRight: { label: string; value: number; frames: number[] }[]; fps: number; videoRef: Props['videoRef']; leftLabel?: string; rightLabel?: string; }>=({ dataLeft, dataRight, fps, videoRef, leftLabel='P0', rightLabel='P1' })=>{
  const all = [...dataLeft, ...dataRight];
  const max = Math.max(1, ...all.map(d => d.value || 0));
  const left = dataLeft.slice(0, 6);
  const right = dataRight.slice(0, 6);
  const Row: React.FC<{ side: 'left'|'right'; item: { label: string; value: number; frames: number[] } }>=({ side, item })=> (
    <div style={{ display:'grid', gridTemplateColumns:'1fr auto 1fr', alignItems:'center', gap:8 }}>
      <div style={{ display:'flex', justifyContent:'flex-end', gap:6 }}>
        {side==='left' && (
          <div title={`${item.label}: ${item.value}`} style={{ height: 10, width: `${(item.value/max)*100}%`, background:'#3b82f6', borderRadius: 4 }} />
        )}
      </div>
      <div style={{ fontSize: 12, opacity: 0.9, minWidth: 80, textAlign:'center' }}>{item.label} ({item.value})</div>
      <div style={{ display:'flex', justifyContent:'flex-start', gap:6 }}>
        {side==='right' && (
          <div title={`${item.label}: ${item.value}`} style={{ height: 10, width: `${(item.value/max)*100}%`, background:'#06b6d4', borderRadius: 4 }} />
        )}
      </div>
    </div>
  );
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom: 6, fontWeight: 600 }}>
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:8 }}>
        {left.map((it, i)=> <Row key={`l-${i}`} side="left" item={it} />)}
        {right.map((it, i)=> <Row key={`r-${i}`} side="right" item={it} />)}
      </div>
      <div style={{ marginTop: 8, display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
        {[...left, ...right].slice(0, 12).map((it, i) => {
          const f = it.frames[0]; const sec = toSec(f, fps);
          return (
            <div key={`bc-${i}`} onClick={()=>seek(videoRef, sec)} title={`${it.label} example`} style={{ padding:'0.35rem 0.6rem', background:'#eef2ff22', border:'1px solid #334155', borderRadius:999, fontSize:12, color:'#cbd5e1', cursor:'pointer', userSelect:'none' }}>
              [{formatMs(Math.max(0,(sec-2))*1000)}]
            </div>
          );
        })}
      </div>
    </div>
  );
};

const DivergingBar: React.FC<{ rows: { label: string; neg: number; pos: number }[] }>=({ rows })=>{
  const max = Math.max(1, ...rows.map(r => Math.max(r.neg, r.pos)));
  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:8 }}>
      {rows.map((r, i)=> (
        <div key={`db-${i}`} style={{ display:'grid', gridTemplateColumns:'1fr auto 1fr', alignItems:'center', gap:8 }}>
          <div style={{ display:'flex', justifyContent:'flex-end' }}>
            <div title={`Neg: ${r.neg}`} style={{ height: 10, width: `${(r.neg/max)*100}%`, background:'#ef4444', borderRadius:4 }} />
          </div>
          <div style={{ fontSize: 12, opacity: 0.9, minWidth: 140, textAlign:'center' }}>{r.label}</div>
          <div style={{ display:'flex', justifyContent:'flex-start' }}>
            <div title={`Pos: ${r.pos}`} style={{ height: 10, width: `${(r.pos/max)*100}%`, background:'#22c55e', borderRadius:4 }} />
          </div>
        </div>
      ))}
    </div>
  );
};

// Simple SVG Sankey-like flow for Serve -> Receive patterns
const SrSankey: React.FC<{ patterns: Array<{ serve: string; recv: string; count: number }>; title?: string }>=({ patterns, title })=>{
  const width = 640; const height = 220; const padding = 12;
  // Build nodes
  const serves = Array.from(new Set(patterns.map(p => p.serve)));
  const recvs = Array.from(new Set(patterns.map(p => p.recv)));
  const leftX = padding + 120; const rightX = width - padding - 120;
  const leftYGap = (height - 2*padding) / Math.max(1, serves.length);
  const rightYGap = (height - 2*padding) / Math.max(1, recvs.length);
  const servePos: Record<string, { x:number; y:number }> = {};
  const recvPos: Record<string, { x:number; y:number }> = {};
  serves.forEach((s, i) => { servePos[s] = { x: leftX, y: padding + i*leftYGap + leftYGap/2 }; });
  recvs.forEach((r, i) => { recvPos[r] = { x: rightX, y: padding + i*rightYGap + rightYGap/2 }; });
  const maxCount = Math.max(1, ...patterns.map(p => p.count));
  const link = (p: { serve:string; recv:string; count:number }, idx:number) => {
    const a = servePos[p.serve]; const b = recvPos[p.recv];
    const w = 2 + 10 * (p.count / maxCount);
    const cx1 = a.x + 120; const cx2 = b.x - 120;
    return (
      <g key={`ln-${idx}`}>
        <path d={`M ${a.x},${a.y} C ${cx1},${a.y} ${cx2},${b.y} ${b.x},${b.y}`} stroke="#64748b" strokeOpacity={0.9} strokeWidth={w} fill="none" />
      </g>
    );
  };
  return (
    <div>
      {title && <div style={{ fontWeight:700, marginBottom:6 }}>{title}</div>}
      <svg width={width} height={height} style={{ maxWidth:'100%', height:'auto', background:'#0b0f14', border:'1px solid #1f2937', borderRadius:6 }}>
        {/* Links */}
        {patterns.map(link)}
        {/* Left labels */}
        {serves.map((s, i)=> (
          <g key={`sl-${i}`}> 
            <circle cx={servePos[s].x} cy={servePos[s].y} r={6} fill="#3b82f6" />
            <text x={servePos[s].x-10} y={servePos[s].y} textAnchor="end" dominantBaseline="middle" fill="#cbd5e1" fontSize={12}>{s}</text>
          </g>
        ))}
        {/* Right labels */}
        {recvs.map((r, i)=> (
          <g key={`rl-${i}`}>
            <circle cx={recvPos[r].x} cy={recvPos[r].y} r={6} fill="#06b6d4" />
            <text x={recvPos[r].x+10} y={recvPos[r].y} textAnchor="start" dominantBaseline="middle" fill="#cbd5e1" fontSize={12}>{r}</text>
          </g>
        ))}
      </svg>
    </div>
  );
};

// Zone data type
type ZoneEffectData = {
  zone: string;
  type: 'effective' | 'ineffective' | null;
  uses: number;
  avgEffectiveness: number | null;
  frames: number[];
  shots: string[];
};

// Badminton Court with 6 zones
const BadmintonCourt: React.FC<{ zones: ZoneEffectData[]; title?: string; fps: number; videoRef: Props['videoRef'] }>=({ zones, title, fps, videoRef })=>{
  // 6 zones: back_right, back_left, middle_right, middle_left, front_right, front_left
  const zoneOrder = ['front_right', 'front_left', 'middle_right', 'middle_left', 'back_right', 'back_left'];
  const width = 360; const height = 240;
  const netY = 20;
  const frontRowY = netY + 20; const midRowY = frontRowY + 70; const backRowY = midRowY + 70;
  const leftX = width * 0.3; const rightX = width * 0.7;
  const cellW = width * 0.4; const cellH = 60;
  
  // Build zone map from data
  const zoneMap: Record<string, ZoneEffectData> = {};
  zones.forEach(z => {
    const key = z.zone.toLowerCase().replace(/\s+/g, '_');
    zoneMap[key] = z;
  });
  
  // Calculate max values for intensity (combination of uses and effectiveness) - only consider zones with data
  const zonesWithData = zones.filter(z => z.type !== null);
  const maxUses = zonesWithData.length > 0 ? Math.max(...zonesWithData.map(z => z.uses), 1) : 1;
  
  const getColor = (zone: ZoneEffectData | undefined) => {
    if (!zone || !zone.type) return '#1f2937'; // Grey for empty
    
    // Normalize uses (0-1) and effectiveness (0-1), then combine
    const usesNorm = zone.uses / maxUses;
    const effNorm = zone.avgEffectiveness ? (zone.avgEffectiveness / 100) : 0;
    const intensity = (usesNorm * 0.5 + effNorm * 0.5); // Combine 50/50
    
    if (zone.type === 'effective') {
      return `rgba(34, 197, 94, ${0.3 + 0.7 * intensity})`; // Green
    } else {
      return `rgba(239, 68, 68, ${0.3 + 0.7 * intensity})`; // Red
    }
  };
  
  const getZonePos = (zone: string) => {
    const key = zone.toLowerCase().replace(/\s+/g, '_');
    if (key === 'front_right') return { x: rightX - cellW/2, y: frontRowY, w: cellW, h: cellH };
    if (key === 'front_left') return { x: leftX - cellW/2, y: frontRowY, w: cellW, h: cellH };
    if (key === 'middle_right') return { x: rightX - cellW/2, y: midRowY, w: cellW, h: cellH };
    if (key === 'middle_left') return { x: leftX - cellW/2, y: midRowY, w: cellW, h: cellH };
    if (key === 'back_right') return { x: rightX - cellW/2, y: backRowY, w: cellW, h: cellH };
    if (key === 'back_left') return { x: leftX - cellW/2, y: backRowY, w: cellW, h: cellH };
    return { x: 0, y: 0, w: 0, h: 0 };
  };
  
  return (
    <div>
      {title && <div style={{ fontWeight:700, marginBottom:6 }}>{title}</div>}
      <svg width={width} height={height} style={{ maxWidth:'100%', height:'auto', background:'#0b0f14', border:'1px solid #1f2937', borderRadius:6 }}>
        {/* Net line */}
        <line x1={0} y1={netY} x2={width} y2={netY} stroke="#94a3b8" strokeWidth={2} strokeDasharray="4,4" />
        <text x={width/2} y={netY-5} textAnchor="middle" fill="#94a3b8" fontSize={10}>NET</text>
        
        {/* Court zones */}
        {zoneOrder.map((zoneKey) => {
          const zone = zoneMap[zoneKey];
          const pos = getZonePos(zoneKey);
          const color = getColor(zone);
          const label = zoneKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
          const info = zone ? `${zone.uses} uses, ${zone.avgEffectiveness?.toFixed(1) || 'N/A'}%` : 'No data';
          
          return (
            <g key={zoneKey}>
              <rect x={pos.x} y={pos.y} width={pos.w} height={pos.h} fill={color} stroke="#475569" strokeWidth={1} rx={2} />
              <text x={pos.x + pos.w/2} y={pos.y + 15} textAnchor="middle" fill="#e5e7eb" fontSize={11} fontWeight={600}>{label}</text>
              {zone && (
                <text x={pos.x + pos.w/2} y={pos.y + 30} textAnchor="middle" fill="#cbd5e1" fontSize={9}>{info}</text>
              )}
              <title>{zone ? `${label}: ${info}` : `${label}: No data`}</title>
            </g>
          );
        })}
      </svg>
      
      {/* Example frames for effective/ineffective zones */}
      {zones.filter(z => z.frames.length > 0).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Example shots:</div>
          <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
            {zones.flatMap((z, i) => 
              z.frames.slice(0, 8).map((f, j) => {
                const sec = toSec(f, fps);
                return (
                  <div key={`zone-${i}-${j}`} onClick={()=>seek(videoRef, sec)} title={`${z.zone} (${z.avgEffectiveness?.toFixed(1) || 'N/A'}%)`} style={{ padding:'0.35rem 0.6rem', background: z.type === 'effective' ? '#eef2ff22' : '#fef2f222', border:`1px solid ${z.type === 'effective' ? '#334155' : '#7f1d1d'}`, borderRadius:999, fontSize:12, color:'#cbd5e1', cursor:'pointer', userSelect:'none' }}>
                    [{formatMs(Math.max(0,(sec-2))*1000)}]
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// Rally Category Bar Chart - shows distribution by last shot category
const RallyCategoryBar: React.FC<{ data: { category: string; count: number; examples: Array<{ start: number; game: string; rally: string }> }[]; color: string; title?: string; fps: number; videoRef: Props['videoRef'] }>=({ data, color, title, fps, videoRef })=>{
  const max = Math.max(1, ...data.map(d => d.count));
  const order: (keyof typeof shotCategories | 'Other')[] = ['Attacking','Defense','NetBattle','Placement','Reset','Other'];
  const sorted = data.sort((a,b) => order.indexOf(a.category as any) - order.indexOf(b.category as any));
  return (
    <div>
      {title && <div style={{ fontWeight:700, marginBottom:6 }}>{title}</div>}
      <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:8 }}>
        {sorted.map((d, i) => (
          <div key={`rcb-${i}`}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
              <div style={{ minWidth: 100, fontSize: 12, opacity: 0.9 }}>{d.category}</div>
              <div style={{ flex:1, display:'flex', alignItems:'center', gap:4 }}>
                <div title={`${d.category}: ${d.count}`} style={{ height: 20, width: `${(d.count/max)*100}%`, background: color, borderRadius: 4 }} />
                <span style={{ fontSize: 11, opacity: 0.8 }}>{d.count}</span>
              </div>
            </div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem', marginTop: 4 }}>
              {d.examples.slice(0, 6).map((ex, j) => {
                const sec = toSec(ex.start, fps);
                return (
                  <div key={`ex-${i}-${j}`} onClick={()=>seek(videoRef, sec)} title={`G${ex.game}-R${ex.rally} (±2s)`} style={{ padding:'0.35rem 0.6rem', background:'#eef2ff22', border:'1px solid #334155', borderRadius:999, fontSize:12, color:'#cbd5e1', cursor:'pointer', userSelect:'none' }}>
                    [{formatMs(Math.max(0,(sec-2))*1000)}]
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Rally Timeline - colored markers across match time
const RallyTimeline: React.FC<{ rallies: Array<{ start: number; end: number; game: string; rally: string; lastShot: string; duration: number }>; color: string; title?: string; fps: number; videoRef: Props['videoRef']; maxTime?: number }>=({ rallies, color, title, fps, videoRef, maxTime })=>{
  if (!rallies.length) return null;
  const width = 600; const height = 60;
  const padding = 8;
  const minFrame = Math.min(...rallies.map(r => r.start));
  const maxFrame = maxTime ? Math.max(maxTime * fps, ...rallies.map(r => r.end)) : Math.max(...rallies.map(r => r.end));
  const frameRange = maxFrame - minFrame || 1;
  const x = (frame: number) => padding + ((frame - minFrame) / frameRange) * (width - 2*padding);
  return (
    <div>
      {title && <div style={{ fontWeight:700, marginBottom:6 }}>{title}</div>}
      <svg width={width} height={height} style={{ maxWidth:'100%', height:'auto', background:'#0b0f14', border:'1px solid #1f2937', borderRadius:6 }}>
        {/* Time axis */}
        <line x1={padding} y1={height-12} x2={width-padding} y2={height-12} stroke="#475569" strokeWidth={1} />
        {/* Rally markers */}
        {rallies.map((r, i) => {
          const xStart = x(r.start);
          const xEnd = x(r.end);
          const durationSec = r.duration / fps;
          return (
            <g key={`tm-${i}`}>
              <title>{`G${r.game}-R${r.rally} | ${r.lastShot} | ${durationSec.toFixed(1)}s`}</title>
              <rect x={xStart} y={8} width={Math.max(2, xEnd - xStart)} height={30} fill={color} fillOpacity={0.7} rx={2} style={{ cursor:'pointer' }} onClick={()=>seek(videoRef, toSec(r.start, fps))} />
              <circle cx={xStart} cy={23} r={4} fill={color} style={{ cursor:'pointer' }} onClick={()=>seek(videoRef, toSec(r.start, fps))} />
            </g>
          );
        })}
        {/* Time labels */}
        <text x={padding} y={height-2} fill="#94a3b8" fontSize={10}>{formatMs(Math.max(0, (minFrame/fps-2))*1000)}</text>
        <text x={width-padding} y={height-2} textAnchor="end" fill="#94a3b8" fontSize={10}>{formatMs(Math.max(0, (maxFrame/fps-2))*1000)}</text>
      </svg>
    </div>
  );
};

// Video Timeline Marker - shows instances on timeline strip below video
export type TimelineInstance = { timeSec: number; label: string; category?: string };
type VideoTimelineMarkerProps = { instances: TimelineInstance[]; sectionName: string; fps: number; videoRef: Props['videoRef']; videoDurationSec?: number; colorByCategory?: boolean };

export const VideoTimelineMarker: React.FC<VideoTimelineMarkerProps> = ({ instances, sectionName, fps: _fps, videoRef, videoDurationSec, colorByCategory = false }) => {
  if (!instances || instances.length === 0) return null;
  
  // Color palette for shot types (when colorByCategory is true)
  const shotColors: Record<string, string> = {
    'forehand_smash': '#22c55e', 'overhead_smash': '#10b981', 'backhand_smash': '#059669',
    'forehand_drop': '#3b82f6', 'overhead_drop': '#2563eb', 'backhand_drop': '#1d4ed8',
    'forehand_clear': '#60a5fa', 'overhead_clear': '#3b82f6', 'backhand_clear': '#2563eb',
    'forehand_netkeep': '#a78bfa', 'backhand_netkeep': '#8b5cf6', 'forehand_nettap': '#7c3aed',
    'forehand_drive': '#f59e0b', 'backhand_drive': '#d97706', 'forehand_push': '#eab308',
    'forehand_defense': '#ef4444', 'backhand_defense': '#dc2626',
  };
  
  const getColor = (inst: TimelineInstance): string => {
    if (colorByCategory && inst.category) {
      const key = inst.category.toLowerCase().replace(/_cross$/i, '');
      return shotColors[key] || '#64748b';
    }
    // Default section colors
    if (sectionName.includes('winner')) return '#22c55e';
    if (sectionName.includes('error')) return '#ef4444';
    if (sectionName.includes('effective')) return '#3b82f6';
    if (sectionName.includes('ineffective')) return '#ef4444';
    return '#64748b';
  };
  
  // Calculate video duration - prefer provided, otherwise calculate from max frame time
  if (instances.length === 0) return null;
  const maxTime = videoDurationSec && videoDurationSec > 0 ? videoDurationSec : Math.max(...instances.map(i => i.timeSec));
  const minTime = Math.min(...instances.map(i => i.timeSec));
  const timeRange = Math.max(1, maxTime - minTime);
  
  // Use video element width for responsive sizing
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        const video = videoRef.current;
        const targetWidth = video ? video.offsetWidth : containerRef.current.offsetWidth;
        setWidth(Math.max(400, targetWidth));
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    const resizeObserver = typeof ResizeObserver !== 'undefined' && containerRef.current ? new ResizeObserver(updateWidth) : null;
    if (resizeObserver && containerRef.current) resizeObserver.observe(containerRef.current);
    return () => {
      window.removeEventListener('resize', updateWidth);
      if (resizeObserver) resizeObserver.disconnect();
    };
  }, [videoRef]);
  
  const height = 50;
  const padding = 8;
  const x = (t: number) => padding + ((t - minTime) / timeRange) * (width - 2 * padding);
  
  // Cluster nearby instances (within 2 seconds) to avoid overlapping
  const clustered = useMemo(() => {
    const sorted = [...instances].sort((a, b) => a.timeSec - b.timeSec);
    const clusters: Array<{ timeSec: number; count: number; labels: string[]; category?: string }> = [];
    const threshold = 2; // seconds
    
    for (const inst of sorted) {
      const existing = clusters.find(c => Math.abs(c.timeSec - inst.timeSec) < threshold);
      if (existing) {
        existing.count += 1;
        existing.labels.push(inst.label);
      } else {
        clusters.push({ timeSec: inst.timeSec, count: 1, labels: [inst.label], category: inst.category });
      }
    }
    return clusters;
  }, [instances]);
  
  return (
    <div ref={containerRef} style={{ width: '100%', marginTop: 8 }}>
      <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 4, fontWeight: 600 }}>{sectionName}</div>
      <svg width={width} height={height} style={{ width: '100%', height: height, maxWidth: '100%', background: '#0b0f14', border: '1px solid #2c2c34', borderRadius: 4 }}>
        {/* Time axis */}
        <line x1={padding} y1={height-16} x2={width-padding} y2={height-16} stroke="#475569" strokeWidth={1.5} />
        
        {/* Time labels */}
        {[0, 0.25, 0.5, 0.75, 1].map(frac => {
          const t = minTime + frac * timeRange;
          const xPos = padding + frac * (width - 2 * padding);
          return (
            <g key={`label-${frac}`}>
              <line x1={xPos} y1={height-16} x2={xPos} y2={height-12} stroke="#475569" strokeWidth={1} />
              <text x={xPos} y={height-2} textAnchor="middle" fill="#94a3b8" fontSize={9}>{formatMs(t * 1000)}</text>
            </g>
          );
        })}
        
        {/* Instance markers */}
        {clustered.map((c, i) => {
          const color = getColor({ timeSec: c.timeSec, label: c.labels[0], category: c.category });
          const xPos = x(c.timeSec);
          const isClustered = c.count > 1;
          const tooltip = isClustered ? `${c.count} instances: ${c.labels.slice(0, 3).join(', ')}${c.labels.length > 3 ? '...' : ''}` : c.labels[0];
          
          return (
            <g key={`marker-${i}`}>
              <title>{tooltip} @ {formatMs(c.timeSec * 1000)}</title>
              <circle cx={xPos} cy={height-16} r={isClustered ? 5 : 4} fill={color} stroke="#0b0f14" strokeWidth={1} style={{ cursor: 'pointer' }} onClick={() => seek(videoRef, Math.max(0, c.timeSec - 2))} />
              {isClustered && <circle cx={xPos} cy={height-16} r={3} fill={color} opacity={0.3} />}
            </g>
          );
        })}
      </svg>
    </div>
  );
};

const StatsPanelV2: React.FC<Props & { onTimelineInstances?: (instances: TimelineInstance[], sectionName: string) => void }> = ({ data, fps, videoRef, activeSection, onTimelineInstances }) => {
  const [playerView, setPlayerView] = useState<'both'|'P0'|'P1'>('both');
  
  // Only show graph for the active section
  if (!activeSection) return null;
  
  // Extract and notify timeline instances whenever section or player view changes
  useEffect(() => {
    if (activeSection && onTimelineInstances) {
      try {
        const instances = extractTimelineInstances(data, activeSection, fps, playerView);
        const sectionNames: Record<string, string> = {
          'sr': 'Service → Receive',
          'winners': 'Winners',
          'errors': 'Errors',
          'eff': 'Shot Effectiveness',
          'zones': 'Zone Effectiveness',
        };
        onTimelineInstances(instances, sectionNames[activeSection] || activeSection);
      } catch (err) {
        console.error('Error extracting timeline instances:', err);
        onTimelineInstances([], activeSection);
      }
    } else if (onTimelineInstances) {
      onTimelineInstances([], '');
    }
  }, [activeSection, playerView, data, fps, onTimelineInstances]);
  // Winners grouped by stroke
  const groupByStroke = (rows?: CsvRow[]) => {
    const freq: Record<string, { label: string; value: number; frames: number[] }> = {};
    for (const r of rows || []) {
      const s = normalizeShot(String(r.Stroke || ''));
      const f = parseInt(String(r.FrameNumber || r.LastShotFrame || ''), 10);
      if (!Number.isFinite(f)) continue;
      if (!freq[s]) freq[s] = { label: s, value: 0, frames: [] };
      freq[s].value += 1; freq[s].frames.push(f);
    }
    return Object.values(freq).sort((a,b)=>b.value-a.value).slice(0,6);
  };
  const winnersP0 = useMemo(()=>groupByStroke(data.p0Winners), [data.p0Winners]);
  const winnersP1 = useMemo(()=>groupByStroke(data.p1Winners), [data.p1Winners]);
  const errorsCsvP0 = useMemo(()=>groupByStroke(data.p0Errors), [data.p0Errors]);
  const errorsCsvP1 = useMemo(()=>groupByStroke(data.p1Errors), [data.p1Errors]);

  // Effectiveness diverging per stroke (effective vs ineffective)
  type EffMap = Record<string, { eff: number; ineff: number }>;
  const effRows = useMemo(() => {
    const rowsAll = (data.effectiveness || []).filter(r => {
      const stroke = String(r.Stroke || '').toLowerCase();
      const isServe = stroke.includes('serve') || String(r.is_serve || '').toLowerCase() === 'true';
      const label = String(r.effectiveness_label || r.Effectiveness_Label || '').toLowerCase();
      const isTerminal = label.includes('rally winner') || label.includes('forced error') || label.includes('unforced error') || label.startsWith('serve');
      return !isServe && !isTerminal;
    });
    const build = (player: 'P0'|'P1') => {
      const eff: EffMap = {};
      for (const r of rowsAll.filter(r => String(r.Player || '').toUpperCase()===player)) {
        const stroke = normalizeShot(String(r.Stroke || ''));
        const color = String(r.color || '').toLowerCase();
        if (!eff[stroke]) eff[stroke] = { eff: 0, ineff: 0 };
        if (color === 'green') eff[stroke].eff += 1;
        else if (color === 'red' || color === 'darkred') eff[stroke].ineff += 1;
      }
      return Object.entries(eff).map(([k,v])=>({ label:k, neg:v.ineff, pos:v.eff })).sort((a,b)=> (b.pos-b.neg) - (a.pos-a.neg)).slice(0,6);
    };
    return { P0: build('P0'), P1: build('P1') };
  }, [data.effectiveness]);

  // Errors diverging using effectiveness labels (final shots)
  const errorRows = useMemo(() => {
    const norm = (s: string) => String(s || '').toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    const rowsAll = (data.effectiveness || []).filter(r => {
      const stroke = String(r.Stroke || '').toLowerCase();
      const isServe = stroke.includes('serve') || String(r.is_serve || '').toLowerCase() === 'true';
      const label = norm(String(r.effectiveness_label || r.Effectiveness_Label || r.reason || r.Reason || ''));
      const hasUnforced = /\bunforced\b/.test(label) || /\bue\b/.test(label);
      const hasForced = /\bforced\b/.test(label) || /\bfe\b/.test(label);
      return !isServe && (hasForced || hasUnforced);
    });
    const build = (player: 'P0'|'P1') => {
      const map: Record<string, { unforced: number; forced: number }> = {};
      for (const r of rowsAll.filter(r => String(r.Player || '').toUpperCase()===player)) {
        const stroke = normalizeShot(String(r.Stroke || ''));
        const label = norm(String(r.effectiveness_label || r.Effectiveness_Label || r.reason || r.Reason || ''));
        if (!map[stroke]) map[stroke] = { unforced: 0, forced: 0 };
        const isUnf = /\bunforced\b/.test(label) || /\bue\b/.test(label);
        const isFor = !isUnf && (/(^|\b)forced(\b|$)/.test(label) || /\bfe\b/.test(label));
        if (isUnf) map[stroke].unforced += 1; else if (isFor) map[stroke].forced += 1;
      }
      return Object.entries(map).map(([k,v])=>({ label:k, neg:v.unforced, pos:v.forced })).sort((a,b)=> (b.pos-b.neg) - (a.pos-a.neg)).slice(0,6);
    };
    return { P0: build('P0'), P1: build('P1') };
  }, [data.effectiveness]);

  // Zone effectiveness - parse CSV and combine effective/ineffective zones
  const zoneSummary = useMemo(() => {
    const parse = (player: 'P0'|'P1'): ZoneEffectData[] => {
      const rows = (data.zoneTopBottom || []).filter(r => String(r.Player || '').toUpperCase() === player);
      const zoneMap: Record<string, ZoneEffectData> = {};
      
      // Initialize all 6 zones with null data
      const allZones = ['back_right', 'back_left', 'middle_right', 'middle_left', 'front_right', 'front_left'];
      allZones.forEach(zone => {
        zoneMap[zone] = { zone, type: null, uses: 0, avgEffectiveness: null, frames: [], shots: [] };
      });
      
      // Fill in data from CSV
      for (const r of rows) {
        const zone = String(r.AnchorHittingZone || '').trim().toLowerCase().replace(/\s+/g, '_');
        const type = String(r.ZoneType || '').toLowerCase();
        const uses = parseInt(String(r.Uses || ''), 10);
        const avgEff = Number.isFinite(parseFloat(String(r.AvgEffectiveness || ''))) ? parseFloat(String(r.AvgEffectiveness)) : null;
        const shotsStr = String(r.Shots || '').trim();
        const allFramesStr = String(r.AllFrames || '').trim();
        
        if (zoneMap[zone]) {
          zoneMap[zone].type = type === 'most_effective' ? 'effective' : (type === 'most_ineffective' ? 'ineffective' : null);
          zoneMap[zone].uses = Number.isFinite(uses) ? uses : 0;
          zoneMap[zone].avgEffectiveness = avgEff;
          zoneMap[zone].shots = shotsStr ? shotsStr.split(',').map(s => s.trim()).filter(Boolean) : [];
          
          // Parse frames from AllFrames (format: G1-R6-F9836|G1-R6-F9892)
          const frames: number[] = [];
          if (allFramesStr) {
            const parts = allFramesStr.split('|');
            for (const part of parts) {
              const m = part.match(/F(\d+)/i);
              if (m) {
                const f = parseInt(m[1], 10);
                if (Number.isFinite(f)) frames.push(f);
              }
            }
          }
          zoneMap[zone].frames = frames;
        }
      }
      
      return Object.values(zoneMap);
    };
    
    return { P0: parse('P0'), P1: parse('P1') };
  }, [data.zoneTopBottom]);

  // Service -> Receive Sankey data
  const srPatterns = useMemo(() => {
    const parse = (rows?: CsvRow[]) => {
      const r = rows || [];
      const items: Array<{ serve:string; recv:string; count:number }> = [];
      for (const row of r) {
        const serve = String(row.Serve_Shot || '').trim();
        const recv = String(row.Receive_Shot || '').trim();
        const count = parseInt(String(row.Count || '0'), 10) || 0;
        if (serve && recv && count>0) items.push({ serve, recv, count });
      }
      // collapse duplicates
      const keyMap: Record<string, { serve:string; recv:string; count:number }> = {};
      for (const it of items) {
        const k = `${it.serve}__${it.recv}`;
        if (!keyMap[k]) keyMap[k] = { ...it };
        else keyMap[k].count += it.count;
      }
      return Object.values(keyMap).sort((a,b)=>b.count-a.count).slice(0,10);
    };
    return { P0: parse(data.p0SrPatterns), P1: parse(data.p1SrPatterns) };
  }, [data.p0SrPatterns, data.p1SrPatterns]);

  // Winning/Losing Rallies - grouped by last shot category
  type RallyData = { start: number; end: number; game: string; rally: string; lastShot: string; duration: number };
  const rallyData = useMemo(() => {
    const parse = (rows?: CsvRow[]): RallyData[] => {
      const r = rows || [];
      const rallies: RallyData[] = [];
      for (const row of r) {
        const start = parseInt(String(row.StartFrame || ''), 10);
        const end = parseInt(String(row.EndFrame || ''), 10);
        const lastShot = String(row.LastShot || row.LastShotName || row.LastShotType || '').trim();
        const game = String(row.GameNumber || '');
        const rally = String(row.RallyNumber || '');
        if (Number.isFinite(start) && Number.isFinite(end) && lastShot) {
          rallies.push({ start, end, game, rally, lastShot, duration: end - start });
        }
      }
      return rallies;
    };
    return {
      winning: { P0: parse(data.p0WinningRallies), P1: parse(data.p1WinningRallies) },
      losing: { P0: parse(data.p0LosingRallies), P1: parse(data.p1LosingRallies) },
    };
  }, [data.p0WinningRallies, data.p1WinningRallies, data.p0LosingRallies, data.p1LosingRallies]);

  // Group rallies by category for bar chart
  const rallyByCategory = useMemo(() => {
    const group = (rallies: RallyData[]) => {
      const buckets: Record<string, { count: number; examples: Array<{ start: number; game: string; rally: string }> }> = {};
      for (const r of rallies) {
        const cat = mapShotToBucket(r.lastShot);
        if (!buckets[cat]) buckets[cat] = { count: 0, examples: [] };
        buckets[cat].count += 1;
        buckets[cat].examples.push({ start: r.start, game: r.game, rally: r.rally });
      }
      return Object.entries(buckets).map(([category, data]) => ({ category, count: data.count, examples: data.examples })).filter(x => x.count > 0);
    };
    return {
      winning: { P0: group(rallyData.winning.P0), P1: group(rallyData.winning.P1) },
      losing: { P0: group(rallyData.losing.P0), P1: group(rallyData.losing.P1) },
    };
  }, [rallyData]);

  // Calculate max time for timeline (use all rallies)
  const maxMatchTime = useMemo(() => {
    const allFrames = [
      ...rallyData.winning.P0.map(r => r.end),
      ...rallyData.winning.P1.map(r => r.end),
      ...rallyData.losing.P0.map(r => r.end),
      ...rallyData.losing.P1.map(r => r.end),
    ];
    return allFrames.length > 0 ? Math.max(...allFrames) / fps : 0;
  }, [rallyData, fps]);

  // Shot Distribution Heatmap
  type ShotDistRow = { Player:string; HittingZone:string; ShotType:string; Direction:string; LandingPosition:string; Count:number };
  const shotDist = useMemo(() => {
    const rows = (data.shotDistribution || []) as unknown as CsvRow[];
    const parsed: ShotDistRow[] = [];
    for (const r of rows) {
      const player = String(r.Player || '').toUpperCase();
      const hz = String(r.HittingZone || '').trim();
      const st = String(r.ShotType || '').trim();
      const dir = String(r.Direction || '').trim().toLowerCase();
      const lp = String(r.LandingPosition || '').trim();
      const cnt = parseInt(String(r.Count || '0'), 10) || 0;
      if (!player || !hz || !st || !dir || !lp || cnt <= 0) continue;
      parsed.push({ Player: player, HittingZone: hz, ShotType: st, Direction: dir, LandingPosition: lp, Count: cnt });
    }
    return parsed;
  }, [data.shotDistribution]);

  // Bar view helpers for shot distribution
  const [selectedZone, setSelectedZone] = useState<string>('All zones');
  const allZones = useMemo(() => {
    const z = Array.from(new Set(shotDist.map(r => r.HittingZone)));
    return ['All zones', ...z];
  }, [shotDist]);

  type ShotRow = { baseShot: string; straight: number; cross: number; total: number };
  const buildShotRows = (player: 'P0'|'P1', zone: string): ShotRow[] => {
    const filtered = shotDist.filter(r => r.Player === player && (zone === 'All zones' || r.HittingZone === zone));
    const map: Record<string, { straight: number; cross: number; total: number }> = {};
    for (const r of filtered) {
      const base = String(r.ShotType || '').replace(/_cross$/i, '');
      const variant = (String(r.Direction || '').toLowerCase() === 'cross') ? 'cross' : 'straight';
      if (!map[base]) map[base] = { straight: 0, cross: 0, total: 0 };
      map[base][variant] += r.Count;
      map[base].total += r.Count;
    }
    return Object.entries(map)
      .map(([baseShot, v]) => ({ baseShot, straight: v.straight, cross: v.cross, total: v.total }))
      .sort((a, b) => b.total - a.total);
  };

  const ShotBars: React.FC<{ rows: ShotRow[]; title?: string }>=({ rows, title }) => {
    if (!rows || rows.length === 0) return null;
    const max = Math.max(1, ...rows.map(r => Math.max(r.straight, r.cross)));
    const color = { straight: '#3b82f6', cross: '#06b6d4' } as const;
    return (
      <div>
        {title && <div style={{ fontWeight:700, marginBottom:6 }}>{title}</div>}
        <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:8 }}>
          {rows.map((r, i) => (
            <div key={`sb-${i}`}>
              <div style={{ display:'grid', gridTemplateColumns:'140px 1fr', alignItems:'center', gap:10 }}>
                <div style={{ fontSize:12, opacity:0.9 }}>{r.baseShot}</div>
                <div>
                  <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
                    <div title={`Straight: ${r.straight}`} style={{ height: 10, width: `${(r.straight/max)*100}%`, background: color.straight, borderRadius: 4 }} />
                    <span style={{ fontSize:11, opacity:0.8 }}>{r.straight}</span>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <div title={`Cross: ${r.cross}`} style={{ height: 10, width: `${(r.cross/max)*100}%`, background: color.cross, borderRadius: 4 }} />
                    <span style={{ fontSize:11, opacity:0.8 }}>{r.cross}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div>
      <div style={{ display:'flex', gap:6, marginBottom: 12, alignItems:'center' }}>
        <span style={{ fontSize: 12, opacity: 0.8 }}>Player view:</span>
        <button onClick={()=>setPlayerView('both')} style={{ padding:'4px 8px', borderRadius: 6, border:'1px solid #2c2c34', background: playerView==='both' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Both</button>
        <button onClick={()=>setPlayerView('P0')} style={{ padding:'4px 8px', borderRadius: 6, border:'1px solid #2c2c34', background: playerView==='P0' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>P0</button>
        <button onClick={()=>setPlayerView('P1')} style={{ padding:'4px 8px', borderRadius: 6, border:'1px solid #2c2c34', background: playerView==='P1' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>P1</button>
      </div>

      {activeSection === 'sr' && (srPatterns.P0.length>0 || srPatterns.P1.length>0) && (
        <Section title="Serve → Receive (top patterns)">
          {playerView==='both' ? (
            <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:12 }}>
              {srPatterns.P0.length>0 && <SrSankey patterns={srPatterns.P0} title="P0" />}
              {srPatterns.P1.length>0 && <SrSankey patterns={srPatterns.P1} title="P1" />}
            </div>
          ) : playerView==='P0' ? (
            srPatterns.P0.length>0 ? <SrSankey patterns={srPatterns.P0} title="P0" /> : null
          ) : (
            srPatterns.P1.length>0 ? <SrSankey patterns={srPatterns.P1} title="P1" /> : null
          )}
        </Section>
      )}

      {activeSection === 'winners' && (winnersP0.length>0 || winnersP1.length>0) && (
        <Section title="Winners (top strokes)">
          {playerView==='both' ? (
            <BarCompare dataLeft={winnersP0} dataRight={winnersP1} fps={fps} videoRef={videoRef} leftLabel="P0" rightLabel="P1" />
          ) : playerView==='P0' ? (
            <BarCompare dataLeft={winnersP0} dataRight={[]} fps={fps} videoRef={videoRef} leftLabel="P0" rightLabel="" />
          ) : (
            <BarCompare dataLeft={[]} dataRight={winnersP1} fps={fps} videoRef={videoRef} leftLabel="" rightLabel="P1" />
          )}
        </Section>
      )}

      {activeSection === 'errors' && (errorsCsvP0.length>0 || errorsCsvP1.length>0) && (
        <Section title="Errors (top strokes)">
          {playerView==='both' ? (
            <BarCompare dataLeft={errorsCsvP0} dataRight={errorsCsvP1} fps={fps} videoRef={videoRef} leftLabel="P0" rightLabel="P1" />
          ) : playerView==='P0' ? (
            <BarCompare dataLeft={errorsCsvP0} dataRight={[]} fps={fps} videoRef={videoRef} leftLabel="P0" rightLabel="" />
          ) : (
            <BarCompare dataLeft={[]} dataRight={errorsCsvP1} fps={fps} videoRef={videoRef} leftLabel="" rightLabel="P1" />
          )}
        </Section>
      )}

      {activeSection === 'eff' && (
        <>
          {(effRows.P0.length>0 || effRows.P1.length>0) && (
            <Section title="Shot effectiveness (ineffective vs effective)">
              {playerView==='both' ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                  <div>
                    <div style={{ fontWeight:700, marginBottom:6 }}>P0</div>
                    <DivergingBar rows={effRows.P0} />
                  </div>
                  <div>
                    <div style={{ fontWeight:700, marginBottom:6 }}>P1</div>
                    <DivergingBar rows={effRows.P1} />
                  </div>
                </div>
              ) : playerView==='P0' ? (
                <div>
                  <div style={{ fontWeight:700, marginBottom:6 }}>P0</div>
                  <DivergingBar rows={effRows.P0} />
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight:700, marginBottom:6 }}>P1</div>
                  <DivergingBar rows={effRows.P1} />
                </div>
              )}
            </Section>
          )}
          {(errorRows.P0.length>0 || errorRows.P1.length>0) && (
            <Section title="Terminal errors (unforced vs forced)">
              {playerView==='both' ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                  <div>
                    <div style={{ fontWeight:700, marginBottom:6 }}>P0</div>
                    <DivergingBar rows={errorRows.P0} />
                  </div>
                  <div>
                    <div style={{ fontWeight:700, marginBottom:6 }}>P1</div>
                    <DivergingBar rows={errorRows.P1} />
                  </div>
                </div>
              ) : playerView==='P0' ? (
                <div>
                  <div style={{ fontWeight:700, marginBottom:6 }}>P0</div>
                  <DivergingBar rows={errorRows.P0} />
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight:700, marginBottom:6 }}>P1</div>
                  <DivergingBar rows={errorRows.P1} />
                </div>
              )}
            </Section>
          )}
        </>
      )}

      {activeSection === 'zones' && ((zoneSummary.P0 && zoneSummary.P0.length>0) || (zoneSummary.P1 && zoneSummary.P1.length>0)) && (
        <Section title="Zone effectiveness (combined view)">
          {playerView==='both' ? (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <BadmintonCourt zones={zoneSummary.P0} title="P0" fps={fps} videoRef={videoRef} />
              <BadmintonCourt zones={zoneSummary.P1} title="P1" fps={fps} videoRef={videoRef} />
            </div>
          ) : playerView==='P0' ? (
            <BadmintonCourt zones={zoneSummary.P0} title="P0" fps={fps} videoRef={videoRef} />
          ) : (
            <BadmintonCourt zones={zoneSummary.P1} title="P1" fps={fps} videoRef={videoRef} />
          )}
        </Section>
      )}

      {activeSection === 'winRallies' && (
        <>
          {(rallyByCategory.winning.P0.length>0 || rallyByCategory.winning.P1.length>0) && (
            <Section title="Winning rallies (by last shot category)">
              {playerView==='both' ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                  {rallyByCategory.winning.P0.length>0 && <RallyCategoryBar data={rallyByCategory.winning.P0} color="#22c55e" title="P0" fps={fps} videoRef={videoRef} />}
                  {rallyByCategory.winning.P1.length>0 && <RallyCategoryBar data={rallyByCategory.winning.P1} color="#22c55e" title="P1" fps={fps} videoRef={videoRef} />}
                </div>
              ) : playerView==='P0' ? (
                rallyByCategory.winning.P0.length>0 ? <RallyCategoryBar data={rallyByCategory.winning.P0} color="#22c55e" title="P0" fps={fps} videoRef={videoRef} /> : null
              ) : (
                rallyByCategory.winning.P1.length>0 ? <RallyCategoryBar data={rallyByCategory.winning.P1} color="#22c55e" title="P1" fps={fps} videoRef={videoRef} /> : null
              )}
            </Section>
          )}
          {((rallyData.winning.P0.length>0 || rallyData.winning.P1.length>0) && maxMatchTime > 0) && (
            <Section title="Winning rallies timeline">
              {playerView==='both' ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:12 }}>
                  {rallyData.winning.P0.length>0 && <RallyTimeline rallies={rallyData.winning.P0} color="#22c55e" title="P0" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} />}
                  {rallyData.winning.P1.length>0 && <RallyTimeline rallies={rallyData.winning.P1} color="#22c55e" title="P1" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} />}
                </div>
              ) : playerView==='P0' ? (
                rallyData.winning.P0.length>0 ? <RallyTimeline rallies={rallyData.winning.P0} color="#22c55e" title="P0" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} /> : null
              ) : (
                rallyData.winning.P1.length>0 ? <RallyTimeline rallies={rallyData.winning.P1} color="#22c55e" title="P1" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} /> : null
              )}
            </Section>
          )}
        </>
      )}

      {activeSection === 'loseRallies' && (
        <>
          {(rallyByCategory.losing.P0.length>0 || rallyByCategory.losing.P1.length>0) && (
            <Section title="Losing rallies (by last shot category)">
              {playerView==='both' ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                  {rallyByCategory.losing.P0.length>0 && <RallyCategoryBar data={rallyByCategory.losing.P0} color="#ef4444" title="P0" fps={fps} videoRef={videoRef} />}
                  {rallyByCategory.losing.P1.length>0 && <RallyCategoryBar data={rallyByCategory.losing.P1} color="#ef4444" title="P1" fps={fps} videoRef={videoRef} />}
                </div>
              ) : playerView==='P0' ? (
                rallyByCategory.losing.P0.length>0 ? <RallyCategoryBar data={rallyByCategory.losing.P0} color="#ef4444" title="P0" fps={fps} videoRef={videoRef} /> : null
              ) : (
                rallyByCategory.losing.P1.length>0 ? <RallyCategoryBar data={rallyByCategory.losing.P1} color="#ef4444" title="P1" fps={fps} videoRef={videoRef} /> : null
              )}
            </Section>
          )}
          {((rallyData.losing.P0.length>0 || rallyData.losing.P1.length>0) && maxMatchTime > 0) && (
            <Section title="Losing rallies timeline">
              {playerView==='both' ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr', gap:12 }}>
                  {rallyData.losing.P0.length>0 && <RallyTimeline rallies={rallyData.losing.P0} color="#ef4444" title="P0" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} />}
                  {rallyData.losing.P1.length>0 && <RallyTimeline rallies={rallyData.losing.P1} color="#ef4444" title="P1" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} />}
                </div>
              ) : playerView==='P0' ? (
                rallyData.losing.P0.length>0 ? <RallyTimeline rallies={rallyData.losing.P0} color="#ef4444" title="P0" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} /> : null
              ) : (
                rallyData.losing.P1.length>0 ? <RallyTimeline rallies={rallyData.losing.P1} color="#ef4444" title="P1" fps={fps} videoRef={videoRef} maxTime={maxMatchTime} /> : null
              )}
            </Section>
          )}
        </>
      )}

      {activeSection === 'shotDist' && shotDist.length > 0 && (
        <Section title="Shot distribution (bars)">
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom: 8 }}>
            <span style={{ fontSize: 12, opacity: 0.8 }}>Zone:</span>
            <select value={selectedZone} onChange={(e)=>setSelectedZone(e.target.value)} style={{ background:'#0f0f15', color:'#e5e7eb', border:'1px solid #2c2c34', borderRadius:6, padding:'4px 6px' }}>
              {allZones.map(z => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
          {playerView==='both' ? (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <ShotBars rows={buildShotRows('P0', selectedZone)} title="P0" />
              <ShotBars rows={buildShotRows('P1', selectedZone)} title="P1" />
            </div>
          ) : playerView==='P0' ? (
            <ShotBars rows={buildShotRows('P0', selectedZone)} title="P0" />
          ) : (
            <ShotBars rows={buildShotRows('P1', selectedZone)} title="P1" />
          )}
        </Section>
      )}
    </div>
  );
};

export default StatsPanelV2;


