export type SubmissionType = 'match' | 'technical';

export type SubmissionStatus = 'pending' | 'processing' | 'ready';

export type Submission = {
  id: string;
  player: string;
  video_url: string;
  type: SubmissionType;
  notes?: string | null;
  status: SubmissionStatus;
  created_at: string;
  updated_at: string;
  report_url?: string | null;
  folder?: string | null;
  match_label?: string | null;
};

