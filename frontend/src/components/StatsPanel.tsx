import React, { useMemo, useState } from 'react';
import { formatMs } from '../utils/timecode';

export type CsvRow = Record<string, string>;

export type StatsData = {
  p0SrPatterns?: CsvRow[]; // new: P0 service-receive patterns
  p1SrPatterns?: CsvRow[];
  p0Winners?: CsvRow[];
  p1Winners?: CsvRow[];
  p0Errors?: CsvRow[];
  p1Errors?: CsvRow[];
  p0WinningRallies?: CsvRow[];
  p1WinningRallies?: CsvRow[];
  p0LosingRallies?: CsvRow[];
  p1LosingRallies?: CsvRow[];
  threeShot?: CsvRow[];
  effectiveness?: CsvRow[]; // new: *_detailed_effectiveness.csv
  zoneTopBottom?: CsvRow[]; // new: zone_effectiveness_top_vs_bottom.csv
  shotDistribution?: CsvRow[]; // new: shot distribution by zone/direction/landing
};

type Props = {
  data: StatsData;
  fps: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onSectionExpanded?: (section: string | null) => void;
  uiVersion?: 'v1' | 'v2';
};

const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current; if (!v) return;
  const s = Math.max(0, sec - 2); // -2s padding
  v.currentTime = s; v.play().catch(() => {});
};

const toSec = (frame: number, fps: number) => (Number.isFinite(frame) && fps > 0 ? frame / fps : 0);

const normalizeShot = (s: string) => String(s || '').replace(/_cross$/i, '').trim();

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

const SectionHeader: React.FC<{title: string, rightText?: string, onClick: ()=>void, collapsed: boolean}> = ({ title, rightText, onClick, collapsed }) => (
  <div onClick={onClick} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', cursor:'pointer' }}>
    <h3 style={{ margin: 0 }}>{title}</h3>
    <div style={{ display:'inline-flex', alignItems:'center', gap:8, opacity:0.7 }}>
      {rightText && <span style={{ fontSize: 12 }}>{rightText}</span>}
      <span>{collapsed ? '▼' : '▲'}</span>
    </div>
  </div>
);

const Chip: React.FC<{label: string, title?: string, onClick?: ()=>void}> = ({ label, title, onClick }) => (
  <div onClick={onClick}
    title={title}
    style={{ padding:'0.35rem 0.6rem', background:'#eef2ff22', border:'1px solid #334155', borderRadius:999, fontSize:12, color:'#cbd5e1', cursor:'pointer', userSelect:'none' }}>
    {label}
  </div>
);

