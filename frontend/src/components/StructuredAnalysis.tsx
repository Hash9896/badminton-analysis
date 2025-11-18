import React, { useState } from 'react';

export type SAInstance = {
  start_frame: number;
  trigger_frame?: number | null;
  rally_id?: string | null;
  actor?: string | null;
  evidence_shots?: string | null;
};

export type SAJumpLinkGroup = {
  label: string;
  pattern_key: string;
  sub_section: string;
  instances: SAInstance[];
};

export type SASection = {
  section_id: string;
  section_name: string;
  summary: string;
  jump_links: SAJumpLinkGroup[];
};

type Props = {
  sections: SASection[];
  videoRef: React.RefObject<HTMLVideoElement>;
  fps: number;
};

export const StructuredAnalysis: React.FC<Props> = ({ sections, videoRef, fps }) => {
  const [actor, setActor] = useState<'P0'|'P1'>('P0');
  const onJump = (startFrame: number, triggerFrame?: number | null) => {
    const v = videoRef.current;
    if (!v) return;
    const startSec = Math.max(0, startFrame / (fps || 30) - 1);
    v.currentTime = startSec;
    v.play().catch(() => {});
    if (triggerFrame && Number.isFinite(triggerFrame)) {
      const pauseSec = Math.max(0, triggerFrame / (fps || 30));
      const delayMs = Math.max(0, (pauseSec - startSec) * 1000);
      window.setTimeout(() => {
        v.pause();
        window.setTimeout(() => {
          v.play().catch(() => {});
        }, 1000);
      }, delayMs);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <div style={{ fontSize: 12, opacity: 0.8, alignSelf: 'center' }}>View insights for:</div>
        <button onClick={() => setActor('P0')} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2c2c34', background: actor==='P0' ? '#1f2937' : '#0f0f15', color: '#e5e7eb' }}>P0 (You)</button>
        <button onClick={() => setActor('P1')} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #2c2c34', background: actor==='P1' ? '#1f2937' : '#0f0f15', color: '#e5e7eb' }}>P1</button>
      </div>
      {sections.map((sec) => (
        <div key={sec.section_id} style={{ marginBottom: 18 }}>
          <h2 style={{ margin: '6px 0 4px' }}>{sec.section_id}. {sec.section_name}</h2>
          {sec.summary && (
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.45, fontSize: 14, marginBottom: 8 }}>{sec.summary}</div>
          )}
          {sec.jump_links.map((group, gi) => {
            const instances = (group.instances || []).filter(inst => (inst.actor || '') === actor);
            if (!instances.length) return null;
            return (
              <div key={`${sec.section_id}-${gi}`} style={{ margin: '8px 0', padding: '8px', border: '1px solid #2c2c34', borderRadius: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontWeight: 700 }}>{group.label}</div>
                  <div style={{ opacity: 0.7, fontSize: 12 }}>{group.sub_section}</div>
                </div>
                <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {instances.map((inst, ii) => (
                    <div key={`${gi}-${ii}`}
                      onClick={() => onJump(inst.start_frame, inst.trigger_frame ?? undefined)}
                      style={{ padding: '0.3rem 0.55rem', background: '#eef2ff22', border: '1px solid #334155', borderRadius: 999, fontSize: 12, color: '#cbd5e1', cursor: 'pointer', userSelect: 'none' }}
                      title={`Start ${Math.max(0, inst.start_frame / (fps || 30) - 1).toFixed(2)}s${inst.trigger_frame ? `, pause @ ${(inst.trigger_frame/(fps||30)).toFixed(2)}s` : ''}`}>
                      [{inst.start_frame}]{inst.trigger_frame ? ` → [${inst.trigger_frame}]` : ''}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
};

export default StructuredAnalysis;


