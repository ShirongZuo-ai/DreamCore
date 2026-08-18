export type ValidationSample = {
  review_id: string;
  sample_kind: 'candidate' | 'control';
  candidate_id: string;
  dataset_id: string;
  subject_id: string;
  recording_id: string;
  source_channel: string;
  timestamp: string;
  normalized_stage: string;
  agreement_class: string;
  confidence?: string;
  amplitude_uv?: string;
  polarity?: string;
  duration_s?: string;
  robust_deviation_z?: string;
  peak_to_peak_uv?: string;
  mean_absolute_derivative_uv_per_s?: string;
  local_rms_uv?: string;
};

export type ValidationRecording = {
  available: true;
  validation_version: string;
  contract_sha256: string;
  manual_review_status: 'pending' | 'in_progress';
  channels: Array<Record<string, string | number | null>>;
  agreement: Array<Record<string, string>>;
  stage_distribution: Array<Record<string, string>>;
  scorer_disagreement: Array<Record<string, string>>;
};

export type UnavailableValidationRecording = {
  available: false;
  validation_version: string;
  reason: string;
};

export type ReviewProgress = {
  candidate_reviewed: number;
  candidate_total: number;
  control_reviewed: number;
  control_total: number;
  label_counts: Record<string, number>;
  datasets: Record<string, { reviewed: number; total: number }>;
};

export type FocusResponse = {
  sample: ValidationSample;
  focus_start_s: number;
  focus_end_s: number;
  candidate_timestamp: number;
  eog_signals: Array<{
    signal_id: string;
    channel: string;
    sampling_rate_hz: number;
  }>;
  eeg_signals: Array<{
    signal_id: string;
    channel: string;
    sampling_rate_hz: number;
  }>;
  review: {
    review_id: string;
    review_label: string;
    notes: string;
  } | null;
};

export type FilteredValidationWindow = {
  session_id: string;
  channel: string;
  start_s: number;
  end_s: number;
  sampling_rate_hz: number;
  unit: string;
  timestamps: number[];
  samples: number[];
  provenance: 'derived';
};

type Envelope<T> = { eog_validation_api_version: 'v1'; data: T };

class EogValidationApi {
  constructor(private readonly prefix = '/api/eog-validation/v1') {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.prefix}${path}`, init);
    const payload = (await response.json()) as Envelope<T>;
    if (!response.ok)
      throw new Error(`EOG validation request failed: ${response.status}`);
    return payload.data;
  }

  recording(sessionId: string) {
    return this.request<ValidationRecording | UnavailableValidationRecording>(
      `/recording?session_id=${encodeURIComponent(sessionId)}`,
    );
  }

  samples(sessionId: string, kind: 'candidate' | 'control') {
    return this.request<ValidationSample[]>(
      `/samples?session_id=${encodeURIComponent(sessionId)}&kind=${kind}`,
    );
  }

  progress() {
    return this.request<ReviewProgress>('/progress');
  }

  focus(reviewId: string) {
    return this.request<FocusResponse>(
      `/focus?review_id=${encodeURIComponent(reviewId)}`,
    );
  }

  filteredWindow(
    sessionId: string,
    channel: string,
    startSeconds: number,
    durationSeconds: number,
  ) {
    return this.request<FilteredValidationWindow>(
      `/filtered-window?session_id=${encodeURIComponent(sessionId)}&channel=${encodeURIComponent(channel)}&start_s=${startSeconds}&duration_s=${durationSeconds}`,
    );
  }

  saveReview(reviewId: string, reviewLabel: string, notes: string) {
    return this.request<Record<string, unknown>>('/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        review_id: reviewId,
        review_label: reviewLabel,
        notes,
      }),
    });
  }
}

export const eogValidationApi = new EogValidationApi();
