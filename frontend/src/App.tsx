import React, { useEffect, useMemo, useRef, useState } from 'react';
import { KeyTakeaways, type Observation } from './components/KeyTakeaways';
import { KeyTakeawaysV2, type V2Section } from './components/KeyTakeawaysV2';
import StructuredAnalysis, { type SASection } from './components/StructuredAnalysis';
import RallyDynamics, { type DynamicsPayload } from './components/RallyDynamics';
import TempoAnalysis, { type TempoEvent, type TempoThresholds } from './components/TempoAnalysis';
import IneffectiveSlowEvents, { type IneffSlowEvent } from './components/IneffectiveSlowEvents';
import ZoneBuckets, { type ZoneBucketRow } from './components/ZoneBuckets';
import ComboExplorer, { type ComboSummaryBandRow, type ComboInstanceBandRow } from './components/ComboExplorer';
import RallyPace, { type RallyMetricsRow } from './components/RallyPace';
import ChatPanelV2 from './components/ChatPanelV2';
import RallyTempoVisualization, { type RallyTempoPayload } from './components/RallyTempoVisualization';
import TempoEffectivenessCorrelation from './components/TempoEffectivenessCorrelation';
import { formatMs } from './utils/timecode';
import './App.css';
import Papa from 'papaparse';
import StatsPanel, { type StatsData } from './components/StatsPanel';
import StatsPanelV2, { VideoTimelineMarker, type TimelineInstance } from './components/StatsPanelV2.tsx';

// Generic JSON type
type AnyJson = Record<string, any>;

// Technical issue type
type TechIssue = {
  issue_text: string;
  issue_feedback: string;
  recommended_feedback: string;
  timestampsSec: number[];
};

function normalizeSummaryJson(summary: AnyJson): Observation[] {
  const out: Observation[] = [];
  const map: Array<{ key: string; sect: Observation['section'] }> = [
    { key: 'mandatory_observations', sect: 'mandatory' },
    { key: 'things_that_worked', sect: 'worked' },
    { key: "things_that_didnt_work", sect: 'didnt_work' },
    { key: 'things_that_could_be_better', sect: 'could_be_better' },
  ];
  for (const { key, sect } of map) {
    const arr = Array.isArray(summary?.[key]) ? summary[key] : [];
    arr.forEach((item: AnyJson, idx: number) => {
      const text = String(item?.statement || '').trim();
      const anchors = Array.isArray(item?.anchors) ? item.anchors : [];
      const frameAnchors: string[] = anchors
        .map((a: AnyJson) => {
          const t = String(a?.type || '');
          const v = String(a?.value || '').trim();
          if (t === 'frame_range' && v) return v; // e.g., 12953-12984
          if (t === 'rally_id' && v) return v;    // e.g., G1-R5-F14680
          return '';
        })
        .filter(Boolean);
      if (text) out.push({ id: `${sect}-${idx}`, section: sect, text, frameAnchors });
    });
  }
  return out;
}

function parseTimestampToSec(t: string): number | null {
    const parts = String(t || '').trim().split(':').map(x => parseInt(x, 10));
    if (parts.some(n => !Number.isFinite(n))) return null;
  if (parts.length === 2) {
    const [m, s] = parts; return m * 60 + s;
  }
  if (parts.length === 3) {
    const [h, m, s] = parts; return h * 3600 + m * 60 + s;
    }
    return null;
}

