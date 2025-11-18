import React, { useCallback, useMemo, useRef, useState } from 'react';

type Hit = {
  chunk_id: string;
  match_id: string;
  file_path: string;
  source_type?: string;
  rally_id?: string | null;
  text: string;
  score?: number;
};

type ChatResponse = {
  answer: string;
  hits: Hit[];
  model: string;
};

const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string) || 'http://localhost:8000';

export const ChatPanelV2: React.FC = () => {
  const [matchId, setMatchId] = useState<string>('Aikya/1');
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [history, setHistory] = useState<Array<{ q: string; a: string; hits: Hit[] }>>([]);

  const canAsk = useMemo(() => !!question.trim() && !!matchId.trim(), [question, matchId]);

  const indexMatch = useCallback(async () => {
    setError('');
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_URL}/index`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ match_id: matchId }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || 'Failed to index match');
      }
      // no-op on success
    } catch (e: any) {
      setError(e?.message || 'Failed to index');
    } finally {
      setLoading(false);
    }
  }, [matchId]);

  const ask = useCallback(async () => {
    if (!canAsk) return;
    setError('');
    try {
      setLoading(true);
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ match_id: matchId, message: question }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || 'Failed to chat');
      }
      const data = (await res.json()) as ChatResponse;
      setHistory(prev => [{ q: question, a: data.answer || '', hits: data.hits || [] }, ...prev]);
      setQuestion('');
    } catch (e: any) {
      setError(e?.message || 'Chat error');
    } finally {
      setLoading(false);
    }
  }, [question, matchId, canAsk]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <select
          value={matchId}
          onChange={(e) => setMatchId(e.target.value)}
          style={{ padding: '6px 8px', borderRadius: 8, background: '#0f0f15', color: '#e5e7eb', border: '1px solid #2c2c34' }}
          title="Active match context"
        >
          <option value="Aikya/1">Aikya/1</option>
          <option value="Ayush/2">Ayush/2</option>
          <option value="Ayush/3">Ayush/3</option>
          <option value="Siddhanth/4">Siddhanth/4</option>
        </select>
        <button onClick={indexMatch} disabled={loading}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #2c2c34', background: '#0f0f15', color: '#e5e7eb' }}>
          {loading ? 'Indexing...' : 'Index match'}
        </button>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about errors, winners, zones, rallies..."
          onKeyDown={(e) => { if (e.key === 'Enter') ask(); }}
          style={{ flex: 1, padding: '8px 10px', borderRadius: 8, background: '#0f0f15', color: '#e5e7eb', border: '1px solid #2c2c34' }}
        />
        <button onClick={ask} disabled={!canAsk || loading}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #2c2c34', background: canAsk ? '#18181f' : '#0f0f1533', color: '#e5e7eb' }}>
          {loading ? 'Asking...' : 'Ask'}
        </button>
      </div>
      {error && (
        <div style={{ color: '#ef4444', fontSize: 12 }}>{error}</div>
      )}
      <div style={{ display: 'grid', gap: 12 }}>
        {history.map((h, idx) => (
          <div key={idx} style={{ border: '1px solid #2c2c34', borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ padding: 10, background: '#0f0f15', borderBottom: '1px solid #2c2c34' }}>
              <div style={{ fontSize: 12, opacity: 0.8 }}>You</div>
              <div>{h.q}</div>
            </div>
            <div style={{ padding: 10, background: '#0b0b11' }}>
              <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 6 }}>Assistant</div>
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.45 }}>{h.a}</div>
              {h.hits && h.hits.length > 0 && (
                <div style={{ marginTop: 10, fontSize: 12 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>Sources</div>
                  <div style={{ display: 'grid', gap: 6 }}>
                    {h.hits.map((hit) => (
                      <div key={hit.chunk_id} style={{ padding: '6px 8px', background: '#11131a', border: '1px solid #2c2c34', borderRadius: 6 }}>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                          <span style={{ opacity: 0.8 }}>{hit.file_path}</span>
                          {hit.rally_id ? (<span style={{ opacity: 0.6 }}>rally: {hit.rally_id}</span>) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {history.length === 0 && (
          <div style={{ opacity: 0.7, fontSize: 14 }}>
            Start by indexing the match and asking: “Show P0 errors between rallies 10–20”, “Top zones where P1 scored winners”, “Summarize backhand errors”.
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatPanelV2;


