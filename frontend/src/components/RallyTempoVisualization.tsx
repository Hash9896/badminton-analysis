import React, { useEffect, useMemo, useState } from 'react';
import {
  CLUTCH_FILTERS,
  EFFECTIVENESS_FILTERS,
  LENGTH_FILTERS,
  TEMPO_FILTERS,
  type RallyTags,
  resolveTempoDominance,
} from '../utils/rallyTags';

export type RallyTempoShot = {
  stroke_number: number;
  time_sec: number;
  time_in_rally: number;
  frame_number: number;
  response_time_sec: number | null;
  stroke: string;
  effectiveness: number | null;
  tempo_control: string;
  control_type: string;
  classification: string;
};

export type RallyTempoData = {
  rally_id: string;
  game_number: number;
  rally_number: number;
  rally_winner: string;
  rally_start_time: number;
  p0_shots: RallyTempoShot[];
  p1_shots: RallyTempoShot[];
  total_shots: number;
};

export type RallyTempoPayload = {
  rallies: RallyTempoData[];
  total_rallies: number;
  metadata?: any;
};

type Props = {
  data: RallyTempoPayload | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  tags?: Record<string, RallyTags>;
};

const PAD = 40;
const H = 400;
const W = 1000;

const filterSelectStyle: React.CSSProperties = {
  padding: '4px 8px',
  borderRadius: 6,
  border: '1px solid #2c2c34',
  background: '#0f0f15',
  color: '#e5e7eb',
};

const seek = (ref: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = ref.current;
  if (!v) return;
  const s = Math.max(0, sec - 2);
  v.currentTime = s;
  v.play().catch(() => {});
};

// Color mapping for tempo states
const getTempoColor = (tempoControl: string, player: 'P0' | 'P1'): string => {
  const base = player === 'P0' ? '#3b82f6' : '#ef4444'; // Blue for P0, Red for P1
  
  switch (tempoControl.toLowerCase()) {
    case 'player_dominant':
      return player === 'P0' ? '#10b981' : '#22c55e'; // Green shades
    case 'opponent_dominant':
      return player === 'P0' ? '#f59e0b' : '#f97316'; // Orange/amber
    case 'player_aggressive':
      return player === 'P0' ? '#8b5cf6' : '#a78bfa'; // Purple
    case 'neutral':
    default:
      return base;
  }
};

// Classification styling helpers
const classificationColors: Record<'P0' | 'P1', Record<'fast' | 'normal' | 'slow', string>> = {
  P0: {
    fast: '#06b6d4', // Cyan
    normal: '#3b82f6', // Blue
    slow: '#1e40af', // Navy
  },
  P1: {
    fast: '#f97316', // Orange
    normal: '#ef4444', // Red
    slow: '#dc2626', // Dark red
  },
};

const classificationSizes: Record<'fast' | 'normal' | 'slow', number> = {
  fast: 8,
  normal: 6,
  slow: 5,
};

const normalizeClassification = (classification?: string): 'fast' | 'normal' | 'slow' => {
  const c = (classification || '').toLowerCase().trim();
  if (c === 'fast' || c === 'slow') return c;
  return 'normal';
};

const getClassificationColor = (classification: string, player: 'P0' | 'P1'): string => {
  const key = normalizeClassification(classification);
  return classificationColors[player][key];
};

const getClassificationRadius = (classification: string): number => {
  const key = normalizeClassification(classification);
  return classificationSizes[key];
};

const formatControlType = (controlType?: string) => {
  if (!controlType) return '';
  return controlType
    .split('_')
    .map(part => (part ? part[0].toUpperCase() + part.slice(1) : part))
    .join(' ');
};

