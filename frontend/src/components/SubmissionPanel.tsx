import React, { useCallback, useMemo, useState } from 'react';
import { createSubmission, fetchSubmissions } from '../api/submissions';
import type { Submission, SubmissionStatus, SubmissionType } from '../types/submission';

type Props = {
  mode: SubmissionType;
  onOpenSubmission?: (submission: Submission) => void;
  loadingSubmissionId?: string | null;
};

const statusLabel: Record<SubmissionStatus, string> = {
  pending: 'Pending',
  processing: 'In progress',
  ready: 'Ready',
};

export const SubmissionPanel: React.FC<Props> = ({ mode, onOpenSubmission, loadingSubmissionId }) => {
  const [playerName, setPlayerName] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [notes, setNotes] = useState('');
  const [submitStatus, setSubmitStatus] = useState<string | null>(null);
  const [lookupName, setLookupName] = useState('');
  const [loadingList, setLoadingList] = useState(false);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [listFetched, setListFetched] = useState(false);

  const readySubmissions = useMemo(() => submissions.filter(s => s.status === 'ready'), [submissions]);
  const pendingSubmissions = useMemo(() => submissions.filter(s => s.status !== 'ready'), [submissions]);

  const canSubmit = playerName.trim().length > 0 && videoUrl.trim().length > 4;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    try {
      setSubmitStatus('Submitting...');
      await createSubmission({
        player: playerName.trim(),
        video_url: videoUrl.trim(),
        type: mode,
        notes: notes.trim() || undefined,
      });
      setSubmitStatus('Submission received! We will notify you when your report is ready.');
      setPlayerName('');
      setVideoUrl('');
      setNotes('');
    } catch (error) {
      setSubmitStatus('Something went wrong. Please try again.');
    }
  };

  const refreshList = useCallback(async () => {
    if (!lookupName.trim()) {
      setListError('Please enter your name to view submissions.');
      return;
    }
    setListError(null);
    setLoadingList(true);
    try {
      const data = await fetchSubmissions({ player: lookupName.trim(), type: mode, status: 'all' });
      setSubmissions(data);
      setListFetched(true);
    } catch (error) {
      setListError('Unable to load submissions. Please try again.');
      setListFetched(false);
    } finally {
      setLoadingList(false);
    }
  }, [lookupName, mode]);

  const title = mode === 'match' ? 'Submit Match' : 'Submit Training / Technical Session';

  return (
    <div className="submission-panel">
      <div className="submission-card">
        <h3>{title}</h3>
        <p className="submission-description">
          Share a video link and our team will review and upload the full report for you. You&apos;ll be able to access it below once it&apos;s ready.
        </p>
        <form onSubmit={handleSubmit} className="submission-form">
          <label>
            Your name
            <input
              type="text"
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              placeholder="e.g. Ayush"
              required
            />
          </label>
          <label>
            {mode === 'match' ? 'Match video link' : 'Training session link'}
            <input
              type="url"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              placeholder="https://youtube.com/..."
              required
            />
          </label>
          <label>
            Notes (optional)
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add any context or focus areas"
            />
          </label>
          <button type="submit" disabled={!canSubmit}>
            Submit for Review
          </button>
        </form>
        {submitStatus && <p className="submission-status">{submitStatus}</p>}
      </div>

      <div className="submission-card">
        <h3>View your submissions</h3>
        <p className="submission-description">
          Enter your name to see the status of all {mode} uploads you&apos;ve shared with us.
        </p>
        <div className="submission-lookup">
          <input
            type="text"
            value={lookupName}
            onChange={(e) => setLookupName(e.target.value)}
            placeholder="Your name"
          />
          <button type="button" onClick={refreshList} disabled={loadingList}>
            {loadingList ? 'Loading...' : 'Check status'}
          </button>
        </div>
        {listError && <p className="submission-error">{listError}</p>}
        {(submissions.length > 0 || listFetched) && (
          <div className="submission-list">
            {pendingSubmissions.length > 0 && (
              <div className="submission-group">
                <h4>In progress</h4>
                {pendingSubmissions.map((entry) => (
                  <SubmissionRow
                    key={entry.id}
                    submission={entry}
                    onOpen={onOpenSubmission}
                    isLoading={loadingSubmissionId === entry.id}
                  />
                ))}
              </div>
            )}
            {readySubmissions.length > 0 && (
              <div className="submission-group">
                <h4>Ready to view</h4>
                {readySubmissions.map((entry) => (
                  <SubmissionRow
                    key={entry.id}
                    submission={entry}
                    onOpen={onOpenSubmission}
                    isLoading={loadingSubmissionId === entry.id}
                  />
                ))}
              </div>
            )}
            {pendingSubmissions.length === 0 && readySubmissions.length === 0 && (
              <p>No submissions found for this name.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const SubmissionRow: React.FC<{
  submission: Submission;
  onOpen?: (submission: Submission) => void;
  isLoading?: boolean;
}> = ({ submission, onOpen, isLoading }) => {
  return (
    <div className="submission-row">
      <div>
        <div className="submission-row-title">{submission.match_label || submission.video_url}</div>
        <div className="submission-row-meta">
          <span>{statusLabel[submission.status]}</span>
          <span>{new Date(submission.created_at).toLocaleString()}</span>
        </div>
        {submission.notes && <p className="submission-notes">{submission.notes}</p>}
      </div>
      {submission.status === 'ready' && (
        <>
          {onOpen && submission.folder ? (
            <button
              type="button"
              className="submission-link"
              onClick={() => onOpen(submission)}
              disabled={isLoading}
            >
              {isLoading ? 'Loading…' : 'View report'}
            </button>
          ) : submission.report_url ? (
            <a
              href={submission.report_url}
              className="submission-link"
              target="_blank"
              rel="noopener noreferrer"
            >
              View report
            </a>
          ) : null}
        </>
      )}
    </div>
  );
};

