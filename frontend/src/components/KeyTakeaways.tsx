import React, { useState } from 'react';
import { parseFrameAnchor, formatMs, type ParsedAnchor } from '../utils/timecode';

export type Observation = {
  id: string;
  section: 'mandatory' | 'worked' | 'didnt_work' | 'could_be_better';
  text: string;
  frameAnchors: string[];
};

type Props = {
  items: Observation[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
  fps: number;
};

export const KeyTakeaways: React.FC<Props> = ({ items, videoRef, fps }) => {
  type SectionKey = 'mandatory' | 'worked' | 'didnt_work' | 'could_be_better';
  const grouped: Record<SectionKey, Observation[]> = {
    mandatory: [],
    worked: [],
    didnt_work: [],
    could_be_better: [],
  };
  for (const it of items) {
    if (!grouped[it.section]) grouped[it.section] = [] as Observation[];
    grouped[it.section].push(it);
  }

  const [collapsed, setCollapsed] = useState<Record<SectionKey, boolean>>({
    mandatory: true,
    worked: true,
    didnt_work: true,
    could_be_better: true,
  });

  const seek = (sec: number) => {
    const v = videoRef.current;
    if (!v) return;
    try {
      v.currentTime = sec;
      v.play().catch(() => {});
    } catch {}
  };

  const renderSection = (title: string, sectionKey: SectionKey) => {
    const arr = grouped[sectionKey] || [];
    if (arr.length === 0) return null;
    const isCollapsed = collapsed[sectionKey];
    return (
      <div style={{ marginTop: '0.75rem' }}>
        <div
          onClick={() => setCollapsed(prev => ({ ...prev, [sectionKey]: !prev[sectionKey] }))}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
        >
          <div style={{ fontWeight: 700, marginBottom: 8 }}>{title}</div>
          <span style={{ opacity: 0.7 }}>{isCollapsed ? '▼' : '▲'}</span>
        </div>
        {!isCollapsed && (
          <ol style={{ paddingLeft: 18, lineHeight: 1.5 }}>
            {arr.map(obs => {
              const videoDur = videoRef.current?.duration ?? undefined;
              const parsed: ParsedAnchor[] = (obs.frameAnchors || [])
                .map(a => parseFrameAnchor(a, fps, videoDur))
                .filter((x): x is ParsedAnchor => !!x);
              const show = parsed.slice(0, 5);
              const remaining = parsed.length - show.length;
              return (
                <li key={obs.id} style={{ marginBottom: 8 }}>
                  <div style={{ marginBottom: 6 }}>{obs.text}</div>
                  {show.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {show.map((p, i) => (
                        <div
                          key={`${obs.id}-chip-${i}`}
                          onClick={() => seek(p.startSec)}
                          title={p.tooltip + (p.endSec ? ` (${formatMs(p.startSec*1000)} - ${formatMs(p.endSec*1000)})` : '')}
                          style={{ padding: '0.35rem 0.6rem', background: '#eef2ff', border: '1px solid #c7d2fe', borderRadius: 999, fontSize: 12, color: '#1e40af', cursor: 'pointer', userSelect: 'none' }}
                        >
                          {p.label}
                        </div>
                      ))}
                      {remaining > 0 && (
                        <div style={{ padding: '0.35rem 0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: 999, fontSize: 12, color: '#cbd5e1' }}
                          title={`+${remaining} more anchors`}
                        >
                          +{remaining} more
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    );
  };

  return (
    <div>
      {renderSection('Mandatory observations', 'mandatory')}
      {renderSection('Things that worked', 'worked')}
      {renderSection("Things that absolutely didn't work", 'didnt_work')}
      {renderSection('Things that could be better', 'could_be_better')}
    </div>
  );
};

export default KeyTakeaways;


