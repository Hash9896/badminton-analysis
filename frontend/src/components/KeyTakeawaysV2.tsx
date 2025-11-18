import React, { useEffect, useState } from 'react';
import { parseFrameAnchor, formatMs, type ParsedAnchor } from '../utils/timecode';

export type V2Anchor = {
  type: 'frame_range' | 'rally_id' | 'pair';
  value: string;
};

export type V2Item = {
  heading: string;
  text: string;
  anchors: V2Anchor[];
};

export type V2Section = {
  title: string;
  items: V2Item[];
};

type Props = {
  sections: V2Section[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
  fps: number;
};

const seek = (videoRef: React.RefObject<HTMLVideoElement | null>, sec: number) => {
  const v = videoRef.current;
  if (!v) return;
  v.currentTime = sec;
  v.play().catch(() => {});
};

export const KeyTakeawaysV2: React.FC<Props> = ({ sections, videoRef, fps }) => {
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});

  useEffect(() => {
    // Default collapse all sections on mount/change
    const init: Record<number, boolean> = {};
    sections.forEach((_, idx) => { init[idx] = true; });
    setCollapsed(init);
  }, [sections]);

  return (
    <div>
      {sections.map((section, sIdx) => {
        const isCollapsed = !!collapsed[sIdx];
        return (
          <div key={`v2-sec-${sIdx}`} style={{ marginTop: '0.75rem' }}>
            <div
              onClick={() => setCollapsed(prev => ({ ...prev, [sIdx]: !prev[sIdx] }))}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
            >
              <div style={{ fontWeight: 700, marginBottom: 8 }}>{section.title}</div>
              <span style={{ opacity: 0.7 }}>{isCollapsed ? '▼' : '▲'}</span>
            </div>
            {!isCollapsed && (
              <ol style={{ paddingLeft: 18, lineHeight: 1.5 }}>
                {section.items.map((it, iIdx) => {
                  const videoDur = videoRef.current?.duration ?? undefined;
                  const frameAnchors: string[] = Array.isArray(it.anchors) ? it.anchors.map(a => String(a?.value || '').trim()).filter(Boolean) : [];
                  const parsed: ParsedAnchor[] = frameAnchors
                    .map(a => parseFrameAnchor(a, fps, videoDur))
                    .filter((x): x is ParsedAnchor => !!x);
                  const show = parsed.slice(0, 5);
                  const remaining = parsed.length - show.length;
                  return (
                    <li key={`v2-item-${sIdx}-${iIdx}`} style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 600 }}>{it.heading}</div>
                      <div style={{ margin: '4px 0 6px 0' }}>{it.text}</div>
                      {show.length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                          {show.map((p, i) => (
                            <div
                              key={`v2-chip-${sIdx}-${iIdx}-${i}`}
                              onClick={() => seek(videoRef, p.startSec)}
                              title={p.tooltip + (p.endSec ? ` (${formatMs(p.startSec*1000)} - ${formatMs(p.endSec*1000)})` : '')}
                              style={{ padding: '0.35rem 0.6rem', background: '#eef2ff', border: '1px solid #c7d2fe', borderRadius: 999, fontSize: 12, color: '#1e40af', cursor: 'pointer', userSelect: 'none' }}
                            >
                              {p.label}
                            </div>
                          ))}
                          {remaining > 0 && (
                            <div style={{ padding: '0.35rem 0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: 999, fontSize: 12, color: '#cbd5e1' }}
                              title={`+${remaining} more anchors`}>
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
      })}
    </div>
  );
};

export default KeyTakeawaysV2;


