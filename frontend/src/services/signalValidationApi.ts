export interface MetricSummary {
  count: number;
  mean: number | null;
  median: number | null;
  mae: number | null;
  p90: number | null;
  p95: number | null;
}

export interface DetectionMetrics {
  reference_events: number;
  detector_events: number;
  matched_events: number;
  unmatched_detector_events: number;
  missed_reference_events: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface SignalValidationSummary {
  validation_version: string;
  contract_sha256: string;
  alpha: {
    case_count: number;
    frequency_error: MetricSummary;
    positive_reliable_peak_detection_rate: number | null;
    negative_false_reliable_peak_rate: number | null;
    absolute_power_pearson_r: number | null;
    stationary_stability: { relative_power_sd: MetricSummary };
  };
  eye_movement: {
    expert_events_evaluable: number;
    dreamcore_candidate_count: number;
    pooled_candidate_agreement_with_expert_rem_labels: DetectionMetrics;
    timing_offset_from_expert_interval_midpoint_s: MetricSummary;
    human_qc: { status: string; review_count: number };
  };
  k_complex: {
    experts: {
      expert_1: DetectionMetrics;
      expert_2: DetectionMetrics;
    };
    inter_expert_agreement: DetectionMetrics;
    trough_validation_status: string;
  };
  cross_talk: {
    case_count: number;
    contamination_matrix: Record<
      string,
      {
        true_alpha: boolean;
        true_k_complex: boolean;
        true_eog: boolean;
        mean_reliable_alpha_peak_rate: number;
        k_complex_detected_case_rate: number;
        eog_candidate_detected_case_rate: number;
        mean_false_k_complex_per_hour: number;
        mean_false_eye_candidates_per_hour: number;
      }
    >;
  };
}

export class SignalValidationApi {
  constructor(private readonly path = '/api/validation/v1/summary') {}

  async getSummary(signal?: AbortSignal): Promise<SignalValidationSummary> {
    const response = await fetch(this.path, { signal });
    const payload = (await response.json()) as {
      data?: SignalValidationSummary;
      error?: { message?: string };
    };
    if (!response.ok || !payload.data) {
      throw new Error(
        payload.error?.message ??
          `Validation request failed (${response.status})`,
      );
    }
    return payload.data;
  }
}
