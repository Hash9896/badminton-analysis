import React, { useEffect, useMemo, useRef, useState } from 'react';
import { KeyTakeaways, type Observation } from './components/KeyTakeaways';
import { KeyTakeawaysV2, type V2Section } from './components/KeyTakeawaysV2';
import StructuredAnalysis, { type SASection } from './components/StructuredAnalysis';
import RallyDynamics, { type DynamicsPayload } from './components/RallyDynamics';
import type { TempoEvent } from './components/TempoAnalysis';
import type { IneffSlowEvent } from './components/IneffectiveSlowEvents';
import type { ZoneBucketRow } from './components/ZoneBuckets';
import type { ComboSummaryBandRow, ComboInstanceBandRow } from './components/ComboExplorer';
import type { RallyMetricsRow } from './components/RallyPace';
import RallyTempoVisualization, { type RallyTempoPayload } from './components/RallyTempoVisualization';
import { SubmissionPanel } from './components/SubmissionPanel';
import SubmissionAdminPanel from './components/SubmissionAdminPanel';
import type { Submission } from './types/submission';
import { formatMs } from './utils/timecode';
import './App.css';
import Papa from 'papaparse';
import type { StatsData } from './components/StatsPanel';
import StatsPanelV2, { VideoTimelineMarker, type TimelineInstance } from './components/StatsPanelV2.tsx';
import { computeRallyTags, type RallyTags } from './utils/rallyTags';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string) || 'http://localhost:8000';

// Generic JSON type
type AnyJson = Record<string, any>;

// Technical issue type
type TechIssue = {
  issue_text: string;
  issue_feedback: string;
  recommended_feedback: string;
  timestampsSec: number[];
};