const RallyTempoVisualization: React.FC<Props> = ({ data, videoRef, tags }) => {
  const [selectedRallyId, setSelectedRallyId] = useState<string | null>(null);
  const [showTempoControl, setShowTempoControl] = useState<boolean>(true);
  const [showClassification, setShowClassification] = useState<boolean>(false);
  const [lengthFilter, setLengthFilter] = useState<(typeof LENGTH_FILTERS)[number]['value']>('all');
  const [tempoFilter, setTempoFilter] = useState<(typeof TEMPO_FILTERS)[number]['value']>('all');
  const [effectFilter, setEffectFilter] = useState<(typeof EFFECTIVENESS_FILTERS)[number]['value']>('all');
  const [clutchFilter, setClutchFilter] = useState<(typeof CLUTCH_FILTERS)[number]['value']>('all');

  const filteredRallies = useMemo(() => {
    if (!data?.rallies) return [];
    return data.rallies.filter(rally => {
      const tag = tags?.[rally.rally_id];
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
  }, [data, tags, lengthFilter, tempoFilter, effectFilter, clutchFilter]);

  useEffect(() => {
    if (!filteredRallies.length) {
      setSelectedRallyId(null);
      return;
    }
    if (!selectedRallyId || !filteredRallies.some(r => r.rally_id === selectedRallyId)) {
      setSelectedRallyId(filteredRallies[0].rally_id);
    }
  }, [filteredRallies, selectedRallyId]);

  const selectedRally = filteredRallies.find(r => r.rally_id === selectedRallyId) || filteredRallies[0] || null;

  const plotData = useMemo(() => {
    if (!selectedRally) return null;

    const p0Points = selectedRally.p0_shots
      .filter(s => s.response_time_sec != null && s.response_time_sec > 0)
      .map(s => ({
        x: s.time_in_rally,
        y: s.response_time_sec!,
        stroke: s.stroke,
        tempo_control: s.tempo_control,
        control_type: s.control_type,
        classification: s.classification,
        effectiveness: s.effectiveness,
        time_sec: s.time_sec,
        frame_number: s.frame_number,
        player: 'P0' as const,
      }));

    const p1Points = selectedRally.p1_shots
      .filter(s => s.response_time_sec != null && s.response_time_sec > 0)
      .map(s => ({
        x: s.time_in_rally,
        y: s.response_time_sec!,
        stroke: s.stroke,
        tempo_control: s.tempo_control,
        control_type: s.control_type,
        classification: s.classification,
        effectiveness: s.effectiveness,
        time_sec: s.time_sec,
        frame_number: s.frame_number,
        player: 'P1' as const,
      }));

    // Calculate scales
    const allX = [...p0Points.map(p => p.x), ...p1Points.map(p => p.x)];
    const allY = [...p0Points.map(p => p.y), ...p1Points.map(p => p.y)];

    const xMin = Math.min(...allX, 0);
    const xMax = Math.max(...allX, 1);
    const yMin = 0;
    const yMax = Math.max(...allY, 1.5) * 1.1;

    return {
      p0Points,
      p1Points,
      xMin,
      xMax,
      yMin,
      yMax,
    };
  }, [selectedRally]);

  if (!data || !data.rallies || data.rallies.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#94a3b8' }}>
        No rally tempo data available. Load tempo_analysis_new.csv to generate visualization data.
      </div>
    );
  }

  if (!filteredRallies.length) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#94a3b8' }}>
        No rallies match the selected filters.
      </div>
    );
  }

  if (!plotData || plotData.p0Points.length === 0 && plotData.p1Points.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#94a3b8' }}>
        No valid tempo data for selected rally.
      </div>
    );
  }

  const { p0Points, p1Points, xMin, xMax, yMin, yMax } = plotData;

  const scaleX = (x: number) => {
    if (xMax <= xMin) return PAD;
    return PAD + ((x - xMin) / (xMax - xMin)) * (W - 2 * PAD);
  };

  const scaleY = (y: number) => {
    if (yMax <= yMin) return H - PAD;
    return H - PAD - ((y - yMin) / (yMax - yMin)) * (H - 2 * PAD);
  };

  // Generate line paths
  const p0Path = p0Points.length > 0
    ? `M ${p0Points.map(p => `${scaleX(p.x)},${scaleY(p.y)}`).join(' L ')}`
    : '';

  const p1Path = p1Points.length > 0
    ? `M ${p1Points.map(p => `${scaleX(p.x)},${scaleY(p.y)}`).join(' L ')}`
    : '';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Controls */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong>Rally Tempo Visualization</strong>
        <select
          value={selectedRallyId || ''}
          onChange={(e) => setSelectedRallyId(e.target.value || null)}
          style={{
            padding: '4px 8px',
            borderRadius: 6,
            border: '1px solid #2c2c34',
            background: '#0f0f15',
            color: '#e5e7eb',
          }}
        >
          {filteredRallies.map(r => (
            <option key={r.rally_id} value={r.rally_id}>
              Rally {r.rally_number} (Game {r.game_number}) - {r.rally_winner || 'Unknown'} - {r.total_shots} shots
            </option>
          ))}
        </select>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
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
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showTempoControl}
            onChange={(e) => {
              const checked = e.target.checked;
              setShowTempoControl(checked);
              if (checked) setShowClassification(false); // Make mutually exclusive
            }}
          />
          Color by Tempo Control
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showClassification}
            onChange={(e) => {
              const checked = e.target.checked;
              setShowClassification(checked);
              if (checked) setShowTempoControl(false); // Make mutually exclusive
            }}
          />
          Color by Classification
        </label>
        {selectedRally && (
          <div style={{ marginLeft: 'auto', fontSize: 12, color: '#94a3b8' }}>
            Winner: {selectedRally.rally_winner || 'Unknown'} | 
            P0: {p0Points.length} shots | 
            P1: {p1Points.length} shots
          </div>
        )}
      </div>

      {/* Chart */}
      <div style={{ border: '1px solid #2c2c34', borderRadius: 8, padding: 12, background: '#0f0f15' }}>
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ maxHeight: '500px' }}>
          {/* Grid lines */}
          {Array.from({ length: 6 }).map((_, i) => {
            const y = yMin + (i * (yMax - yMin) / 5);
            const yPos = scaleY(y);
            return (
              <g key={`grid-y-${i}`}>
                <line
                  x1={PAD}
                  y1={yPos}
                  x2={W - PAD}
                  y2={yPos}
                  stroke="#1f2937"
                  strokeDasharray="2,4"
                  opacity={0.5}
                />
                <text
                  x={PAD - 8}
                  y={yPos + 4}
                  fontSize={11}
                  fill="#94a3b8"
                  textAnchor="end"
                >
                  {y.toFixed(2)}s
                </text>
              </g>
            );
          })}

          {Array.from({ length: 6 }).map((_, i) => {
            const x = xMin + (i * (xMax - xMin) / 5);
            const xPos = scaleX(x);
            return (
              <g key={`grid-x-${i}`}>
                <line
                  x1={xPos}
                  y1={PAD}
                  x2={xPos}
                  y2={H - PAD}
                  stroke="#1f2937"
                  strokeDasharray="2,4"
                  opacity={0.5}
                />
                <text
                  x={xPos}
                  y={H - PAD + 16}
                  fontSize={11}
                  fill="#94a3b8"
                  textAnchor="middle"
                >
                  {x.toFixed(1)}s
                </text>
              </g>
            );
          })}

          {/* Axes */}
          <line
            x1={PAD}
            y1={H - PAD}
            x2={W - PAD}
            y2={H - PAD}
            stroke="#334155"
            strokeWidth={2}
          />
          <line
            x1={PAD}
            y1={PAD}
            x2={PAD}
            y2={H - PAD}
            stroke="#334155"
            strokeWidth={2}
          />

          {/* Axis labels */}
          <text
            x={W / 2}
            y={H - 8}
            fontSize={12}
            fill="#94a3b8"
            textAnchor="middle"
          >
            Time in Rally (seconds)
          </text>
          <text
            x={20}
            y={H / 2}
            fontSize={12}
            fill="#94a3b8"
            textAnchor="middle"
            transform={`rotate(-90, 20, ${H / 2})`}
          >
            Response Time (seconds)
          </text>

          {/* P0 Line */}
          {p0Path && (
            <path
              d={p0Path}
              fill="none"
              stroke="#3b82f6"
              strokeWidth={2.5}
              opacity={0.8}
            />
          )}

          {/* P1 Line */}
          {p1Path && (
            <path
              d={p1Path}
              fill="none"
              stroke="#ef4444"
              strokeWidth={2.5}
              opacity={0.8}
            />
          )}

          {/* P0 Points */}
          {p0Points.map((point, idx) => {
            const x = scaleX(point.x);
            const y = scaleY(point.y);
            let color = '#3b82f6'; // Default P0 color
            let radius = 5;
            const controlInfo = resolveTempoDominance(point.player, point.tempo_control);
            if (showClassification) {
              color = getClassificationColor(point.classification || 'normal', 'P0');
              radius = getClassificationRadius(point.classification || 'normal');
            } else if (showTempoControl) {
              color = getTempoColor(point.tempo_control || 'neutral', 'P0');
              radius = 6;
            }
            return (
              <g
                key={`p0-${idx}`}
                onClick={() => seek(videoRef, point.time_sec)}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  cx={x}
                  cy={y}
                  r={radius}
                  fill={color}
                  stroke="#0f172a"
                  strokeWidth={1.2}
                />
                <rect
                  x={x - (radius + 4)}
                  y={y - (radius + 4)}
                  width={(radius + 4) * 2}
                  height={(radius + 4) * 2}
                  fill="transparent"
                />
                <title>
                  {`P0 ${point.stroke}\n` +
                   `Response: ${point.y.toFixed(3)}s\n` +
                   `Control: ${controlInfo.label}${point.control_type ? ` (${formatControlType(point.control_type)})` : ''}\n` +
                   `Classification: ${point.classification || 'normal'}\n` +
                   `Effectiveness: ${point.effectiveness?.toFixed(0) || 'N/A'}%\n` +
                   `Time: ${point.time_sec.toFixed(2)}s`}
                </title>
              </g>
            );
          })}

          {/* P1 Points */}
          {p1Points.map((point, idx) => {
            const x = scaleX(point.x);
            const y = scaleY(point.y);
            let color = '#ef4444'; // Default P1 color
            let radius = 5;
            const controlInfo = resolveTempoDominance(point.player, point.tempo_control);
            if (showClassification) {
              color = getClassificationColor(point.classification || 'normal', 'P1');
              radius = getClassificationRadius(point.classification || 'normal');
            } else if (showTempoControl) {
              color = getTempoColor(point.tempo_control || 'neutral', 'P1');
              radius = 6;
            }
            const diamondSize = radius * 2;
            return (
              <g
                key={`p1-${idx}`}
                onClick={() => seek(videoRef, point.time_sec)}
                style={{ cursor: 'pointer' }}
              >
                {showClassification ? (
                  <rect
                    x={x - radius}
                    y={y - radius}
                    width={diamondSize}
                    height={diamondSize}
                    fill={color}
                    stroke="#0f172a"
                    strokeWidth={1.2}
                    transform={`rotate(45 ${x} ${y})`}
                  />
                ) : (
                  <circle
                    cx={x}
                    cy={y}
                    r={radius}
                    fill={color}
                    stroke="#0f172a"
                    strokeWidth={1.2}
                  />
                )}
                <rect
                  x={x - (radius + 4)}
                  y={y - (radius + 4)}
                  width={(radius + 4) * 2}
                  height={(radius + 4) * 2}
                  fill="transparent"
                />
                <title>
                  {`P1 ${point.stroke}\n` +
                   `Response: ${point.y.toFixed(3)}s\n` +
                   `Control: ${controlInfo.label}${point.control_type ? ` (${formatControlType(point.control_type)})` : ''}\n` +
                   `Classification: ${point.classification || 'normal'}\n` +
                   `Effectiveness: ${point.effectiveness?.toFixed(0) || 'N/A'}%\n` +
                   `Time: ${point.time_sec.toFixed(2)}s`}
                </title>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, fontSize: 12, color: '#94a3b8', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 3, background: '#3b82f6' }} />
          <span>P0 Line</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 20, height: 3, background: '#ef4444' }} />
          <span>P1 Line</span>
        </div>
        {showTempoControl && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#10b981', borderRadius: '50%' }} />
              <span>Player Dominant</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#f59e0b', borderRadius: '50%' }} />
              <span>Opponent Dominant</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#8b5cf6', borderRadius: '50%' }} />
              <span>Player Aggressive</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#3b82f6', borderRadius: '50%' }} />
              <span>Neutral</span>
            </div>
          </>
        )}
        {showClassification && (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#06b6d4', borderRadius: '50%' }} />
              <span>P0 Fast (circle)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#3b82f6', borderRadius: '50%' }} />
              <span>P0 Normal</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, background: '#1e40af', borderRadius: '50%' }} />
              <span>P0 Slow</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div
                style={{
                  width: 12,
                  height: 12,
                  background: '#f97316',
                  transform: 'rotate(45deg)',
                }}
              />
              <span>P1 Fast (diamond)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div
                style={{
                  width: 12,
                  height: 12,
                  background: '#ef4444',
                  transform: 'rotate(45deg)',
                }}
              />
              <span>P1 Normal</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div
                style={{
                  width: 12,
                  height: 12,
                  background: '#dc2626',
                  transform: 'rotate(45deg)',
                }}
              />
              <span>P1 Slow</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default RallyTempoVisualization;

