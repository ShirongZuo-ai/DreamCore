import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { RealEEGWaveformPanel } from '../src/components/eeg/EEGWaveformPanel';
import { KComplexPanel } from '../src/components/insights/KComplexPanel';
import type {
  KComplexApi,
  KComplexEvent,
  KComplexPayload,
} from '../src/services/kComplexApi';
import type { ReplaySignalWindow } from '../src/services/replaySource';

const first: KComplexEvent = {
  event_id: 'kc-first',
  dataset_id: 'hmc',
  subject_id: 'SN001',
  recording_id: 'SN001',
  channel: 'EEG F4-M1',
  stage: 'N2',
  n2_bout_id: 'N2-0004',
  ordinal_in_n2_bout: 1,
  onset_s: 2537.9,
  negative_trough_s: 2538.62,
  negative_trough_amplitude: -92.5,
  positive_peak_s: 2539.1,
  end_s: 2539.8,
  duration_s: 1.9,
  score: 0.82,
  confidence: 'high',
  detector_version: 'k_complex_v0',
  config_hash: 'config',
  source_fingerprint: 'source',
  amplitude_unit: 'uV',
  provenance: 'derived',
  event_type: 'k_complex_candidate',
  verification_method: 'morphology_b1',
  verification_probability: 0.91,
  verification_status: 'accepted',
  verification_accepted: true,
  verifier_version: 'k-complex-morphology-b1-v1',
  verification_threshold: 0.5,
  original_candidate_id: 'kc-first',
  original_morphology_score: 0.82,
  trough_s: 2538.62,
  cbramod_probability: 0.91,
  cbramod_status: 'accepted',
  cbramod_confidence: 'high',
  cbramod_verifier_version: 'cbramod-kc-linear-v1',
};
const second = {
  ...first,
  event_id: 'kc-second',
  ordinal_in_n2_bout: 2,
  negative_trough_s: 2563.14,
} satisfies KComplexEvent;

const payload: KComplexPayload = {
  session_id: 'SN001',
  detector_version: 'k_complex_v0',
  verifier_version: 'k-complex-morphology-b1-v1',
  verification_method: 'morphology_b1',
  candidate_count: 2,
  verified_count: 2,
  rejected_count: 0,
  config_hash: 'config',
  source_fingerprint: 'source',
  analysis: {
    recording_duration_s: 25_650,
    primary_stage: 'N2',
    n2_duration_s: 12_900,
    n2_bout_count: 1,
    candidate_count: 2,
    verified_count: 2,
    rejected_count: 0,
    event_count: 2,
    events_per_hour_n2: 0.56,
    n2_bouts_with_events: 1,
    n2_bouts_with_at_least_two_events: 1,
    primary_channel: 'EEG F4-M1',
    primary_signal_id: 'eeg-1',
    focus_signals: [
      {
        signal_id: 'eeg-1',
        channel: 'EEG F4-M1',
        canonical_role: 'EEG_FRONTAL',
        sampling_rate_hz: 256,
        unit: 'uV',
      },
    ],
    focus_half_window_s: 5,
    candidate_detector: 'k_complex_v0',
    verification_method: 'morphology_b1',
    verifier_version: 'k-complex-morphology-b1-v1',
    verification_threshold: 0.5,
    retrospective_only: true,
    causal_lead_time: null,
    cbramod: { status: 'ready', verifier_version: 'cbramod-kc-linear-v1' },
  },
  events: [first, second],
  bouts: [
    {
      bout_id: 'N2-0004',
      stage: 'N2',
      start_s: 2520,
      end_s: 2580,
      duration_s: 60,
      raw_labels: ['N2'],
      scorers: ['official'],
    },
  ],
  reviews: [],
  manual_events: [],
  review_progress: { reviewed: 0, total: 2, label_counts: {} },
};

function api(): KComplexApi {
  return {
    get: vi.fn().mockResolvedValue(payload),
    review: vi.fn().mockResolvedValue({
      event_id: first.event_id,
      review_label: 'Looks right',
      notes: '',
      reviewed_at: '2026-08-14T00:00:00Z',
    }),
    markManual: vi.fn().mockResolvedValue({}),
  } as unknown as KComplexApi;
}

