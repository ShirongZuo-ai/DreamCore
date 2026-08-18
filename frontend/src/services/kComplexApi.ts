export type KComplexEvent = {
  event_id: string;
  dataset_id: string;
  subject_id: string;
  recording_id: string;
  channel: string;
  stage: string;
  n2_bout_id: string;
  ordinal_in_n2_bout: number;
  onset_s: number;
  negative_trough_s: number;
  negative_trough_amplitude: number;
  positive_peak_s: number | null;
  end_s: number;
  duration_s: number;
  score: number;
  confidence: 'low' | 'medium' | 'high';
  detector_version: string;
  config_hash: string;
  source_fingerprint: string;
  amplitude_unit: string;
  provenance: 'derived';
  event_type: 'k_complex_candidate';
  verification_method: 'morphology_b1';
  verification_probability: number;
  verification_status: 'accepted' | 'rejected';
  verification_accepted: boolean;
  verifier_version: string;
  verification_threshold: number;
  original_candidate_id: string;
  original_morphology_score: number;
  trough_s: number;
  cbramod_probability?: number;
  cbramod_status?: 'accepted' | 'rejected' | 'uncertain';
  cbramod_confidence?: 'low' | 'medium' | 'high';
  cbramod_verifier_version?: string;
};

export type KComplexBout = {
  bout_id: string;
  stage: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  raw_labels: string[];
  scorers: string[];
};

export type KComplexReview = {
  event_id: string;
  review_label: 'Looks right' | 'Wrong' | 'Uncertain';
  notes: string;
  reviewed_at: string;
};

export type ManualKComplexEvent = {
  manual_event_id: string;
  recording_id: string;
  channel: string;
  stage: 'N2';
  n2_bout_id: string;
  negative_trough_s: number;
  notes: string;
  created_at: string;
  provenance: 'manual';
  event_type: 'manual_k_complex_trough_candidate';
};

export type KComplexPayload = {
  session_id: string;
  detector_version: string;
  verifier_version: string;
  verification_method: 'morphology_b1';
  candidate_count: number;
  verified_count: number;
  rejected_count: number;
  config_hash: string;
  source_fingerprint: string;
  analysis: {
    recording_duration_s: number;
    primary_stage: 'N2';
    n2_duration_s: number;
    n2_bout_count: number;
    candidate_count: number;
    verified_count: number;
    rejected_count: number;
    event_count: number;
    events_per_hour_n2: number;
    n2_bouts_with_events: number;
    n2_bouts_with_at_least_two_events: number;
    primary_channel: string;
    primary_signal_id: string;
    focus_signals: Array<{
      signal_id: string;
      channel: string;
      canonical_role: string;
      sampling_rate_hz: number;
      unit: string;
    }>;
    focus_half_window_s: number;
    candidate_detector: string;
    verification_method: 'morphology_b1';
    verifier_version: string;
    verification_threshold: number;
    retrospective_only: true;
    causal_lead_time: null;
    cbramod?: {
      status: 'loading' | 'ready' | 'error' | 'not_computed';
      verifier_version?: string;
    };
  };
  events: KComplexEvent[];
  bouts: KComplexBout[];
  reviews: KComplexReview[];
  manual_events: ManualKComplexEvent[];
  review_progress: {
    reviewed: number;
    total: number;
    label_counts: Record<string, number>;
  };
};

export interface KComplexApi {
  get(sessionId: string, signal?: AbortSignal): Promise<KComplexPayload>;
  review(
    sessionId: string,
    eventId: string,
    reviewLabel: KComplexReview['review_label'],
    notes: string,
  ): Promise<KComplexReview>;
  markManual(
    sessionId: string,
    negativeTroughSeconds: number,
    notes: string,
  ): Promise<ManualKComplexEvent>;
}

export class HttpKComplexApi implements KComplexApi {
  constructor(private readonly baseUrl = '/api/analysis/v1') {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, init);
    const payload = (await response.json()) as
      { data: T } | { error: { message: string } };
    if (!response.ok || 'error' in payload) {
      throw new Error(
        'error' in payload ? payload.error.message : response.statusText,
      );
    }
    return payload.data;
  }

  get(sessionId: string, signal?: AbortSignal) {
    return this.request<KComplexPayload>(
      `/sessions/${encodeURIComponent(sessionId)}/k-complex`,
      { signal },
    );
  }

  review(
    sessionId: string,
    eventId: string,
    reviewLabel: KComplexReview['review_label'],
    notes: string,
  ) {
    return this.request<KComplexReview>(
      `/sessions/${encodeURIComponent(sessionId)}/k-complex/reviews`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_id: eventId,
          review_label: reviewLabel,
          notes,
        }),
      },
    );
  }

  markManual(sessionId: string, negativeTroughSeconds: number, notes: string) {
    return this.request<ManualKComplexEvent>(
      `/sessions/${encodeURIComponent(sessionId)}/k-complex/manual-events`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          negative_trough_s: negativeTroughSeconds,
          notes,
        }),
      },
    );
  }
}

export const kComplexApi = new HttpKComplexApi();