function App() {
  // Mode
  const [mode, setMode] = useState<'match' | 'technical'>('match');

  // Match state
  const videoRef = useRef<HTMLVideoElement>(null as unknown as HTMLVideoElement);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoLoaded, setVideoLoaded] = useState<boolean>(false);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [v2Sections, setV2Sections] = useState<V2Section[]>([]);
  const [saSections, setSaSections] = useState<SASection[]>([]);
  const [summaryLoaded, setSummaryLoaded] = useState<boolean>(false); // true if either v1 or v2 is loaded

  // Technical state
  const techVideoRef = useRef<HTMLVideoElement | null>(null);
  const [techVideoUrl, setTechVideoUrl] = useState<string>('');
  const [techVideoLoaded, setTechVideoLoaded] = useState<boolean>(false);
  const [techIssues, setTechIssues] = useState<TechIssue[]>([]);
  const [selectedTechIssue, setSelectedTechIssue] = useState<string | null>(null);

  // Right panel collapse states (handled per-section/issue; no global collapse state)

  // Shared
  const [fps, setFps] = useState<number>(30);
  const [inputsExpanded, setInputsExpanded] = useState<boolean>(true);
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [statusType, setStatusType] = useState<'ok' | 'err' | ''>('');
  const [rightTab, setRightTab] = useState<'summary'|'stats'|'dynamics'|'tempo'|'chat'>('summary');
  const [statsData, setStatsData] = useState<StatsData>({});
  const [v3Text, setV3Text] = useState<string>('');
  const [uiVersion, setUiVersion] = useState<'v1'|'v2'>('v1');
  const [dynData, setDynData] = useState<DynamicsPayload | null>(null);
  const [tempoEvents, setTempoEvents] = useState<TempoEvent[]>([]);
  const [tempoThresholds, setTempoThresholds] = useState<TempoThresholds | null>(null);
  const [ineffSlowEvents, setIneffSlowEvents] = useState<IneffSlowEvent[]>([]);
  const [zoneBuckets, setZoneBuckets] = useState<ZoneBucketRow[]>([]);
  const [comboSummaryBand, setComboSummaryBand] = useState<ComboSummaryBandRow[]>([]);
  const [comboInstancesBand, setComboInstancesBand] = useState<ComboInstanceBandRow[]>([]);
  const [rallyMetrics, setRallyMetrics] = useState<RallyMetricsRow[]>([]);
  const [rallyTempoData, setRallyTempoData] = useState<RallyTempoPayload | null>(null);
  const [tempoView, setTempoView] = useState<'overview'|'combos'|'zones'|'rally'|'ineff'|'rally_tempo'|'tempo_effect'>('overview');
  const [activeStatsSection, setActiveStatsSection] = useState<string | null>(null);
  const [timelineInstances, setTimelineInstances] = useState<TimelineInstance[]>([]);
  const [timelineSectionName, setTimelineSectionName] = useState<string>('');

  const anyStatsLoaded = useMemo(() => {
    const d = statsData;
    return !!(
      (d.p1SrPatterns && d.p1SrPatterns.length) ||
      (d.p0Winners && d.p0Winners.length) ||
      (d.p1Winners && d.p1Winners.length) ||
      (d.p0Errors && d.p0Errors.length) ||
      (d.p1Errors && d.p1Errors.length) ||
      (d.p0WinningRallies && d.p0WinningRallies.length) ||
      (d.p1WinningRallies && d.p1WinningRallies.length) ||
      (d.p0LosingRallies && d.p0LosingRallies.length) ||
      (d.p1LosingRallies && d.p1LosingRallies.length) ||
      (d.threeShot && d.threeShot.length) ||
      (d.shotDistribution && d.shotDistribution.length)
    );
  }, [statsData]);
  const isMatchCollapsed = useMemo(() => videoLoaded && (summaryLoaded || anyStatsLoaded), [videoLoaded, summaryLoaded, anyStatsLoaded]);
  const isTechCollapsed = useMemo(() => techVideoLoaded && techIssues.length > 0, [techVideoLoaded, techIssues.length]);

  useEffect(() => {
    if (mode === 'match' && isMatchCollapsed) setInputsExpanded(false);
    if (mode === 'technical' && isTechCollapsed) setInputsExpanded(false);
  }, [mode, isMatchCollapsed, isTechCollapsed]);

  useEffect(() => { /* no auto-loads */ }, []);

  // Load CSV utility
  // Deprecated helper (replaced by folder loader parsing)

  // CSV uploads handler: detect types and populate statsData
  const detectCsvType = (rows: Record<string,string>[], filename: string): keyof StatsData | null => {
    const lower = filename.toLowerCase();
    const headers = Object.keys(rows[0] || {}).map(h => h.toLowerCase());
    const has = (k: string) => headers.includes(k.toLowerCase());
    // Heuristics based on columns
    if (has('player') && has('hittingzone') && has('shottype') && has('direction') && has('landingposition') && has('count')) {
      return 'shotDistribution';
    }
    if (has('serve_shot') && has('receive_shot') && has('count')) {
      if (lower.includes('p0')) return 'p0SrPatterns';
      if (lower.includes('p1')) return 'p1SrPatterns';
      // fallback: assume P1 if unspecified
      return 'p1SrPatterns';
    }
    if (has('sequence') && (has('firstframe') || has('targetframe'))) return 'threeShot';
    if ((has('stroke') || has('framnumber') || has('framenumber')) && (has('color') || lower.includes('detailed_effectiveness'))) return 'effectiveness';
    if ((has('zonetype') || lower.includes('zone')) && (has('anchorhittingzone') || has('hittingzone')) && (has('allframes') || has('uses') || has('avgeffectiveness') || lower.includes('zone_effectiveness'))) return 'zoneTopBottom';
    if (has('startframe') && has('endframe') && (has('lastshot') || has('lastshotframe'))) {
      // Cannot know win/lose and side reliably without filename; try to infer from columns
      if (lower.includes('winning') && lower.includes('p0')) return 'p0WinningRallies';
      if (lower.includes('winning') && lower.includes('p1')) return 'p1WinningRallies';
      if (lower.includes('losing') && lower.includes('p0')) return 'p0LosingRallies';
      if (lower.includes('losing') && lower.includes('p1')) return 'p1LosingRallies';
      return null;
    }
    if (has('framenumber') && has('stroke')) {
      if (lower.includes('winner') && lower.includes('p0')) return 'p0Winners';
      if (lower.includes('winner') && lower.includes('p1')) return 'p1Winners';
    }
    if (has('framenumber') && has('shotcategory')) {
      if (lower.includes('error') && lower.includes('p0')) return 'p0Errors';
      if (lower.includes('error') && lower.includes('p1')) return 'p1Errors';
    }
    return null;
  };

  // Deprecated per-file CSV loader (replaced by folder loader)

  const showStatus = (msg: string, type: 'ok' | 'err') => {
    setStatusMsg(msg); setStatusType(type);
    window.clearTimeout((showStatus as any)._t);
    (showStatus as any)._t = window.setTimeout(() => { setStatusMsg(''); setStatusType(''); }, 2200);
  };

  // Match inputs
  // Deprecated per-file loaders (replaced by folder loader)

  const normalizeSummaryV2 = (raw: AnyJson): V2Section[] => {
    const v = Number(raw?.version);
    // Case 1: Single V2 object with sections
    if (v === 2 && Array.isArray(raw?.sections)) {
      const sections = (raw.sections as AnyJson[])
        .map((s): V2Section | null => {
          const title = String(s?.title || '').trim();
          const items = Array.isArray(s?.items) ? s.items : [];
          if (!title) return null;
          return {
            title,
            items: items.map((it: AnyJson) => ({
              heading: String(it?.heading || '').trim(),
              text: String(it?.text || '').trim(),
              anchors: Array.isArray(it?.anchors) ? it.anchors : [],
            })).filter((it: AnyJson) => it.heading || it.text),
          };
        })
        .filter((x): x is V2Section => !!x);
      return sections;
    }
    // Case 2: Multi-summary file { version:2, summaries:[{sections:[]}, ...] }
    if (v === 2 && Array.isArray(raw?.summaries)) {
      const all: V2Section[] = [];
      for (const s of raw.summaries as AnyJson[]) {
        const secs = normalizeSummaryV2({ version: 2, sections: s?.sections });
        all.push(...secs);
      }
      return all;
    }
    // Fallback: if payload is just {sections: []} without version
    if (Array.isArray(raw?.sections)) return normalizeSummaryV2({ version: 2, sections: raw.sections });
    return [];
  };

  // Deprecated per-file loaders (replaced by folder loader)

  // Rally dynamics (swing-filtered timeseries JSON)
  // Deprecated per-file loaders (replaced by folder loader)

  // Tempo: events CSV
  // Deprecated per-file loaders (replaced by folder loader)

  // Tempo: thresholds JSON
  // Deprecated per-file loaders (replaced by folder loader)

  // Folder session loader
  const onPickFolder: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    try {
      // 1) Video
      const videoFile = files.find(f => /\.(mp4|mov|mkv)$/i.test(f.name));
      if (videoFile) {
        const url = URL.createObjectURL(videoFile);
        setVideoUrl(url); setVideoLoaded(true);
      }
      // Helpers
      const getText = (f: File) => f.text();
      const parseCsv = async (f: File) => new Promise<any[]>((resolve) => {
        f.text().then(text => {
          Papa.parse(text, { header: true, skipEmptyLines: true, complete: (r: any) => resolve((r.data as any[]) || []) });
        });
      });
      const parseJson = async (f: File) => JSON.parse(await getText(f));
      // 2) Tempo files
      const find = (re: RegExp) => files.find(f => re.test(f.name.toLowerCase()));
      const fev = find(/_tempo_events\.csv$/i);
      if (fev) {
        const rows = await parseCsv(fev);
        const mapped: TempoEvent[] = rows.map((row: any) => ({
          frame: Number(row.FrameNumber || row.frame || 0),
          time_sec: Number(row.time_sec || 0),
          stroke_no: Number(row.StrokeNumber || row.stroke_no || 0),
          player: String(row.Player || row.player || ''),
          stroke: String(row.Stroke || row.stroke || ''),
          effectiveness: row.effectiveness != null && row.effectiveness !== '' ? Number(row.effectiveness) : null,
        } as any));
        setTempoEvents(mapped);
      }
      const fth = find(/_tempo_thresholds\.json$/i);
      if (fth) {
        const raw = await parseJson(fth);
        setTempoThresholds(raw as TempoThresholds);
      }
      const fine = find(/_tempo_ineffective_slow_events\.csv$/i);
      if (fine) {
        const rows = await parseCsv(fine);
        const mapped: IneffSlowEvent[] = rows.map((row: any) => ({
          rally_id: String(row.rally_id || ''),
          Player: String(row.Player || ''),
          time_sec: Number(row.time_sec),
          Stroke: String(row.Stroke || ''),
          opp_prev_stroke: String(row.opp_prev_stroke || ''),
          response_time_sec: Number(row.response_time_sec),
          classification: String(row.classification || ''),
          effectiveness: row.effectiveness != null && row.effectiveness !== '' ? Number(row.effectiveness) : null,
          effectiveness_color: row.effectiveness_color ? String(row.effectiveness_color).toLowerCase() : null,
          incoming_eff: row.incoming_eff != null && row.incoming_eff !== '' ? Number(row.incoming_eff) : null,
          incoming_eff_bin: row.incoming_eff_bin ? String(row.incoming_eff_bin) : null,
          forced_error: String(row.forced_error || '').toLowerCase() === 'true',
          unforced_error: String(row.unforced_error || '').toLowerCase() === 'true',
          threshold_source: String(row.threshold_source || ''),
          combo_key: String(row.combo_key || ''),
        }));
        setIneffSlowEvents(mapped);
      }
      const fzone = find(/_tempo_zone_buckets\.csv$/i);
      if (fzone) {
        const rows = await parseCsv(fzone);
        const parsed: ZoneBucketRow[] = rows.map((r: any) => ({
          bucket: String(r.bucket || ''),
          player: String(r.player || ''),
          role: String(r.role || ''),
          count: Number(r.count || 0),
          min_rt: Number(r.min_rt || 0),
          p10: r.p10 != null && r.p10 !== '' ? Number(r.p10) : null,
          median: r.median != null && r.median !== '' ? Number(r.median) : null,
          p90: r.p90 != null && r.p90 !== '' ? Number(r.p90) : null,
          max_rt: Number(r.max_rt || 0),
          fast_rate: Number(r.fast_rate || 0),
          slow_rate: Number(r.slow_rate || 0),
          times_sec: (() => {
            const t = r.times_sec;
            if (typeof t === 'string' && t.trim().startsWith('[')) { try { return (JSON.parse(t) as number[]).map(Number); } catch { return []; } }
            if (typeof t === 'string') return t.split(/[;,]\s*/).map((x: string)=>Number(x)).filter((x:number)=>Number.isFinite(x));
            return [];
          })(),
        }));
        setZoneBuckets(parsed);
      }
      const fcs = find(/_tempo_combo_summary_band\.csv$/i);
      if (fcs) {
        const rows = await parseCsv(fcs);
        const parsed: ComboSummaryBandRow[] = rows.map((r: any) => ({
          combo_key_band: String(r.combo_key_band || ''),
          player: String(r.player || ''),
          opp_prev_stroke: String(r.opp_prev_stroke || ''),
          opp_band: String(r.opp_band || ''),
          resp_stroke: String(r.resp_stroke || ''),
          resp_band: String(r.resp_band || ''),
          count: Number(r.count || 0),
          min_rt: Number(r.min_rt || 0),
          p10: r.p10 != null && r.p10 !== '' ? Number(r.p10) : null,
          median: r.median != null && r.median !== '' ? Number(r.median) : null,
          p90: r.p90 != null && r.p90 !== '' ? Number(r.p90) : null,
          max_rt: Number(r.max_rt || 0),
        }));
        setComboSummaryBand(parsed);
      }
      const fci = find(/_tempo_combo_instances_band\.csv$/i);
      if (fci) {
        const rows = await parseCsv(fci);
        const parsed: ComboInstanceBandRow[] = rows.map((r:any)=>({
          combo_key_band: String(r.combo_key_band || ''),
          rally_id: String(r.rally_id || ''),
          player: String(r.player || ''),
          time_sec: Number(r.time_sec || 0),
          opp_prev_stroke: String(r.opp_prev_stroke || ''),
          opp_band: String(r.opp_band || ''),
          resp_stroke: String(r.resp_stroke || ''),
          resp_band: String(r.resp_band || ''),
          response_time_sec: Number(r.response_time_sec || 0),
          position_band: String(r.position_band || 'typical'),
        }));
        setComboInstancesBand(parsed);
      }
      const frm = find(/_tempo_rally_metrics\.csv$/i);
      if (frm) {
        const rows = await parseCsv(frm);
        const parsed: RallyMetricsRow[] = rows.map((r:any)=>({
          game: Number(r.game || 0),
          rally: Number(r.rally || 0),
          rally_id: String(r.rally_id || ''),
          player: String(r.player || ''),
          shots: Number(r.shots || 0),
          median_rt: r.median_rt != null && r.median_rt !== '' ? Number(r.median_rt) : null,
          stddev_rt: r.stddev_rt != null && r.stddev_rt !== '' ? Number(r.stddev_rt) : null,
          iqr_rt: r.iqr_rt != null && r.iqr_rt !== '' ? Number(r.iqr_rt) : null,
          range_rt: r.range_rt != null && r.range_rt !== '' ? Number(r.range_rt) : null,
          transitions: Number(r.transitions || 0),
          longest_run: Number(r.longest_run || 0),
          early_late_delta: r.early_late_delta != null && r.early_late_delta !== '' ? Number(r.early_late_delta) : null,
          slope_rt: r.slope_rt != null && r.slope_rt !== '' ? Number(r.slope_rt) : null,
          delta_vs_baseline: r.delta_vs_baseline != null && r.delta_vs_baseline !== '' ? Number(r.delta_vs_baseline) : null,
        }));
        setRallyMetrics(parsed);
      }
      // Rally tempo visualization: check for pre-generated JSON first, then process CSV
      const frtv = find(/_rally_tempo_viz\.json$/i);
      if (frtv) {
        try {
          const raw = await parseJson(frtv);
          if (raw && Array.isArray(raw.rallies)) {
            setRallyTempoData(raw as RallyTempoPayload);
          }
        } catch { /* ignore */ }
      }
      // Process tempo_analysis_new.csv to generate rally tempo data
      const ftan = find(/tempo_analysis_new\.csv$/i);
      if (ftan && !frtv) {
        try {
          const rows = await parseCsv(ftan);
          // Process CSV to generate rally tempo visualization data
          const ralliesMap: Record<string, any> = {};
          
          for (const row of rows) {
            const isServe = String(row.is_serve || '').toLowerCase() === 'true';
            if (isServe) continue; // Skip serves
            
            const rallyId = String(row.rally_id || '').trim();
            if (!rallyId) continue;
            
            const player = String(row.Player || '').trim();
            if (player !== 'P0' && player !== 'P1') continue;
            
            if (!ralliesMap[rallyId]) {
              const gameNum = Number(row.GameNumber || 0);
              const rallyNum = Number(row.RallyNumber || 0);
              const rallyWinner = String(row.rally_winner || '').trim();
              ralliesMap[rallyId] = {
                rally_id: rallyId,
                game_number: gameNum,
                rally_number: rallyNum,
                rally_winner: rallyWinner,
                rally_start_time: 0,
                p0_shots: [],
                p1_shots: [],
                total_shots: 0,
              };
            }
            
            const timeSec = row.time_sec != null && row.time_sec !== '' ? Number(row.time_sec) : null;
            const responseTime = row.response_time_sec != null && row.response_time_sec !== '' ? Number(row.response_time_sec) : null;
            const strokeNum = row.StrokeNumber != null && row.StrokeNumber !== '' ? Number(row.StrokeNumber) : 0;
            const frameNum = row.FrameNumber != null && row.FrameNumber !== '' ? Number(row.FrameNumber) : 0;
            
            if (timeSec == null || responseTime == null || responseTime <= 0) continue;
            
            const shot = {
              stroke_number: strokeNum,
              time_sec: timeSec,
              time_in_rally: 0, // Will be calculated later
              frame_number: frameNum,
              response_time_sec: responseTime,
              stroke: String(row.Stroke || '').trim(),
              effectiveness: row.effectiveness != null && row.effectiveness !== '' ? Number(row.effectiveness) : null,
              tempo_control: String(row.tempo_control || 'neutral').trim(),
              control_type: String(row.control_type || 'balanced').trim(),
              classification: String(row.classification || 'normal').trim(),
            };
            
            if (player === 'P0') {
              ralliesMap[rallyId].p0_shots.push(shot);
            } else {
              ralliesMap[rallyId].p1_shots.push(shot);
            }
          }
          
          // Process rallies: calculate rally start times and normalize
          const processedRallies = Object.values(ralliesMap).map((rally: any) => {
            const allShots = [...rally.p0_shots, ...rally.p1_shots];
            if (allShots.length === 0) return null;
            
            // Sort by stroke number
            allShots.sort((a: any, b: any) => a.stroke_number - b.stroke_number);
            rally.p0_shots.sort((a: any, b: any) => a.stroke_number - b.stroke_number);
            rally.p1_shots.sort((a: any, b: any) => a.stroke_number - b.stroke_number);
            
            // Find rally start time
            const allTimes = allShots.map((s: any) => s.time_sec).filter((t: number) => t > 0);
            rally.rally_start_time = allTimes.length > 0 ? Math.min(...allTimes) : 0;
            
            // Normalize times
            for (const shot of allShots) {
              shot.time_in_rally = rally.rally_start_time > 0 ? shot.time_sec - rally.rally_start_time : shot.time_sec;
            }
            
            rally.total_shots = allShots.length;
            return rally;
          }).filter((r: any) => r != null && r.total_shots > 0);
          
          // Sort by game and rally number
          processedRallies.sort((a: any, b: any) => {
            if (a.game_number !== b.game_number) return a.game_number - b.game_number;
            return a.rally_number - b.rally_number;
          });
          
          setRallyTempoData({
            rallies: processedRallies,
            total_rallies: processedRallies.length,
            metadata: { source_file: ftan.name, generated_in_browser: true },
          });
        } catch (err) {
          console.error('Failed to process tempo_analysis_new.csv:', err);
        }
      }
      // 3) Stats CSVs (auto-detect via existing detectCsvType)
      const next: StatsData = { ...statsData };
      for (const f of files) {
        const lower = f.name.toLowerCase();
        if (/_tempo_/.test(lower)) continue; // handled above
        if (/\.(csv)$/i.test(lower)) {
          const rows = await parseCsv(f);
          if (!rows || rows.length === 0) continue;
          const key = detectCsvType(rows as any, f.name) as keyof StatsData | null;
          if (key) (next as any)[key] = rows;
        }
      }
      setStatsData(next);
      // 4) Summaries and rally dynamics JSON
      for (const f of files) {
        const lower = f.name.toLowerCase();
        if (!/\.(json|txt|md)$/i.test(lower)) continue;
        try {
          if (lower.endsWith('rally_timeseries.json')) {
            const raw = await parseJson(f);
            if (raw && raw.rallies) setDynData(raw as DynamicsPayload);
            continue;
          }
          if (/\.(txt|md)$/i.test(lower)) {
            const txt = await getText(f);
            if (txt && txt.length > 10) { setV3Text(txt); setSummaryLoaded(true); }
            continue;
          }
          const raw = await parseJson(f);
          // Try V2
          const secs = normalizeSummaryV2(raw);
          if (secs && secs.length > 0) { setV2Sections(secs); setSummaryLoaded(true); continue; }
          // Try Structured
          if (Array.isArray(raw?.sections)) {
            const sections = (raw.sections as any[]).map((s): SASection => ({
              section_id: String(s?.section_id || '').trim(),
              section_name: String(s?.section_name || '').trim(),
              summary: String(s?.summary || '').trim(),
              jump_links: Array.isArray(s?.jump_links) ? s.jump_links : [],
            })).filter(s => s.section_id && s.section_name);
            if (sections.length) { setSaSections(sections); setSummaryLoaded(true); continue; }
          }
          // Try V1
          const obs = normalizeSummaryJson(raw);
          if (obs && obs.length > 0) { setObservations(obs); setSummaryLoaded(true); continue; }
        } catch { /* ignore */ }
      }
      showStatus('Session folder loaded', 'ok');
    } catch {
      showStatus('Failed to load session folder', 'err');
    } finally {
      e.currentTarget.value = '';
    }
  };

  // Tempo: Ineffective + Slow Events CSV
  // Deprecated per-file loaders (replaced by folder loader)

  // Structured Analysis JSON (sections with summaries + jump links)
  // Deprecated per-file loaders (replaced by folder loader)

  // Summary V3: plain text/markdown
  // Deprecated per-file loaders (replaced by folder loader)

  // Technical inputs
  const onPickTechVideo: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    setTechVideoUrl(url); setTechVideoLoaded(true); showStatus('Technical video loaded', 'ok');
    e.currentTarget.value = '';
  };
  const onPickTechJson: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const raw = JSON.parse(String(reader.result || '{}')) as AnyJson;
        const items = Array.isArray(raw?.data) ? (raw.data as AnyJson[]) : [];
        const parsed: TechIssue[] = items.map((it: AnyJson) => {
          const tsList: string[] = Array.isArray(it?.issue_keyframe)
            ? (it.issue_keyframe as AnyJson[]).map(k => String(k?.timestamp || '').trim()).filter(Boolean)
            : [];
          const timestampsSec = tsList
            .map(parseTimestampToSec)
            .filter((n): n is number => Number.isFinite(n))
            .sort((a, b) => a - b);
          return {
            issue_text: String(it?.issue_text || '').trim(),
            issue_feedback: String(it?.issue_feedback || '').trim(),
            recommended_feedback: String(it?.recommended_feedback || '').trim(),
            timestampsSec,
          };
        }).filter(x => x.issue_text);
        setTechIssues(parsed);
        setSelectedTechIssue(parsed[0]?.issue_text || null);
        showStatus('Technical JSON loaded', 'ok');
      } catch { showStatus('Failed to parse technical JSON', 'err'); }
    };
    reader.onerror = () => showStatus('Failed to read technical JSON', 'err');
    reader.readAsText(f);
    e.currentTarget.value = '';
  };

  // Inputs UI
  const CollapsedInputsStrip: React.FC = () => {
    const isMatch = mode === 'match';
  return (
      <div onClick={() => setInputsExpanded(true)}
        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 10px', border: '1px solid #2c2c34', borderRadius: 8, background: '#0f0f15', fontSize: 12, cursor: 'pointer' }}>
        {isMatch ? (
          <>
            <span title={videoLoaded ? 'Video loaded' : 'Video not loaded'} style={{ width: 8, height: 8, borderRadius: 999, background: videoLoaded ? '#22c55e' : '#475569', display: 'inline-block' }} />
            <span title={summaryLoaded ? 'Summary loaded' : 'Summary not loaded'} style={{ width: 8, height: 8, borderRadius: 999, background: summaryLoaded ? '#22c55e' : '#475569', display: 'inline-block' }} />
                  </>
                ) : (
                  <>
            <span title={techVideoLoaded ? 'Technical video loaded' : 'Technical video not loaded'} style={{ width: 8, height: 8, borderRadius: 999, background: techVideoLoaded ? '#22c55e' : '#475569', display: 'inline-block' }} />
            <span title={techIssues.length > 0 ? 'Technical JSON loaded' : 'Technical JSON not loaded'} style={{ width: 8, height: 8, borderRadius: 999, background: techIssues.length > 0 ? '#22c55e' : '#475569', display: 'inline-block' }} />
                  </>
                )}
        <span style={{ opacity: 0.85 }}>FPS: {fps}</span>
        <span style={{ marginLeft: 'auto' }}>▼</span>
        </div>
    );
  };

  const InputsPanel = () => {
    const isMatch = mode === 'match';
    const collapsed = isMatch ? isMatchCollapsed : isTechCollapsed;
    return (
      <div className="inputs-panel-wrapper">
        <div className="inputs-header" onClick={() => setInputsExpanded(v => !v)}>
          <h2 style={{ margin: 0, fontSize: '1.1em' }}>Inputs</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {collapsed && !inputsExpanded && (
              <>
                <span title={isMatch ? (videoLoaded ? 'Video loaded' : 'Video not loaded') : (techVideoLoaded ? 'Tech video loaded' : 'Tech video not loaded')}
                  style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', backgroundColor: (isMatch ? videoLoaded : techVideoLoaded) ? 'green' : 'gray' }}
                />
                <span title={isMatch ? (summaryLoaded ? 'Summary loaded' : 'Summary not loaded') : (techIssues.length > 0 ? 'Tech JSON loaded' : 'Tech JSON not loaded')}
                  style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', backgroundColor: (isMatch ? summaryLoaded : techIssues.length > 0) ? 'green' : 'gray' }}
                />
                <span>FPS: {fps}</span>
              </>
            )}
            <span>{inputsExpanded ? '▲' : '▼'}</span>
                  </div>
              </div>
        {inputsExpanded && (
          <div className="inputs-content">
            {isMatch ? (
              <>
                <div className="input-group">
                  <label>Session Folder:</label>
                  <label style={{ border:'1px solid #2c2c34', borderRadius:8, padding:'6px 10px', cursor:'pointer', color:'#e5e7eb', display:'inline-block', marginLeft: 8 }}>
                    Load Session Folder
                    <input type="file" style={{ display:'none' }} multiple onChange={onPickFolder} {...({ webkitdirectory: '' } as any)} />
                  </label>
                </div>
                <div style={{ marginTop: 6, fontSize: 12, opacity: 0.8 }}>
                  Video: {videoUrl ? 'loaded' : '—'} · Tempo: ev={tempoEvents.length} ine={ineffSlowEvents.length} zone={zoneBuckets.length} combos={comboSummaryBand.length}/{comboInstancesBand.length} rally={rallyMetrics.length}
                </div>
              </>
            ) : (
              <>
                <div className="input-group">
                  <label htmlFor="tech-video-upload">Technical Video:</label>
                  <input id="tech-video-upload" type="file" accept="video/*" onChange={onPickTechVideo} />
                </div>
                <div className="input-group">
                  <label htmlFor="tech-json-upload">Technical JSON:</label>
                  <input id="tech-json-upload" type="file" accept="application/json" onChange={onPickTechJson} />
                </div>
              </>
            )}
            <div className="input-group">
              <label htmlFor="fps-select">FPS:</label>
              <input id="fps-select" type="number" min={1} max={240} step={1} value={fps}
                onChange={(e) => setFps(Number(e.target.value) || 30)}
                placeholder="e.g., 25" style={{ width: 100 }} />
            </div>
                </div>
              )}
            </div>
    );
  };

  const isMatch = mode === 'match';
  const collapsedInputs = isMatch ? isMatchCollapsed : isTechCollapsed;

  return (
    <div className="container">
      <div style={{ margin: '0 0 12px', display: 'flex', gap: 8, alignItems:'center' }}>
        <button onClick={() => setMode('match')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: mode === 'match' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Match</button>
        <button onClick={() => setMode('technical')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: mode === 'technical' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Technical</button>
        <div style={{ marginLeft:'auto', display:'flex', gap:6 }}>
          <button onClick={()=>setUiVersion('v1')} title="Classic stats UI" style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: uiVersion==='v1' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>UI v1</button>
          <button onClick={()=>setUiVersion('v2')} title="Visualized stats UI" style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: uiVersion==='v2' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>UI v2</button>
        </div>
      </div>
      {/* Only show the full inputs panel in header if not collapsed or if user expanded */}
      {(!collapsedInputs || inputsExpanded) && (
        <div className="header">
          <InputsPanel />
        </div>
      )}
      {statusMsg && (
        <div style={{ position: 'fixed', top: 12, right: 12, background: statusType === 'ok' ? '#064e3b' : '#3f1d1d', border: `1px solid ${statusType === 'ok' ? '#10b981' : '#ef4444'}`, color: '#e5e7eb', padding: '8px 10px', borderRadius: 8, fontSize: 12 }}>
          {statusMsg}
        </div>
      )}

      {mode === 'match' ? (
        uiVersion === 'v2' ? (
          // UI v2: two-panel layout, stats on right, graph below video when section expanded
          <div className="layout">
            <div className="video-area">
              <div className="panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                {collapsedInputs && !inputsExpanded && (
                  <div style={{ marginBottom: 8 }}>
                    <CollapsedInputsStrip />
                  </div>
                )}
                <video className="video-el" ref={videoRef} src={videoUrl} controls />
                {rightTab === 'stats' && activeStatsSection && (
                  <div style={{ marginTop: 12, padding: 12, borderTop: '1px solid #2c2c34', maxHeight: '40%', overflow: 'auto' }}>
                <StatsPanelV2 data={statsData} fps={fps} videoRef={videoRef} activeSection={activeStatsSection} onTimelineInstances={(instances, name) => { setTimelineInstances(instances); setTimelineSectionName(name); }} />
                  </div>
                )}
                {rightTab === 'stats' && activeStatsSection && timelineInstances.length > 0 && (
                  <div style={{ marginTop: 8, padding: '8px 12px', borderTop: '1px solid #2c2c34', width: '100%' }}>
                    <VideoTimelineMarker 
                      instances={timelineInstances} 
                      sectionName={timelineSectionName}
                      fps={fps}
                      videoRef={videoRef}
                      videoDurationSec={videoRef.current?.duration || undefined}
                      colorByCategory={activeStatsSection === 'winners' || activeStatsSection === 'errors' || activeStatsSection === 'eff'}
                    />
                  </div>
                )}
                {rightTab === 'dynamics' && dynData && (
                  <div style={{ marginTop: 12, padding: 12, borderTop: '1px solid #2c2c34', width: '100%', maxHeight: '40%', overflow: 'auto' }}>
                    <RallyDynamics data={dynData} videoRef={videoRef} fps={fps} fullWidth={true} />
                  </div>
                )}
                {rightTab === 'tempo' && (
                  <div style={{ marginTop: 12, padding: 12, borderTop: '1px solid #2c2c34', width: '100%', flexGrow: 1, maxHeight: '50%', overflow: 'auto' }}>
                    <div style={{ display:'flex', gap:8, marginBottom: 12, flexWrap: 'wrap' }}>
                      <button onClick={()=>setTempoView('overview')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='overview' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Overview</button>
                      <button onClick={()=>setTempoView('combos')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='combos' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Combos</button>
                      <button onClick={()=>setTempoView('zones')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='zones' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Zones</button>
                      <button onClick={()=>setTempoView('rally')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='rally' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Rally Pace</button>
                      <button onClick={()=>setTempoView('ineff')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='ineff' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Ineff + Slow</button>
                      <button onClick={()=>setTempoView('rally_tempo')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='rally_tempo' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Rally Tempo</button>
                      <button onClick={()=>setTempoView('tempo_effect')} style={{ padding:'6px 10px', borderRadius:8, border:'1px solid #2c2c34', background: tempoView==='tempo_effect' ? '#18181f' : '#0f0f15', color:'#e5e7eb' }}>Tempo + Eff</button>
                    </div>
                    {tempoView === 'overview' && (
                      tempoEvents.length > 0 ? (
                        <TempoAnalysis events={tempoEvents} thresholds={tempoThresholds} fps={fps} videoRef={videoRef} />
                      ) : <div style={{ opacity: 0.7 }}>Load session folder with *_tempo_events.csv</div>
                    )}
                    {tempoView === 'combos' && (
                      (comboSummaryBand.length > 0 && comboInstancesBand.length > 0) ? (
                        <ComboExplorer summary={comboSummaryBand} instances={comboInstancesBand} videoRef={videoRef} />
                      ) : <div style={{ opacity: 0.7 }}>Load session folder with *_tempo_combo_summary_band.csv and *_tempo_combo_instances_band.csv</div>
                    )}
                    {tempoView === 'zones' && (
                      zoneBuckets.length > 0 ? (
                        <ZoneBuckets data={zoneBuckets} videoRef={videoRef} />
                      ) : <div style={{ opacity: 0.7 }}>Load session folder with *_tempo_zone_buckets.csv</div>
                    )}
                    {tempoView === 'rally' && (
                      rallyMetrics.length > 0 ? (
                        <RallyPace data={rallyMetrics} />
                      ) : <div style={{ opacity: 0.7 }}>Load session folder with *_tempo_rally_metrics.csv</div>
                    )}
                    {tempoView === 'ineff' && (
                      ineffSlowEvents.length > 0 ? (
                        <IneffectiveSlowEvents events={ineffSlowEvents} fps={fps} videoRef={videoRef} />
                      ) : <div style={{ opacity: 0.7 }}>Load session folder with *_tempo_ineffective_slow_events.csv</div>
                    )}
                    {tempoView === 'rally_tempo' && (
                      rallyTempoData && rallyTempoData.rallies.length > 0 ? (
                        <RallyTempoVisualization data={rallyTempoData} videoRef={videoRef} />
                      ) : <div style={{ opacity: 0.7 }}>Load session folder with tempo_analysis_new.csv to generate rally tempo visualization</div>
                    )}
                    {tempoView === 'tempo_effect' && (
                      rallyTempoData && rallyTempoData.rallies.length > 0 && dynData ? (
                        <TempoEffectivenessCorrelation tempoData={rallyTempoData} dynamicsData={dynData} videoRef={videoRef} />
                      ) : <div style={{ opacity: 0.7 }}>Load tempo_analysis_new.csv and rally_timeseries.json to see the merged view</div>
                    )}
                  </div>
                )}
                {rightTab === 'stats' && (
                  <div style={{ marginTop: 8, fontSize: 12, opacity: 0.8 }}>
                    Video: {videoUrl ? 'loaded' : '—'} · Tempo: ev={tempoEvents.length} ine={ineffSlowEvents.length} zone={zoneBuckets.length} combos={comboSummaryBand.length}/{comboInstancesBand.length} rally={rallyMetrics.length}
                  </div>
                )}
              </div>
            </div>
            <aside className="sidebar">
              <div style={{ display:'flex', gap:8, marginBottom: 8, alignItems:'center' }}>
                <button onClick={()=>{setRightTab('summary'); setActiveStatsSection(null); setTimelineInstances([]);}} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='summary' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Summary</button>
                <button onClick={()=>{setRightTab('stats'); if (!activeStatsSection) setTimelineInstances([]);}} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='stats' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Stats</button>
                <button onClick={()=>setRightTab('dynamics')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='dynamics' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Rally Dynamics</button>
                <button onClick={()=>setRightTab('tempo')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='tempo' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Tempo</button>
                <button onClick={()=>{setRightTab('chat'); setActiveStatsSection(null); setTimelineInstances([]);}} title="Ask questions (UI v2 only)" style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='chat' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Chat</button>
              </div>
              <div className="panel" style={{ height: 'calc(100% - 44px)', overflow:'auto' }}>
                {rightTab === 'summary' ? (
                  (v3Text || v2Sections.length > 0 || observations.length > 0 || saSections.length > 0) ? (
                    <>
                      {v3Text ? (
                        <>
                          <h2 style={{ margin: 0 }}>Match Summary</h2>
                          <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', lineHeight: 1.5, fontSize: 14 }}>{v3Text}</div>
                        </>
                      ) : saSections.length > 0 ? (
                        <StructuredAnalysis sections={saSections} videoRef={videoRef as any} fps={fps} />
                      ) : v2Sections.length > 0 ? (
                        <KeyTakeawaysV2 sections={v2Sections} videoRef={videoRef} fps={fps} />
                      ) : (
                        <KeyTakeaways items={observations} videoRef={videoRef} fps={fps} />
                      )}
                    </>
                  ) : null
                ) : rightTab === 'stats' ? (
                  (anyStatsLoaded ? (
                    <StatsPanel data={statsData} fps={fps} videoRef={videoRef} onSectionExpanded={setActiveStatsSection} uiVersion={uiVersion} />
                  ) : null)
                ) : rightTab === 'dynamics' ? (
                  <div style={{ opacity: 0.7 }}>Select Rally Dynamics tab to view effectiveness charts below the video.</div>
                ) : rightTab === 'tempo' ? (
                  <div style={{ opacity: 0.7 }}>Tempo visualizations now appear below the video for more space.</div>
                ) : rightTab === 'chat' ? (
                  <ChatPanelV2 />
                ) : null}
              </div>
            </aside>
          </div>
        ) : (
          // UI v1: original two-panel layout preserved
          <div className="layout">
            <div className="video-area">
              <div className="panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                {collapsedInputs && !inputsExpanded && (
                  <div style={{ marginBottom: 8 }}>
                    <CollapsedInputsStrip />
                  </div>
                )}
                <video className="video-el" ref={videoRef} src={videoUrl} controls />
              </div>
            </div>
            <aside className="sidebar">
              <div style={{ display:'flex', gap:8, marginBottom: 8, alignItems:'center' }}>
                <button onClick={()=>setRightTab('summary')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='summary' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Summary</button>
                <button onClick={()=>setRightTab('stats')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='stats' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Stats</button>
                <button onClick={()=>setRightTab('dynamics')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='dynamics' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Rally Dynamics</button>
                <button onClick={()=>setRightTab('tempo')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: rightTab==='tempo' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Tempo</button>
              </div>
              <div className="panel" style={{ height: 'calc(100% - 44px)', overflow:'auto' }}>
                {rightTab === 'summary' ? (
                  (v3Text || v2Sections.length > 0 || observations.length > 0 || saSections.length > 0) ? (
                    <>
                      {v3Text ? (
                        <>
                          <h2 style={{ margin: 0 }}>Match Summary</h2>
                          <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', lineHeight: 1.5, fontSize: 14 }}>{v3Text}</div>
                        </>
                      ) : saSections.length > 0 ? (
                        <StructuredAnalysis sections={saSections} videoRef={videoRef as any} fps={fps} />
                      ) : v2Sections.length > 0 ? (
                        <KeyTakeawaysV2 sections={v2Sections} videoRef={videoRef} fps={fps} />
                      ) : (
                        <KeyTakeaways items={observations} videoRef={videoRef} fps={fps} />
                      )}
                    </>
                  ) : null
                ) : rightTab === 'stats' ? (
                  (anyStatsLoaded ? (<StatsPanel data={statsData} fps={fps} videoRef={videoRef} uiVersion={uiVersion} />) : null)
                ) : rightTab === 'dynamics' ? (
                  dynData ? (<RallyDynamics data={dynData} videoRef={videoRef} fps={fps} />) : (
                    <div style={{ opacity: 0.7 }}>Load Rally Dynamics JSON to view swings chart.</div>
                  )
                ) : rightTab === 'tempo' ? (
                  tempoEvents.length > 0 ? (<TempoAnalysis events={tempoEvents} thresholds={tempoThresholds} fps={fps} videoRef={videoRef} />) : (
                    <div style={{ opacity: 0.7 }}>Load Tempo Events CSV (and optional Thresholds JSON) to view tempo chart.</div>
                  )
                ) : null}
              </div>
            </aside>
          </div>
        )
      ) : (
        <div className="layout">
          <div className="video-area">
            <div className="panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              {collapsedInputs && !inputsExpanded && (
                <div style={{ marginBottom: 8 }}>
                  <CollapsedInputsStrip />
                </div>
              )}
              <video className="video-el" ref={techVideoRef} src={techVideoUrl} controls />
            </div>
          </div>
          <aside className="sidebar">
            <div className="panel">
              <h3 style={{ margin: 0 }}>Technical observations</h3>
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr', gap: 8 }}>
                {techIssues.map(issue => (
                  <div key={issue.issue_text}>
                    <div onClick={() => setSelectedTechIssue(issue.issue_text)}
                      style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.4rem 0.6rem', background: selectedTechIssue === issue.issue_text ? '#18181f' : '#0f0f15', border: '1px solid #2c2c34', borderRadius: 8, cursor: 'pointer' }}>
                      <span>{issue.issue_text}</span>
                      <span style={{ opacity: 0.7 }}>{issue.timestampsSec.length}</span>
                    </div>
                    {selectedTechIssue === issue.issue_text && (
                      <div style={{ marginTop: '0.4rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                        {issue.timestampsSec.map((sec, i) => (
                          <div key={`tech-ts-${issue.issue_text}-${sec}-${i}`}
                            onClick={() => { const v = techVideoRef.current; if (!v) return; v.currentTime = sec; v.play().catch(() => {}); }}
                            style={{ padding: '0.35rem 0.6rem', background: '#eef2ff22', border: '1px solid #334155', borderRadius: 999, fontSize: 12, color: '#cbd5e1', cursor: 'pointer', userSelect: 'none' }}
                            title={`Jump to ${formatMs(sec * 1000)}`}>
                            [{formatMs(sec * 1000)}]
                          </div>
                        ))}
                      </div>
                    )}
                    {selectedTechIssue === issue.issue_text && (
                      <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.45 }}>
                        <div style={{ fontWeight: 700, marginBottom: 4 }}>Observations</div>
                        <div style={{ marginBottom: 8 }}>{issue.issue_feedback || '—'}</div>
                        <div style={{ fontWeight: 700, marginBottom: 4 }}>Recommendations</div>
                        <div>{issue.recommended_feedback || '—'}</div>
                      </div>
                    )}
                  </div>
                ))}
                {techIssues.length === 0 && (
                  <div style={{ opacity: 0.7, fontSize: 14 }}>Load a technical JSON to view player issues and timestamps.</div>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;
