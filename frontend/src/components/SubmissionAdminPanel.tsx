import React, { useCallback, useMemo, useState } from 'react';
import { fetchSubmissions, updateSubmission } from '../api/submissions';
import type { Submission, SubmissionStatus } from '../types/submission';

const statusOptions: SubmissionStatus[] = ['pending', 'processing', 'ready'];

export const SubmissionAdminPanel: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Partial<Submission>>>({});
  const [updating, setUpdating] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSubmissions({ status: 'all' });
      setSubmissions(data);
    } catch (err) {
      setError('Unable to fetch submissions.');
    } finally {
      setLoading(false);
    }
  }, []);

  const toggleVisible = () => {
    const next = !visible;
    setVisible(next);
    if (next && submissions.length === 0) {
      void refresh();
    }
  };

  const draftsMerged = useMemo(() => {
    const result: Record<string, Submission> = {};
    for (const entry of submissions) {
      result[entry.id] = { ...entry, ...(drafts[entry.id] || {}) };
    }
    return result;
  }, [submissions, drafts]);

  const handleDraftChange = (id: string, field: keyof Submission, value: string) => {
    setDrafts(prev => ({
      ...prev,
      [id]: {
        ...(prev[id] || {}),
        [field]: value,
      },
    }));
  };

  const handleUpdate = async (id: string) => {
    const draft = draftsMerged[id];
    setUpdating(prev => ({ ...prev, [id]: true }));
    try {
      await updateSubmission(id, {
        status: draft.status,
        folder: draft.folder ?? null,
        match_label: draft.match_label ?? null,
        report_url: draft.report_url ?? null,
      });
      await refresh();
      setDrafts(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch (err) {
      setError('Update failed. Please try again.');
    } finally {
      setUpdating(prev => ({ ...prev, [id]: false }));
    }
  };

  if (!visible) {
    return (
      <div className="ops-panel">
        <button onClick={toggleVisible}>
          Show ops queue
        </button>
      </div>
    );
  }

  return (
    <div className="ops-panel">
      <div className="ops-panel__header">
        <div>
          <strong>Ops queue</strong>
          <span>Manage submissions locally (matches + technical).</span>
        </div>
        <div className="ops-panel__actions">
          <button onClick={refresh} disabled={loading}>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
          <button onClick={toggleVisible}>Hide</button>
        </div>
      </div>
      {error && <div className="ops-panel__error">{error}</div>}
      {submissions.length === 0 && !loading ? (
        <div className="ops-panel__empty">No submissions yet.</div>
      ) : (
        <div className="ops-table">
          <div className="ops-table__header">
            <span>Player</span>
            <span>Type</span>
            <span>Status</span>
            <span>Folder</span>
            <span>Label</span>
            <span>Actions</span>
          </div>
          {submissions.map(entry => {
            const merged = draftsMerged[entry.id];
            return (
              <div key={entry.id} className="ops-table__row">
                <div className="ops-table__cell">
                  <div className="ops-table__player">{entry.player}</div>
                  <div className="ops-table__meta">{entry.video_url}</div>
                  {entry.notes && <div className="ops-table__meta">Notes: {entry.notes}</div>}
                </div>
                <div className="ops-table__cell">{entry.type}</div>
                <div className="ops-table__cell">
                  <select
                    value={merged.status}
                    onChange={(e) => handleDraftChange(entry.id, 'status', e.target.value)}
                  >
                    {statusOptions.map(opt => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="ops-table__cell">
                  <input
                    type="text"
                    value={merged.folder || ''}
                    onChange={(e) => handleDraftChange(entry.id, 'folder', e.target.value)}
                    placeholder="e.g. Ayush/3"
                  />
                </div>
                <div className="ops-table__cell">
                  <input
                    type="text"
                    value={merged.match_label || ''}
                    onChange={(e) => handleDraftChange(entry.id, 'match_label', e.target.value)}
                    placeholder="Match label"
                  />
                  <input
                    type="text"
                    value={merged.report_url || ''}
                    onChange={(e) => handleDraftChange(entry.id, 'report_url', e.target.value)}
                    placeholder="Optional report link"
                    style={{ marginTop: 6 }}
                  />
                </div>
                <div className="ops-table__cell ops-table__cell--actions">
                  <button
                    onClick={() => handleUpdate(entry.id)}
                    disabled={updating[entry.id]}
                  >
                    {updating[entry.id] ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SubmissionAdminPanel;