it('makes first/second events and previous/next navigation directly inspectable', () => {
  const onSelect = vi.fn();
  render(
    <KComplexPanel
      sessionId="SN001"
      payload={payload}
      selectedEvent={first}
      currentTime={first.negative_trough_s}
      api={api()}
      onSelect={onSelect}
      onRefresh={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  expect(screen.getByText('First K-Complex')).toBeVisible();
  expect(screen.getByText('Second K-Complex')).toBeVisible();
  expect(screen.getByText('Reviewed 0 / 2')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: /Next KC/i }));
  expect(onSelect).toHaveBeenCalledWith(second);
  fireEvent.click(screen.getByRole('button', { name: /Jump to event/i }));
  expect(onSelect).toHaveBeenCalledWith(first);
});

it('uses morphology B1 by default, keeps CBraMod advanced, and preserves the trough', () => {
  render(
    <KComplexPanel
      sessionId="SN001"
      payload={payload}
      selectedEvent={first}
      currentTime={first.negative_trough_s}
      api={api()}
      onSelect={vi.fn()}
      onRefresh={vi.fn().mockResolvedValue(undefined)}
    />,
  );
  expect(screen.getByText('2 verified')).toBeVisible();
  expect(screen.getByText(/Verified by morphology verifier/)).toBeVisible();
  expect(screen.queryByText('CBraMod verification')).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText('CBraMod comparison'));
  expect(screen.getByText('CBraMod verification')).toBeVisible();
  expect(screen.getByText('0.910 · accepted')).toBeVisible();
  expect(screen.getAllByText('00:42:18.620')).toHaveLength(2);
});

it('keeps morphology-rejected V0 candidates inspectable without calling them false', () => {
  const rejected = {
    ...second,
    event_id: 'kc-rejected',
    original_candidate_id: 'kc-rejected',
    verification_probability: 0.12,
    verification_status: 'rejected',
    verification_accepted: false,
  } satisfies KComplexEvent;
  const withRejected = {
    ...payload,
    events: [first, rejected],
    verified_count: 1,
    rejected_count: 1,
    analysis: {
      ...payload.analysis,
      verified_count: 1,
      rejected_count: 1,
    },
  };
  render(
    <KComplexPanel
      sessionId="SN001"
      payload={withRejected}
      selectedEvent={rejected}
      currentTime={rejected.negative_trough_s}
      api={api()}
      onSelect={vi.fn()}
      onRefresh={vi.fn().mockResolvedValue(undefined)}
    />,
  );
  expect(screen.queryByText(/Rejected by morphology verifier/)).toBeVisible();
  fireEvent.click(screen.getByLabelText('Show rejected V0 candidates'));
  expect(screen.getByText('Second K-Complex')).toBeVisible();
  expect(screen.queryByText(/false KC/i)).not.toBeInTheDocument();
});

it('renders a bounded focused EEG window and makes its KC marker navigable', () => {
  const onMarker = vi.fn();
  const window: ReplaySignalWindow = {
    signal: {
      id: 'eeg-1',
      modality: 'eeg',
      channel_name: 'EEG F4-M1',
      original_channel_name: 'EEG F4-M1',
      canonical_role: 'EEG_FRONTAL',
      unit: 'uV',
      sampling_rate_hz: 2,
      source: 'raw',
      available: true,
    },
    startSeconds: 5,
    durationSeconds: 10,
    timestamps: [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10],
    samples: [0, 1, 2, 1, 0, -2, -8, -2, 0, 2, 0],
  };
  render(
    <RealEEGWaveformPanel
      windows={[window]}
      maxDisplayPoints={100}
      replayCursorSeconds={8}
      interventionMarkers={[]}
      kComplexMarkers={[
        {
          id: 'kc-first',
          timestamp: 8,
          label: 'KC',
          color: '#fff',
          provenance: 'derived',
        },
      ]}
      focused
      onKComplexMarkerClick={onMarker}
    />,
  );

  const plot = screen.getByTestId('real-eeg-uplot');
  expect(plot).not.toHaveAttribute('data-reveal-until-timestamp');
  fireEvent.click(screen.getByRole('button', { name: 'KC at 8.00 seconds' }));
  expect(onMarker).toHaveBeenCalledWith(
    expect.objectContaining({ id: 'kc-first', timestamp: 8 }),
  );
});
