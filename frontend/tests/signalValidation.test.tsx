import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, vi } from 'vitest';

import { App } from '../src/app/App';

const summary = {
  validation_version: 'signal_validation_v1',
  contract_sha256: 'a'.repeat(64),
  alpha: {
    case_count: 48,
    frequency_error: {
      count: 45,
      mean: 0,
      median: 0,
      mae: 0.125,
      p90: 0.25,
      p95: 0.25,
    },
    positive_reliable_peak_detection_rate: 0.9,
    negative_false_reliable_peak_rate: 0,
    absolute_power_pearson_r: 0.98,
    stationary_stability: {
      relative_power_sd: {
        count: 27,
        mean: 0.01,
        median: 0.009,
        mae: 0.01,
        p90: 0.02,
        p95: 0.03,
      },
    },
  },
  eye_movement: {
    expert_events_evaluable: 846,
    dreamcore_candidate_count: 900,
    pooled_candidate_agreement_with_expert_rem_labels: {
      reference_events: 846,
      detector_events: 900,
      matched_events: 400,
      unmatched_detector_events: 500,
      missed_reference_events: 446,
      precision: 0.444,
      recall: 0.473,
      f1: 0.458,
    },
    timing_offset_from_expert_interval_midpoint_s: {
      count: 400,
      mean: 0.1,
      median: 0,
      mae: 0.2,
      p90: 0.4,
      p95: 0.5,
    },
    human_qc: { status: 'Human QC pending', review_count: 0 },
  },
  k_complex: {
    experts: {
      expert_1: {
        reference_events: 272,
        detector_events: 200,
        matched_events: 100,
        unmatched_detector_events: 100,
        missed_reference_events: 172,
        precision: 0.5,
        recall: 0.368,
        f1: 0.424,
      },
      expert_2: {
        reference_events: 64,
        detector_events: 90,
        matched_events: 40,
        unmatched_detector_events: 50,
        missed_reference_events: 24,
        precision: 0.444,
        recall: 0.625,
        f1: 0.52,
      },
    },
    inter_expert_agreement: {
      reference_events: 100,
      detector_events: 64,
      matched_events: 50,
      unmatched_detector_events: 14,
      missed_reference_events: 50,
      precision: 0.781,
      recall: 0.5,
      f1: 0.61,
    },
    trough_validation_status: 'No expert trough landmark exists.',
  },
  cross_talk: {
    case_count: 63,
    contamination_matrix: {
      k_complex_plus_eog: {
        true_alpha: false,
        true_k_complex: true,
        true_eog: true,
        mean_reliable_alpha_peak_rate: 0,
        k_complex_detected_case_rate: 1,
        eog_candidate_detected_case_rate: 1,
        mean_false_k_complex_per_hour: 0,
        mean_false_eye_candidates_per_hour: 0,
      },
      noise_only: {
        true_alpha: false,
        true_k_complex: false,
        true_eog: false,
        mean_reliable_alpha_peak_rate: 0,
        k_complex_detected_case_rate: 0,
        eog_candidate_detected_case_rate: 1,
        mean_false_k_complex_per_hour: 0,
        mean_false_eye_candidates_per_hour: 130,
      },
    },
  },
};

afterEach(() => vi.restoreAllMocks());

describe('Signal Validation dashboard', () => {
  it('shows interpretable metrics and pending labels without fabricated zeroes', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ data: summary }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    render(
      <MemoryRouter initialEntries={['/validation']}>
        <App />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('heading', {
        name: 'Signal Validation',
        level: 1,
      }),
    ).toBeVisible();
    expect(screen.getByText('Human QC pending')).toBeVisible();
    expect(screen.getByText('No expert trough landmark exists.')).toBeVisible();
    expect(screen.getByText('130.0')).toBeVisible();
    expect(screen.getAllByText('NA').length).toBeGreaterThan(0);
    expect(screen.queryByText(/signal score/i)).not.toBeInTheDocument();
  });

  it('shows pending when the local benchmark result does not exist', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { message: 'Signal Validation V1 has not been run locally' },
        }),
        { status: 404, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(
      <MemoryRouter initialEntries={['/validation']}>
        <App />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(/validation results are pending/i),
    ).toBeVisible();
    expect(await screen.findByText(/has not been run locally/i)).toBeVisible();
  });
});