type StatsSurface = 'summary' | 'sr' | 'winners' | 'errors' | 'eff' | 'zones' | 'shotDist' | 'winRallies' | 'loseRallies' | 'threeShot';

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
  const forceOpsPanel = (import.meta.env.VITE_FORCE_OPS_PANEL as string) === 'true';
  const [opsPanelVisible, setOpsPanelVisible] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    try {
      return window.localStorage.getItem('opsPanelVisible') === 'true';
    } catch {
      return false;
    }
  });
  const shouldShowOpsPanel = forceOpsPanel || opsPanelVisible;

  const [submissionPanelCollapsed, setSubmissionPanelCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    try {
      return window.localStorage.getItem('submissionPanelCollapsed') === 'true';
    } catch {
      return false;
    }
  });

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
  const [techIssues, setTechIssues] = useState<TechIssue[]>([]);
  const [selectedTechIssue, setSelectedTechIssue] = useState<string | null>(null);

  // Right panel collapse states (handled per-section/issue; no global collapse state)

  // Shared
  const [fps, setFps] = useState<number>(30);
  const [statusMsg, setStatusMsg] = useState<string>('');
  const [statusType, setStatusType] = useState<'ok' | 'err' | ''>('');
  const [statsData, setStatsData] = useState<StatsData>({});
  const [v3Text, setV3Text] = useState<string>('');
  const [dynData, setDynData] = useState<DynamicsPayload | null>(null);
  const [tempoEvents, setTempoEvents] = useState<TempoEvent[]>([]);
  const [ineffSlowEvents, setIneffSlowEvents] = useState<IneffSlowEvent[]>([]);
  const [zoneBuckets, setZoneBuckets] = useState<ZoneBucketRow[]>([]);
  const [comboSummaryBand, setComboSummaryBand] = useState<ComboSummaryBandRow[]>([]);
  const [comboInstancesBand, setComboInstancesBand] = useState<ComboInstanceBandRow[]>([]);
  const [rallyMetrics, setRallyMetrics] = useState<RallyMetricsRow[]>([]);
  const [rallyTempoData, setRallyTempoData] = useState<RallyTempoPayload | null>(null);
  const [tempoView, setTempoView] = useState<'overview'|'combos'|'zones'|'rally'|'ineff'|'rally_tempo'|'tempo_effect'>('rally_tempo');
  const [activeStatsSection, setActiveStatsSection] = useState<string | null>(null);
  const [timelineInstances, setTimelineInstances] = useState<TimelineInstance[]>([]);
  const [timelineSectionName, setTimelineSectionName] = useState<string>('');
  const [rallyTags, setRallyTags] = useState<Record<string, RallyTags>>({});
  const [primaryTab, setPrimaryTab] = useState<'stats'|'dynamics'|'tempo'|'summary'>('stats');
  const [statsSurface, setStatsSurface] = useState<StatsSurface | null>(null);
  const [playerView, setPlayerView] = useState<'both'|'P0'|'P1'>('both');
  const [loadingSubmissionId, setLoadingSubmissionId] = useState<string | null>(null);

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

  useEffect(() => {
    if (rallyTempoData) {
      setRallyTags(computeRallyTags(rallyTempoData, rallyMetrics, dynData));
    } else {
      setRallyTags({});
    }
  }, [rallyTempoData, rallyMetrics, dynData]);

  useEffect(() => { /* no auto-loads */ }, []);

  useEffect(() => {
    if (primaryTab !== 'stats') {
      setActiveStatsSection(null);
      setTimelineInstances([]);
      setTimelineSectionName('');
      return;
    }
    if (!statsSurface || statsSurface === 'summary') {
      setActiveStatsSection(null);
      setTimelineInstances([]);
      setTimelineSectionName('');
    } else {
      setActiveStatsSection(statsSurface);
    }
  }, [primaryTab, statsSurface]);

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

  useEffect(() => {
    if (forceOpsPanel) return;
    const sequence = ['o', 'o', 'p', 's'];
    let idx = 0;
    const handler = (event: KeyboardEvent) => {
      const activeTag = (event.target as HTMLElement)?.tagName?.toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea') return;
      const key = event.key.toLowerCase();
      if (key === sequence[idx]) {
        idx += 1;
        if (idx === sequence.length) {
          setOpsPanelVisible(prev => {
            const next = !prev;
            try {
              window.localStorage.setItem('opsPanelVisible', next ? 'true' : 'false');
            } catch {
              // ignore storage issues
            }
            return next;
          });
          idx = 0;
        }
      } else {
        idx = key === sequence[0] ? 1 : 0;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [forceOpsPanel]);

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
  const loadSessionFromFiles = async (files: File[]) => {
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
      try {
        window.localStorage.setItem('submissionPanelCollapsed', 'true');
      } catch {
        // ignore
      }
      setSubmissionPanelCollapsed(true);
    } catch {
      showStatus('Failed to load session folder', 'err');
    }
  };

  const onPickFolder: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const files = Array.from(e.target.files || []);
    await loadSessionFromFiles(files);
      e.currentTarget.value = '';
  };

  const loadSubmissionFolder = async (folderPath: string) => {
    const response = await fetch(`${BACKEND_URL}/reports/folder?path=${encodeURIComponent(folderPath)}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch folder (${response.status})`);
    }
    const data = await response.json();
    
    // Fetch each file from S3 URLs
    const filePromises: Array<Promise<File | null>> = data.files.map(async (fileInfo: { name: string; url: string; size: number }) => {
      if (!fileInfo.url) return null;
      try {
        const fileResponse = await fetch(fileInfo.url);
        if (!fileResponse.ok) return null;
        const blob = await fileResponse.blob();
        const file = new File([blob], fileInfo.name);
        try {
          Object.defineProperty(file, 'webkitRelativePath', {
            value: fileInfo.name,
            configurable: false,
          });
        } catch {
          // ignore inability to set path metadata
        }
        return file;
      } catch {
        return null;
      }
    });
    
    const fetchedFiles = (await Promise.all(filePromises)).filter((f): f is File => f !== null);
    await loadSessionFromFiles(fetchedFiles);
  };

  const handleOpenSubmission = async (submission: Submission) => {
    if (loadingSubmissionId) return;
    if (submission.folder) {
      setLoadingSubmissionId(submission.id);
      try {
        await loadSubmissionFolder(submission.folder);
        try {
          window.localStorage.setItem('submissionPanelCollapsed', 'true');
        } catch {
          // ignore
        }
        setSubmissionPanelCollapsed(true);
      } catch (err) {
        console.error(err);
        showStatus('Failed to load submission folder', 'err');
      } finally {
        setLoadingSubmissionId(null);
      }
      return;
    }
    if (submission.report_url) {
      window.open(submission.report_url, '_blank', 'noopener,noreferrer');
      return;
    }
    showStatus('No folder configured for this submission yet.', 'err');
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
    setTechVideoUrl(url); showStatus('Technical video loaded', 'ok');
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

  const InputsPanel = () => {
    if (mode === 'match') {
  return (
        <label className="session-loader">
          Load Session Folder
          <input type="file" multiple onChange={onPickFolder} {...({ webkitdirectory: '' } as any)} />
        </label>
      );
    }
    return (
      <div className="session-loader--tech">
        <label className="session-loader__btn">
          Tech Video
          <input type="file" accept="video/*" onChange={onPickTechVideo} />
        </label>
        <label className="session-loader__btn">
          Tech JSON
          <input type="file" accept="application/json" onChange={onPickTechJson} />
        </label>
        </div>
    );
  };


  // Helper to extract jump links for selected section (UI v1 format) - grouped by category
  type JumpLinkGroup = { category: string; count: number; links: Array<{ label: string; title: string; sec: number }> };
  
  // Shot category mapping for rally categorization
  const shotCategories = {
    Attacking: ['forehand_smash','overhead_smash','backhand_smash','forehand_halfsmash','overhead_halfsmash','forehand_nettap','backhand_nettap','forehand_drive','backhand_drive','flat_game','forehand_push','backhand_push'],
    Defense: ['forehand_defense','backhand_defense','forehand_defense_cross','backhand_defense_cross'],
    NetBattle: ['forehand_netkeep','backhand_netkeep','forehand_dribble','backhand_dribble'],
    Placement: ['overhead_drop','forehand_drop','backhand_drop','forehand_pulldrop','backhand_pulldrop'],
    Reset: ['forehand_lift','backhand_lift','forehand_clear','overhead_clear','backhand_clear'],
  };
  const mapShotToBucket = (shot: string): keyof typeof shotCategories | 'Other' => {
    const n = String(shot || '').replace(/_cross$/i, '').trim().toLowerCase();
    for (const k of Object.keys(shotCategories) as (keyof typeof shotCategories)[]) {
      if (shotCategories[k].some(s => s.toLowerCase() === n)) return k;
    }
    return 'Other';
  };
  
  const extractJumpLinks = (section: StatsSurface | null): JumpLinkGroup[] => {
    if (!section) return [];
    const groups = new Map<string, Array<{ label: string; title: string; sec: number }>>();
    const toSec = (frame: number) => (Number.isFinite(frame) && fps > 0 ? frame / fps : 0);
    const normalizeShot = (s: string) => String(s || '').replace(/_cross$/i, '').trim();
    const addLink = (category: string, link: { label: string; title: string; sec: number }) => {
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category)!.push(link);
    };

    if (section === 'winners') {
      const extract = (rows?: any[]) => {
        if (!Array.isArray(rows)) return;
        for (const r of rows || []) {
          const f = parseInt(String(r.FrameNumber || r.LastShotFrame || ''), 10);
          const stroke = normalizeShot(String(r.Stroke || ''));
          if (Number.isFinite(f) && f > 0 && stroke) {
            const sec = toSec(f);
            addLink(stroke, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `${stroke} (±2s)`, sec });
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract(statsData.p0Winners);
      if (playerView === 'both' || playerView === 'P1') extract(statsData.p1Winners);
    } else if (section === 'errors') {
      const extract = (rows?: any[]) => {
        if (!Array.isArray(rows)) return;
        for (const r of rows || []) {
          const f = parseInt(String(r.FrameNumber || r.LastShotFrame || ''), 10);
          const stroke = normalizeShot(String(r.Stroke || ''));
          if (Number.isFinite(f) && f > 0 && stroke) {
            const sec = toSec(f);
            addLink(stroke, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `${stroke} (±2s)`, sec });
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract(statsData.p0Errors);
      if (playerView === 'both' || playerView === 'P1') extract(statsData.p1Errors);
    } else if (section === 'sr') {
      const extract = (rows?: any[]) => {
        if (!Array.isArray(rows)) return;
        for (const r of rows || []) {
          const serve = String(r.Serve_Shot || '').trim();
          const recv = String(r.Receive_Shot || '').trim();
          const category = `${serve} → ${recv}`;
          const frames = String(r.Frames || '').trim();
          if (frames) {
            const parts = frames.split(',').map(s => s.trim()).filter(Boolean);
            for (const p of parts) {
              const m = p.match(/(\d+)\s*->\s*(\d+)/);
              if (m) {
                const frame = parseInt(m[1], 10);
                if (Number.isFinite(frame) && frame > 0) {
                  const sec = toSec(frame);
                  addLink(category, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `${serve}→${recv} (±2s)`, sec });
                }
              }
            }
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract(statsData.p0SrPatterns);
      if (playerView === 'both' || playerView === 'P1') extract(statsData.p1SrPatterns);
    } else if (section === 'zones') {
      const extract = (player: 'P0'|'P1') => {
        const rows = Array.isArray(statsData.zoneTopBottom) ? statsData.zoneTopBottom.filter(r => r && String(r.Player || '').toUpperCase() === player) : [];
        for (const r of rows) {
          const allFramesStr = String(r.AllFrames || '').trim();
          const zone = String(r.AnchorHittingZone || '').trim();
          if (allFramesStr && zone) {
            const parts = allFramesStr.split('|').filter(Boolean);
            for (const part of parts) {
              const m = part.match(/F(\d+)/i);
              if (m) {
                const f = parseInt(m[1], 10);
                if (Number.isFinite(f) && f > 0) {
                  const sec = toSec(f);
                  addLink(zone, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `${zone} F${f} (±2s)`, sec });
                }
              }
            }
          }
        }
      };
      if (playerView === 'both' || playerView === 'P0') extract('P0');
      if (playerView === 'both' || playerView === 'P1') extract('P1');
    } else if (section === 'eff') {
      // Include all effectiveness rows including forced/unforced errors
      const rowsAll = Array.isArray(statsData.effectiveness) ? statsData.effectiveness.filter(r => {
        const stroke = String(r.Stroke || '').toLowerCase();
        const isServe = stroke.includes('serve') || String(r.is_serve || '').toLowerCase() === 'true';
        const label = String(r.effectiveness_label || r.Effectiveness_Label || '').toLowerCase();
        const isTerminal = label.includes('rally winner') || label.startsWith('serve');
        return !isServe && !isTerminal; // Keep forced/unforced errors
      }) : [];
      
      const extract = (player: 'P0'|'P1') => {
        const playerRows = rowsAll.filter(r => r && String(r.Player || '').toUpperCase() === player);
        
        // Group by effectiveness type, then by shot type
        const byTypeAndShot: Record<string, Record<string, Array<{f: number, stroke: string, label: string}>>> = {
          'most effective': {},
          'most ineffective': {},
          'forced errors': {},
          'unforced errors': {}
        };
        
        for (const r of playerRows) {
          const f = parseInt(String(r.FrameNumber || ''), 10);
          const stroke = normalizeShot(String(r.Stroke || ''));
          const color = String(r.color || '').toLowerCase();
          const label = String(r.effectiveness_label || r.Effectiveness_Label || '').toLowerCase();
          
          if (Number.isFinite(f) && f > 0 && stroke) {
            let type = '';
            if (label.includes('forced error')) {
              type = 'forced errors';
            } else if (label.includes('unforced error')) {
              type = 'unforced errors';
            } else if (color === 'green' || label.includes('effective')) {
              type = 'most effective';
            } else if (color === 'red' || color === 'darkred' || label.includes('ineffective')) {
              type = 'most ineffective';
            }
            
            if (type) {
              if (!byTypeAndShot[type][stroke]) {
                byTypeAndShot[type][stroke] = [];
              }
              byTypeAndShot[type][stroke].push({ f, stroke, label });
            }
          }
        }
        
        // Add links grouped by type and shot
        const typeLabels: Record<string, string> = {
          'most effective': 'most effective',
          'most ineffective': 'most ineffective',
          'forced errors': 'forced errors',
          'unforced errors': 'unforced errors'
        };
        
        for (const [type, byShot] of Object.entries(byTypeAndShot)) {
          // Sort shots by count (descending)
          const sortedShots = Object.entries(byShot).sort((a, b) => b[1].length - a[1].length);
          
          for (const [shot, items] of sortedShots) {
            if (items.length > 0) {
              // Category format: "P0 - most effective - Forehand clear"
              const category = `${player} - ${typeLabels[type]} - ${shot}`;
              for (const item of items) {
                const sec = toSec(item.f);
                addLink(category, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `${item.stroke} (${type}) F${item.f} (±2s)`, sec });
              }
            }
          }
        }
      };
      
      if (playerView === 'both' || playerView === 'P0') extract('P0');
      if (playerView === 'both' || playerView === 'P1') extract('P1');
    } else if (section === 'winRallies' || section === 'loseRallies') {
      const extract = (player: 'P0'|'P1') => {
        const rows = section === 'winRallies'
          ? (player === 'P0' ? (statsData.p0WinningRallies || []) : (statsData.p1WinningRallies || []))
          : (player === 'P0' ? (statsData.p0LosingRallies || []) : (statsData.p1LosingRallies || []));
        
        // Group by rally category
        const byCategory: Record<string, Array<{start: number, game: string, rally: string, lastShot: string}>> = {
          'Attacking': [],
          'Defense': [],
          'NetBattle': [],
          'Placement': [],
          'Reset': [],
          'Other': []
        };
        
        for (const r of rows) {
          const start = parseInt(String(r.StartFrame || ''), 10);
          const game = String(r.GameNumber || '');
          const rally = String(r.RallyNumber || '');
          const lastShot = String(r.LastShot || r.LastShotName || r.LastShotType || '').trim();
          if (Number.isFinite(start) && start > 0) {
            const category = mapShotToBucket(lastShot);
            byCategory[category].push({ start, game, rally, lastShot });
          }
        }
        
        // Add links grouped by category
        const categoryOrder: (keyof typeof shotCategories | 'Other')[] = ['Attacking', 'Defense', 'NetBattle', 'Placement', 'Reset', 'Other'];
        const categoryLabels: Record<string, string> = {
          'Attacking': 'attacking',
          'Defense': 'defensive',
          'NetBattle': 'Net battle',
          'Placement': 'Placement',
          'Reset': 'Reset',
          'Other': 'Other'
        };
        for (const cat of categoryOrder) {
          if (byCategory[cat].length > 0) {
            const categoryName = `${player} - ${categoryLabels[cat]}`;
            for (const item of byCategory[cat]) {
              const sec = toSec(item.start);
              addLink(categoryName, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `G${item.game}-R${item.rally} ${item.lastShot} (±2s)`, sec });
            }
          }
        }
      };
      
      if (playerView === 'both' || playerView === 'P0') extract('P0');
      if (playerView === 'both' || playerView === 'P1') extract('P1');
    } else if (section === 'threeShot') {
      const rows = statsData.threeShot || [];
      for (const r of rows) {
        const f = parseInt(String(r.FirstFrame || r.TargetFrame || r.FrameNumber || ''), 10);
        const seq = String(r.Sequence || r.Label || '').trim();
        if (Number.isFinite(f) && f > 0 && seq) {
          const sec = toSec(f);
          addLink(seq, { label: `[${formatMs(Math.max(0, (sec-2))*1000)}]`, title: `${seq} F${f} (±2s)`, sec });
        }
      }
    }
    // shotDist doesn't have direct frame references, skip for now
    
    // Convert Map to array of groups
    return Array.from(groups.entries()).map(([category, links]) => ({
      category,
      count: links.length,
      links
    })).sort((a, b) => b.count - a.count); // Sort by count descending
  };

  const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
    const v = ref.current; if (!v) return; const s = Math.max(0, sec - 2); v.currentTime = s; v.play().catch(() => {});
  };

  const renderSummaryBlock = () => {
    if (v3Text) {
    return (
        <>
          <h2 style={{ margin: 0 }}>Match Summary</h2>
          <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', lineHeight: 1.5, fontSize: 14 }}>{v3Text}</div>
        </>
      );
    }
    if (saSections.length > 0) {
      return <StructuredAnalysis sections={saSections} videoRef={videoRef as any} fps={fps} />;
    }
    if (v2Sections.length > 0) {
      return <KeyTakeawaysV2 sections={v2Sections} videoRef={videoRef} fps={fps} />;
    }
    if (observations.length > 0) {
      return <KeyTakeaways items={observations} videoRef={videoRef} fps={fps} />;
    }
    return <div style={{ opacity: 0.7 }}>Load a summary file to view insights.</div>;
  };

  const primaryTabsConfig: Array<{ key: 'stats'|'dynamics'|'tempo'|'summary'; label: string }> = [
    { key: 'stats', label: 'Stats' },
    { key: 'dynamics', label: 'Rally Dynamics' },
    { key: 'tempo', label: 'Tempo' },
    { key: 'summary', label: 'Summary' },
  ];

  const statsSegments: Array<{ key: StatsSurface; label: string; available: boolean }> = [
    { key: 'shotDist', label: 'Shot Mix', available: Boolean(statsData.shotDistribution && statsData.shotDistribution.length) },
    { key: 'zones', label: 'Zone Effectiveness', available: Boolean(statsData.zoneTopBottom && statsData.zoneTopBottom.length) },
    { key: 'sr', label: 'Service → Receive', available: Boolean((statsData.p0SrPatterns && statsData.p0SrPatterns.length) || (statsData.p1SrPatterns && statsData.p1SrPatterns.length)) },
    { key: 'eff', label: 'Shot Effectiveness', available: Boolean(statsData.effectiveness && statsData.effectiveness.length) },
    { key: 'winners', label: 'Winners', available: anyStatsLoaded },
    { key: 'errors', label: 'Errors', available: anyStatsLoaded },
    { key: 'winRallies', label: 'Winning Rallies', available: Boolean((statsData.p0WinningRallies && statsData.p0WinningRallies.length) || (statsData.p1WinningRallies && statsData.p1WinningRallies.length)) },
    { key: 'loseRallies', label: 'Losing Rallies', available: Boolean((statsData.p0LosingRallies && statsData.p0LosingRallies.length) || (statsData.p1LosingRallies && statsData.p1LosingRallies.length)) },
    { key: 'threeShot', label: '3 Shot Sequence', available: Boolean(statsData.threeShot && statsData.threeShot.length) },
  ];

  const tempoSegments: Array<{ key: typeof tempoView; label: string; available: boolean }> = [
    { key: 'rally_tempo', label: 'Rally Tempo', available: Boolean(rallyTempoData && rallyTempoData.rallies.length) },
  ];

  return (
    <div className="container">
      <div className="header-controls">
        <div className="header-controls__left">
        <button onClick={() => setMode('match')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: mode === 'match' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Match</button>
        <button onClick={() => setMode('technical')} style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: mode === 'technical' ? '#18181f' : '#0f0f15', color: '#e5e7eb' }}>Technical</button>
          <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:13 }}>
            <span>FPS:</span>
            <select value={fps} onChange={(e)=>setFps(Number(e.target.value) || 30)} style={{ background:'#0f0f15', color:'#e5e7eb', border:'1px solid #2c2c34', borderRadius:6, padding:'4px 6px' }}>
              {[24,25,30,50,60,120].map(val => <option key={val} value={val}>{val}</option>)}
            </select>
          </label>
          <InputsPanel />
        </div>
      </div>
      {/* Only show the full inputs panel in header if not collapsed or if user expanded */}
      {statusMsg && (
        <div style={{ position: 'fixed', top: 12, right: 12, background: statusType === 'ok' ? '#064e3b' : '#3f1d1d', border: `1px solid ${statusType === 'ok' ? '#10b981' : '#ef4444'}`, color: '#e5e7eb', padding: '8px 10px', borderRadius: 8, fontSize: 12 }}>
          {statusMsg}
        </div>
      )}

      {shouldShowOpsPanel && <SubmissionAdminPanel />}

      {mode === 'match' ? (
        <>
          <div className="submission-collapse">
            <button
              type="button"
              onClick={() => {
                const next = !submissionPanelCollapsed;
                setSubmissionPanelCollapsed(next);
                try {
                  window.localStorage.setItem('submissionPanelCollapsed', next ? 'true' : 'false');
                } catch {
                  // ignore
                }
              }}
            >
              {submissionPanelCollapsed ? 'Show submission panel' : 'Hide submission panel'}
            </button>
            {!submissionPanelCollapsed && (
              <SubmissionPanel
                mode="match"
                onOpenSubmission={handleOpenSubmission}
                loadingSubmissionId={loadingSubmissionId}
              />
            )}
          </div>
          <div className="app-shell-v2">
            <header className="app-bar">
              <div className="app-bar__left">
                <div className="app-breadcrumb">
                  <span className="app-breadcrumb__chevron">‹</span>
                  <span>Match report</span>
                  </div>
                <div className="app-meta">
                  <span>Paradigm Sports</span>
                  <span>·</span>
                  <span>{new Date().toLocaleDateString(undefined, { day: '2-digit', month: 'long', year: 'numeric' })}</span>
                </div>
              </div>
              <div className="app-bar__actions">
                <span className={`status-chip ${videoLoaded ? 'status-chip--ready' : ''}`}>{videoLoaded ? 'Video ready' : 'Video missing'}</span>
                <span className={`status-chip ${summaryLoaded ? 'status-chip--ready' : ''}`}>{summaryLoaded ? 'Summary ready' : 'Summary pending'}</span>
                <span className={`status-chip ${anyStatsLoaded ? 'status-chip--ready' : ''}`}>{anyStatsLoaded ? 'Stats ready' : 'Stats pending'}</span>
              </div>
            </header>


            <nav className="primary-tabs">
              {primaryTabsConfig.map(tab => (
                <button
                  key={tab.key}
                  className={`tab-btn ${primaryTab === tab.key ? 'tab-btn--active' : ''}`}
                  onClick={() => setPrimaryTab(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            <div className="content-split">
              <aside className="video-column">
                <section className="hero-stage hero-stage--side">
                <video className="video-el" ref={videoRef} src={videoUrl} controls />
                  <div className="hero-meta">
                    Video: {videoUrl ? 'loaded' : '—'} · Tempo: ev={tempoEvents.length} ine={ineffSlowEvents.length} zone={zoneBuckets.length} combos={comboSummaryBand.length}/{comboInstancesBand.length} rally={rallyMetrics.length}
                  </div>
                  {primaryTab === 'stats' && activeStatsSection && timelineInstances.length > 0 && (
                    <div className="hero-timeline">
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
                </section>
              </aside>

              <main className="data-column">
                <div className="data-sticky-top">
                  {primaryTab === 'stats' && (
                    <>
                      <div className="secondary-pills">
                        {statsSegments.map(segment => (
                          <button
                            key={segment.key}
                            disabled={!segment.available}
                            className={`pill-btn ${statsSurface === segment.key ? 'pill-btn--active' : ''}`}
                            onClick={() => segment.available && setStatsSurface(segment.key)}
                          >
                            {segment.label}
                          </button>
                        ))}
                      </div>
                      {activeStatsSection && (
                        <div style={{ display: 'flex', gap: 6, marginTop: 8, alignItems: 'center' }}>
                          <span style={{ fontSize: 12, opacity: 0.8 }}>Player view:</span>
                          <button onClick={() => setPlayerView('both')} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2c2c34', background: playerView === 'both' ? '#18181f' : '#0f0f15', color: '#e5e7eb', fontSize: 12 }}>Both</button>
                          <button onClick={() => setPlayerView('P0')} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2c2c34', background: playerView === 'P0' ? '#18181f' : '#0f0f15', color: '#e5e7eb', fontSize: 12 }}>P0</button>
                          <button onClick={() => setPlayerView('P1')} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2c2c34', background: playerView === 'P1' ? '#18181f' : '#0f0f15', color: '#e5e7eb', fontSize: 12 }}>P1</button>
                  </div>
                )}
                    </>
                  )}
                  {primaryTab === 'tempo' && (
                    <div className="secondary-pills">
                      {tempoSegments.map(segment => (
                        <button
                          key={segment.key}
                          disabled={!segment.available}
                          className={`pill-btn ${tempoView === segment.key ? 'pill-btn--active' : ''}`}
                          onClick={() => segment.available && setTempoView(segment.key)}
                        >
                          {segment.label}
                        </button>
                      ))}
                  </div>
                )}
              </div>

                <div className="data-scrollable">
                  {primaryTab === 'summary' && (
                    <div className="panel panel--summary">
                      {renderSummaryBlock()}
            </div>
                  )}

                  {primaryTab === 'stats' && (
                    <>
                      {/* Jump Links Section - tied to selected pill */}
                      {statsSurface && statsSurface !== 'summary' && statsSurface !== 'shotDist' && (
                        <div className="panel panel--jump-links">
                          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, opacity: 0.9 }}>
                            {statsSegments.find(s => s.key === statsSurface)?.label || 'Jump Links'}
                          </div>
                          {extractJumpLinks(statsSurface).length === 0 ? (
                            <div style={{ opacity: 0.7, fontSize: 13 }}>No jump links available for this section.</div>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                              {extractJumpLinks(statsSurface).map((group, groupIdx) => (
                                <div key={`group-${statsSurface}-${groupIdx}`} style={{ marginBottom: 4 }}>
                                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: '#e5e7eb' }}>
                                    {group.category} ({group.count})
                                  </div>
                                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                    {group.links.map((link, linkIdx) => (
                                      <div
                                        key={`jump-${statsSurface}-${groupIdx}-${linkIdx}`}
                                        onClick={() => seek(videoRef, link.sec)}
                                        title={link.title}
                                        style={{
                                          padding: '0.35rem 0.6rem',
                                          background: '#eef2ff22',
                                          border: '1px solid #334155',
                                          borderRadius: 999,
                                          fontSize: 12,
                                          color: '#cbd5e1',
                                          cursor: 'pointer',
                                          userSelect: 'none'
                                        }}
                                      >
                                        {link.label}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Graph Section - only selected section */}
                      {statsSurface && statsSurface !== 'summary' && (
                        <div className="panel panel--visual">
                          {activeStatsSection ? (
                            <StatsPanelV2
                              data={statsData}
                              fps={fps}
                              videoRef={videoRef}
                              activeSection={activeStatsSection}
                              playerView={playerView}
                              onTimelineInstances={(instances, name) => { setTimelineInstances(instances); setTimelineSectionName(name); }}
                            />
                          ) : (
                            <div style={{ opacity: 0.7, fontSize: 14 }}>Select a section to view charts.</div>
                          )}
                        </div>
                      )}
                      {!statsSurface && (
                        <div className="panel panel--visual">
                          <div style={{ opacity: 0.7, fontSize: 14 }}>Select a section above to view charts and jump links.</div>
                        </div>
                      )}
                    </>
                  )}

                  {primaryTab === 'dynamics' && (
                    <div className="panel panel--visual">
                      {dynData ? (
                        <RallyDynamics data={dynData} videoRef={videoRef} fps={fps} fullWidth={true} rallyTags={rallyTags} />
                      ) : (
                        <div style={{ opacity: 0.7 }}>Load rally_timeseries.json to view rally swings.</div>
                      )}
                    </div>
                  )}

                  {primaryTab === 'tempo' && (
                    <div className="panel panel--visual">
                      {rallyTempoData && rallyTempoData.rallies.length > 0 ? (
                        <RallyTempoVisualization data={rallyTempoData} videoRef={videoRef} tags={rallyTags} />
                      ) : (
                        <div style={{ opacity: 0.7 }}>Load tempo_analysis_new.csv to generate rally tempo visualization.</div>
                      )}
                    </div>
                  )}

              </div>
              </main>
            </div>
          </div>
        </>
      ) : (
        <>
        <SubmissionPanel mode="technical" />
        <div className="layout">
          <div className="video-area">
            <div className="panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
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
        </>
      )}
    </div>
  );
}

export default App;