export const StatsPanel: React.FC<Props> = ({ data, fps, videoRef, onSectionExpanded, uiVersion }) => {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({
    sr: true,
    winners: true,
    errors: true,
    winRallies: true,
    loseRallies: true,
    threeShot: true,
    eff: true,
    zones: true,
    shotDist: true,
  });

  const toggle = (k: string) => {
    setCollapsed(prev => {
      const newState = { ...prev, [k]: !prev[k] };
      if (onSectionExpanded) {
        // If section is expanded (not collapsed), notify parent
        onSectionExpanded(!newState[k] ? k : null);
      }
      return newState;
    });
  };

  // SR patterns: helper to compute top 4 combos
  const computeSrTop = (rows?: CsvRow[]) => {
    const r = rows || [];
    type Key = { serve: string; recv: string };
    const freq: Record<string, { key: Key; count: number; ranges: Array<[number,number]> }> = {};
    for (const row of r) {
      const serve = String(row.Serve_Shot || '').trim();
      const recv = String(row.Receive_Shot || '').trim();
      const key = `${serve}→${recv}`;
      const count = parseInt(String(row.Count || '0'), 10) || 0;
      const ranges: Array<[number,number]> = [];
      const frames = String(row.Frames || '').trim();
      if (frames) {
        const parts = frames.split(',').map(s => s.trim());
        for (const p of parts) {
          const m = p.match(/(\d+)\s*->\s*(\d+)/);
          if (m) ranges.push([parseInt(m[1],10), parseInt(m[2],10)]);
        }
      }
      if (!freq[key]) freq[key] = { key: { serve, recv }, count: 0, ranges: [] };
      freq[key].count += count;
      freq[key].ranges.push(...ranges);
    }
    return Object.values(freq).sort((a,b)=>b.count-a.count).slice(0,4);
  };

  const srTopP0 = useMemo(() => computeSrTop(data.p0SrPatterns), [data.p0SrPatterns]);
  const srTopP1 = useMemo(() => computeSrTop(data.p1SrPatterns), [data.p1SrPatterns]);

  // 2) Winners (top 4 by stroke) & 3) Errors (top 4 by stroke)
  const groupByStrokeTop = (rows?: CsvRow[]) => {
    const freq: Record<string, { stroke: string; frames: number[]; count: number }> = {};
    for (const r of rows || []) {
      const s = normalizeShot(String(r.Stroke || ''));
      const f = parseInt(String(r.FrameNumber || r.LastShotFrame || ''), 10);
      if (!Number.isFinite(f)) continue;
      if (!freq[s]) freq[s] = { stroke: s, frames: [], count: 0 };
      freq[s].frames.push(f); freq[s].count += 1;
    }
    return Object.values(freq).sort((a,b)=>b.count-a.count).slice(0,4);
  };

  const winnersP0 = useMemo(()=>groupByStrokeTop(data.p0Winners), [data.p0Winners]);
  const winnersP1 = useMemo(()=>groupByStrokeTop(data.p1Winners), [data.p1Winners]);
  const errorsP0 = useMemo(()=>groupByStrokeTop(data.p0Errors), [data.p0Errors]);
  const errorsP1 = useMemo(()=>groupByStrokeTop(data.p1Errors), [data.p1Errors]);

  // 4) Winning/Losing rallies grouped by bucket
  type RallyItem = { game?: string; rally?: string; start?: number; end?: number; lastShot?: string };
  const groupRallies = (rows?: CsvRow[]) => {
    const buckets: Record<string, RallyItem[]> = {};
    for (const r of rows || []) {
      const last = String(r.LastShot || r.LastShotName || r.LastShotType || '').trim();
      const bucket = mapShotToBucket(last);
      const start = parseInt(String(r.StartFrame || ''), 10);
      const end = parseInt(String(r.EndFrame || ''), 10);
      const g = String(r.GameNumber || '');
      const ry = String(r.RallyNumber || '');
      const item: RallyItem = { game: g, rally: ry, start, end, lastShot: last };
      const k = bucket;
      if (!buckets[k]) buckets[k] = [];
      buckets[k].push(item);
    }
    return buckets;
  };

  const winBucketsP0 = useMemo(()=>groupRallies(data.p0WinningRallies), [data.p0WinningRallies]);
  const winBucketsP1 = useMemo(()=>groupRallies(data.p1WinningRallies), [data.p1WinningRallies]);
  const loseBucketsP0 = useMemo(()=>groupRallies(data.p0LosingRallies), [data.p0LosingRallies]);
  const loseBucketsP1 = useMemo(()=>groupRallies(data.p1LosingRallies), [data.p1LosingRallies]);

  // 5) 3-shot sequences (top 10)
  const threeShotTop = useMemo(() => {
    const rows = data.threeShot || [];
    return rows.slice(0, 10);
  }, [data.threeShot]);

  // 6) Effectiveness CSV: top 4 effective/ineffective per player, excluding serves (as before)
  type EffMap = Record<string, { stroke: string; frames: number[]; count: number }>;
  type EffSummary = { topEff: EffMap[keyof EffMap][], topIneff: EffMap[keyof EffMap][] };
  const effByPlayer = useMemo(() => {
    const rowsAll = (data.effectiveness || []).filter(r => {
      const stroke = String(r.Stroke || '').toLowerCase();
      const isServe = stroke.includes('serve') || String(r.is_serve || '').toLowerCase() === 'true';
      // Exclude terminal shots: winners and errors are already shown elsewhere
      const label = String(r.effectiveness_label || r.Effectiveness_Label || '').toLowerCase();
      const isTerminal = label.includes('rally winner')
        || label.includes('forced error')
        || label.includes('unforced error')
        || label.startsWith('serve');
      return !isServe && !isTerminal;
    });
    const build = (player: 'P0' | 'P1'): EffSummary => {
      const rows = rowsAll.filter(r => String(r.Player || '').toUpperCase() === player);
      const effective: EffMap = {};
      const ineffective: EffMap = {};
      for (const r of rows) {
        const color = String(r.color || '').toLowerCase();
        const stroke = normalizeShot(String(r.Stroke || ''));
        const f = parseInt(String(r.FrameNumber || ''), 10);
        if (!Number.isFinite(f) || !stroke) continue;
        if (color === 'green') {
          if (!effective[stroke]) effective[stroke] = { stroke, frames: [], count: 0 };
          effective[stroke].frames.push(f); effective[stroke].count += 1;
        } else if (color === 'red' || color === 'darkred') {
          if (!ineffective[stroke]) ineffective[stroke] = { stroke, frames: [], count: 0 };
          ineffective[stroke].frames.push(f); ineffective[stroke].count += 1;
        }
      }
      const effSorted = Object.values(effective).sort((a,b)=>b.count-a.count);
      const ineffSorted = Object.values(ineffective).sort((a,b)=>b.count-a.count);
      const decideTopN = (arr: EffMap[keyof EffMap][]) => {
        if (arr.length === 0) return 0;
        // Default target 6; fallback to 4 if both 5th and 6th have < 4 counts
        if (arr.length >= 6) {
          const fifth = arr[4]?.count || 0;
          const sixth = arr[5]?.count || 0;
          if (fifth < 4 && sixth < 4) return 4;
          return 6;
        }
        // If fewer than 6 available, show all (even 5) unless fewer than 4 total items
        return Math.min(6, arr.length);
      };
      const nEff = decideTopN(effSorted);
      const nIneff = decideTopN(ineffSorted);
      const topEff = effSorted.slice(0, nEff);
      const topIneff = ineffSorted.slice(0, nIneff);
      return { topEff, topIneff };
    };
    return { P0: build('P0'), P1: build('P1') };
  }, [data.effectiveness]);

  // 7) Zone effectiveness top vs bottom (per player)
  type ZoneRow = { player: 'P0' | 'P1'; type: 'most_effective' | 'most_ineffective'; zone: string; uses?: number; avg?: number | null; frames: number[] };
  const parseZoneRows = useMemo(() => {
    const rows = (data.zoneTopBottom || []).map(r => {
      const player = String(r.Player || '').toUpperCase() as 'P0' | 'P1';
      const type = String(r.ZoneType || '').toLowerCase() as 'most_effective' | 'most_ineffective';
      const zone = String(r.AnchorHittingZone || '').trim();
      const uses = parseInt(String(r.Uses || ''), 10);
      const avg = Number.isFinite(parseFloat(String(r.AvgEffectiveness || ''))) ? parseFloat(String(r.AvgEffectiveness)) : null;
      const all = String(r.AllFrames || '').trim();
      const frames: number[] = all ? all.split('|').map(s => {
        const m = s.match(/F(\d+)/i);
        return m ? parseInt(m[1], 10) : NaN;
      }).filter(n => Number.isFinite(n)) : [];
      return { player, type, zone, uses: Number.isFinite(uses) ? uses : undefined, avg, frames } as ZoneRow;
    }).filter(z => (z.player === 'P0' || z.player === 'P1') && (z.type === 'most_effective' || z.type === 'most_ineffective'));
    const byPlayer = { P0: { eff: null as ZoneRow | null, ineff: null as ZoneRow | null }, P1: { eff: null as ZoneRow | null, ineff: null as ZoneRow | null } };
    for (const r of rows) {
      if (r.player === 'P0') {
        if (r.type === 'most_effective') byPlayer.P0.eff = r;
        if (r.type === 'most_ineffective') byPlayer.P0.ineff = r;
      } else if (r.player === 'P1') {
        if (r.type === 'most_effective') byPlayer.P1.eff = r;
        if (r.type === 'most_ineffective') byPlayer.P1.ineff = r;
      }
    }
    return byPlayer;
  }, [data.zoneTopBottom]);

  // Forced/Unforced errors from effectiveness CSV (final shots), excluding serves
  type ErrMap = Record<string, { stroke: string; frames: number[]; count: number }>;
  type ErrSummary = { forced: ErrMap[keyof ErrMap][], unforced: ErrMap[keyof ErrMap][] };
  const effErrorsByPlayer = useMemo(() => {
    const norm = (s: string) => String(s || '').toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    const rowsAll = (data.effectiveness || []).filter(r => {
      const stroke = String(r.Stroke || '').toLowerCase();
      const isServe = stroke.includes('serve') || String(r.is_serve || '').toLowerCase() === 'true';
      const labelRaw = norm(String(r.effectiveness_label || r.Effectiveness_Label || r.reason || r.Reason || ''));
      const hasUnforced = /\bunforced\b/.test(labelRaw) || /\bue\b/.test(labelRaw);
      const hasForced = /\bforced\b/.test(labelRaw) || /\bfe\b/.test(labelRaw);
      return !isServe && (hasForced || hasUnforced);
    });
    const build = (player: 'P0' | 'P1'): ErrSummary => {
      const rows = rowsAll.filter(r => String(r.Player || '').toUpperCase() === player);
      const forced: ErrMap = {}; const unforced: ErrMap = {};
      for (const r of rows) {
        const labelRaw = norm(String(r.effectiveness_label || r.Effectiveness_Label || r.reason || r.Reason || ''));
        const isUnf = /\bunforced\b/.test(labelRaw) || /\bue\b/.test(labelRaw);
        const isFor = !isUnf && (/(^|\b)forced(\b|$)/.test(labelRaw) || /\bfe\b/.test(labelRaw));
        const stroke = normalizeShot(String(r.Stroke || ''));
        const f = parseInt(String(r.FrameNumber || ''), 10);
        if (!Number.isFinite(f) || !stroke) continue;
        if (isFor) {
          if (!forced[stroke]) forced[stroke] = { stroke, frames: [], count: 0 };
          forced[stroke].frames.push(f); forced[stroke].count += 1;
        } else if (isUnf) {
          if (!unforced[stroke]) unforced[stroke] = { stroke, frames: [], count: 0 };
          unforced[stroke].frames.push(f); unforced[stroke].count += 1;
        }
      }
      const forcedTop = Object.values(forced).sort((a,b)=>b.count-a.count).slice(0,4);
      const unforcedTop = Object.values(unforced).sort((a,b)=>b.count-a.count).slice(0,4);
      return { forced: forcedTop, unforced: unforcedTop };
    };
    return { P0: build('P0'), P1: build('P1') };
  }, [data.effectiveness]);

  const BucketBlock: React.FC<{title: string, buckets: Record<string, RallyItem[]> | undefined}> = ({ title, buckets }) => {
    if (!buckets || Object.keys(buckets).length === 0) return null;
    const order: (keyof typeof shotCategories | 'Other')[] = ['Attacking','Defense','NetBattle','Placement','Reset','Other'];
    return (
      <div style={{ marginTop: 8 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>
        {order.map(k => {
          const arr = buckets[k as string];
          if (!arr || arr.length === 0) return null;
          return (
            <div key={`bucket-${title}-${String(k)}`} style={{ marginBottom: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{String(k)} <span style={{ opacity: 0.7 }}>({arr.length})</span></div>
              <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                {arr.slice(0, 20).map((it, i) => {
                  const sec = toSec(Number(it.start), fps);
                  return (
                    <Chip key={`${title}-${k}-${i}`}
                      label={`[${formatMs(Math.max(0, (sec-2))*1000)}]`}
                      title={`G${it.game}-R${it.rally} ${it.lastShot || ''} (±2s)`}
                      onClick={()=>seek(videoRef, sec)}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div>
      {/* Shot Distribution (UI v2 only) */}
      {(uiVersion === 'v2' && data.shotDistribution && data.shotDistribution.length > 0) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Shot distribution (bars)" onClick={()=>toggle('shotDist')} collapsed={!!collapsed.shotDist} />
          {!collapsed.shotDist && (
            <div style={{ marginTop: 8, opacity: 0.8, fontSize: 12 }}>
              Bar view appears below the video in UI v2.
            </div>
          )}
        </div>
      )}

      {/* Zone effectiveness (overall corners) */}
      {(data.zoneTopBottom && data.zoneTopBottom.length>0) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Zone effectiveness (overall corners)" onClick={()=>toggle('zones')} collapsed={!!collapsed.zones} />
          {!collapsed.zones && (
            <div style={{ marginTop: 8 }}>
              {/* P0 */}
              {(parseZoneRows.P0.eff || parseZoneRows.P0.ineff) && (
                <div style={{ marginBottom: 12 }}>
                  {parseZoneRows.P0.eff && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>P0 — Most effective corner: {parseZoneRows.P0.eff.zone} {Number.isFinite(parseZoneRows.P0.eff.avg||NaN) ? `(avg=${parseZoneRows.P0.eff.avg}%, uses=${parseZoneRows.P0.eff.uses || 'NA'})` : ''}</div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {parseZoneRows.P0.eff.frames.slice(0, 12).map((f, j) => {
                          const sec = toSec(f, fps);
                          return <Chip key={`zone-p0-eff-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  )}
                  {parseZoneRows.P0.ineff && (
                    <div>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>P0 — Most ineffective corner: {parseZoneRows.P0.ineff.zone} {Number.isFinite(parseZoneRows.P0.ineff.avg||NaN) ? `(avg=${parseZoneRows.P0.ineff.avg}%, uses=${parseZoneRows.P0.ineff.uses || 'NA'})` : ''}</div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {parseZoneRows.P0.ineff.frames.slice(0, 12).map((f, j) => {
                          const sec = toSec(f, fps);
                          return <Chip key={`zone-p0-ineff-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
              {/* P1 */}
              {(parseZoneRows.P1.eff || parseZoneRows.P1.ineff) && (
                <div>
                  {parseZoneRows.P1.eff && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>P1 — Most effective corner: {parseZoneRows.P1.eff.zone} {Number.isFinite(parseZoneRows.P1.eff.avg||NaN) ? `(avg=${parseZoneRows.P1.eff.avg}%, uses=${parseZoneRows.P1.eff.uses || 'NA'})` : ''}</div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {parseZoneRows.P1.eff.frames.slice(0, 12).map((f, j) => {
                          const sec = toSec(f, fps);
                          return <Chip key={`zone-p1-eff-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  )}
                  {parseZoneRows.P1.ineff && (
                    <div>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>P1 — Most ineffective corner: {parseZoneRows.P1.ineff.zone} {Number.isFinite(parseZoneRows.P1.ineff.avg||NaN) ? `(avg=${parseZoneRows.P1.ineff.avg}%, uses=${parseZoneRows.P1.ineff.uses || 'NA'})` : ''}</div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {parseZoneRows.P1.ineff.frames.slice(0, 12).map((f, j) => {
                          const sec = toSec(f, fps);
                          return <Chip key={`zone-p1-ineff-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {/* 1) Service → Receive patterns (top 4 each) */}
      {( (data.p0SrPatterns && data.p0SrPatterns.length>0) || (data.p1SrPatterns && data.p1SrPatterns.length>0) ) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Service → Receive patterns" onClick={()=>toggle('sr')} collapsed={!!collapsed.sr} />
          {!collapsed.sr && (
            <div style={{ marginTop: 8 }}>
              {srTopP0.length>0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>P0</div>
                  {srTopP0.map((row, idx) => (
                    <div key={`sr-p0-${idx}`} style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 600 }}>{row.key.serve} → {row.key.recv} <span style={{ opacity:0.7 }}>({row.count})</span></div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem', marginTop: 6 }}>
                        {row.ranges.slice(0, 4).map((r, i) => {
                          const sec = toSec(r[0], fps);
                          return (
                            <Chip key={`sr-p0-chip-${idx}-${i}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`${r[0]}→${r[1]} (±2s) @${fps}fps`} onClick={()=>seek(videoRef, sec)} />
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {srTopP1.length>0 && (
                <div>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>P1</div>
                  {srTopP1.map((row, idx) => (
                    <div key={`sr-p1-${idx}`} style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 600 }}>{row.key.serve} → {row.key.recv} <span style={{ opacity:0.7 }}>({row.count})</span></div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem', marginTop: 6 }}>
                        {row.ranges.slice(0, 4).map((r, i) => {
                          const sec = toSec(r[0], fps);
                          return (
                            <Chip key={`sr-p1-chip-${idx}-${i}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`${r[0]}→${r[1]} (±2s) @${fps}fps`} onClick={()=>seek(videoRef, sec)} />
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 6) Shot effectiveness summary */}
      {(data.effectiveness && data.effectiveness.length>0) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Shot effectiveness (top 6, fallback to 4 if low volume)" onClick={()=>toggle('eff')} collapsed={!!collapsed.eff} />
          {!collapsed.eff && (
            <div style={{ marginTop: 8 }}>
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>P0 — Most effective (green)</div>
                {effByPlayer.P0.topEff.map((e, idx) => (
                  <div key={`eff-p0-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`eff-p0-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
                <div style={{ fontWeight: 700, margin: '8px 0 6px 0' }}>P0 — Most ineffective (red)</div>
                {effByPlayer.P0.topIneff.map((e, idx) => (
                  <div key={`ineff-p0-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`ineff-p0-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>P1 — Most effective (green)</div>
                {effByPlayer.P1.topEff.map((e, idx) => (
                  <div key={`eff-p1-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`eff-p1-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
                <div style={{ fontWeight: 700, margin: '8px 0 6px 0' }}>P1 — Most ineffective (red)</div>
                {effByPlayer.P1.topIneff.map((e, idx) => (
                  <div key={`ineff-p1-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`ineff-p1-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
              </div>

              {/* Forced/Unforced errors from effectiveness CSV (final shots) */}
              <div style={{ marginTop: 16 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>P0 — Forced errors (final shots)</div>
                {effErrorsByPlayer.P0.forced.map((e, idx) => (
                  <div key={`fe-p0-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`fe-p0-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
                <div style={{ fontWeight: 700, margin: '8px 0 6px 0' }}>P0 — Unforced errors (final shots)</div>
                {effErrorsByPlayer.P0.unforced.map((e, idx) => (
                  <div key={`ue-p0-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`ue-p0-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>P1 — Forced errors (final shots)</div>
                {effErrorsByPlayer.P1.forced.map((e, idx) => (
                  <div key={`fe-p1-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`fe-p1-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
                <div style={{ fontWeight: 700, margin: '8px 0 6px 0' }}>P1 — Unforced errors (final shots)</div>
                {effErrorsByPlayer.P1.unforced.map((e, idx) => (
                  <div key={`ue-p1-${idx}`} style={{ marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>{e.stroke} <span style={{ opacity: 0.7 }}>({e.count})</span></div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {e.frames.slice(0, 8).map((f, j) => {
                        const sec = toSec(f, fps);
                        return <Chip key={`ue-p1-chip-${idx}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Winners/Errors/Rallies/3-shot sections remain unchanged below */}
      {/* 2) Winners */}
      {(winnersP0.length>0 || winnersP1.length>0) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Winners (top 4 by stroke)" onClick={()=>toggle('winners')} collapsed={!!collapsed.winners} />
          {!collapsed.winners && (
            <div style={{ marginTop: 8 }}>
              {winnersP0.length>0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>P0</div>
                  {winnersP0.map((w,i)=>(
                    <div key={`w-p0-${i}`} style={{ marginBottom: 6 }}>
                      <div style={{ fontWeight: 600 }}>{w.stroke} <span style={{ opacity:0.7 }}>({w.count})</span></div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {w.frames.slice(0, 8).map((f, j)=>{
                          const sec = toSec(f, fps);
                          return <Chip key={`w-p0-${i}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {winnersP1.length>0 && (
                <div>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>P1</div>
                  {winnersP1.map((w,i)=>(
                    <div key={`w-p1-${i}`} style={{ marginBottom: 6 }}>
                      <div style={{ fontWeight: 600 }}>{w.stroke} <span style={{ opacity:0.7 }}>({w.count})</span></div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {w.frames.slice(0, 8).map((f, j)=>{
                          const sec = toSec(f, fps);
                          return <Chip key={`w-p1-${i}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 3) Errors */}
      {(errorsP0.length>0 || errorsP1.length>0) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Errors (top 4 by stroke)" onClick={()=>toggle('errors')} collapsed={!!collapsed.errors} />
          {!collapsed.errors && (
            <div style={{ marginTop: 8 }}>
              {errorsP0.length>0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>P0</div>
                  {errorsP0.map((w,i)=>(
                    <div key={`e-p0-${i}`} style={{ marginBottom: 6 }}>
                      <div style={{ fontWeight: 600 }}>{w.stroke} <span style={{ opacity:0.7 }}>({w.count})</span></div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {w.frames.slice(0, 8).map((f, j)=>{
                          const sec = toSec(f, fps);
                          return <Chip key={`e-p0-${i}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {errorsP1.length>0 && (
                <div>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>P1</div>
                  {errorsP1.map((w,i)=>(
                    <div key={`e-p1-${i}`} style={{ marginBottom: 6 }}>
                      <div style={{ fontWeight: 600 }}>{w.stroke} <span style={{ opacity: 0.7 }}>({w.count})</span></div>
                      <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                        {w.frames.slice(0, 8).map((f, j)=>{
                          const sec = toSec(f, fps);
                          return <Chip key={`e-p1-${i}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`F${f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 4) Winning/Losing rallies */}
      {(data.p0WinningRallies || data.p1WinningRallies) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Winning rallies" onClick={()=>toggle('winRallies')} collapsed={!!collapsed.winRallies} />
          {!collapsed.winRallies && (
            <div>
              <BucketBlock title="P0" buckets={winBucketsP0} />
              <BucketBlock title="P1" buckets={winBucketsP1} />
            </div>
          )}
        </div>
      )}
      {(data.p0LosingRallies || data.p1LosingRallies) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="Losing rallies" onClick={()=>toggle('loseRallies')} collapsed={!!collapsed.loseRallies} />
          {!collapsed.loseRallies && (
            <div>
              <BucketBlock title="P0" buckets={loseBucketsP0} />
              <BucketBlock title="P1" buckets={loseBucketsP1} />
            </div>
          )}
        </div>
      )}

      {/* 5) 3-shot sequences (top 10) */}
      {(threeShotTop.length>0) && (
        <div style={{ marginBottom: 12 }}>
          <SectionHeader title="3-shot sequences (top 10)" onClick={()=>toggle('threeShot')} collapsed={!!collapsed.threeShot} />
          {!collapsed.threeShot && (
            <div style={{ marginTop: 8 }}>
              {threeShotTop.map((r, i) => {
                const seq = String(r.Sequence || r.sequence || r.FrameNumbers || '').trim() || String(r.SequenceText || '');
                const first = parseInt(String(r.FirstFrame || ''), 10);
                const target = parseInt(String(r.TargetFrame || ''), 10);
                const chips: Array<{ f?: number; label: string } > = [];
                if (Number.isFinite(first)) chips.push({ f:first, label:'start' });
                if (Number.isFinite(target)) chips.push({ f:target, label:'target' });
                return (
                  <div key={`seq-${i}`} style={{ marginBottom: 8 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{seq || '(sequence)'}</div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:'0.5rem' }}>
                      {chips.map((c, j) => {
                        const sec = toSec(Number(c.f), fps);
                        return (
                          <Chip key={`seq-${i}-${j}`} label={`[${formatMs(Math.max(0,(sec-2))*1000)}]`} title={`${c.label} F${c.f} (±2s)`} onClick={()=>seek(videoRef, sec)} />
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default StatsPanel;
