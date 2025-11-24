import type { Submission, SubmissionType, SubmissionStatus } from '../types/submission';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string) || 'http://localhost:8000';

function buildQuery(params: Record<string, string | undefined>): string {
  const query = Object.entries(params)
    .filter(([, value]) => value && value.length > 0)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value!)}`)
    .join('&');
  return query ? `?${query}` : '';
}

export async function createSubmission(payload: {
  player: string;
  video_url: string;
  type: SubmissionType;
  notes?: string;
}): Promise<Submission> {
  const res = await fetch(`${BACKEND_URL}/submissions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to submit video (${res.status})`);
  }
  return res.json();
}

export async function fetchSubmissions(params: {
  player?: string;
  type?: SubmissionType;
  status?: SubmissionStatus | 'all';
}): Promise<Submission[]> {
  const query = buildQuery({
    player: params.player,
    type: params.type,
    status: params.status && params.status !== 'all' ? params.status : undefined,
  });
  const res = await fetch(`${BACKEND_URL}/submissions${query}`);
  if (!res.ok) {
    throw new Error(`Failed to load submissions (${res.status})`);
  }
  return res.json();
}

export async function updateSubmission(
  id: string,
  payload: {
    status?: SubmissionStatus;
    report_url?: string | null;
    folder?: string | null;
    match_label?: string | null;
  }
): Promise<Submission> {
  const res = await fetch(`${BACKEND_URL}/submissions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to update submission (${res.status})`);
  }
  return res.json();
}

