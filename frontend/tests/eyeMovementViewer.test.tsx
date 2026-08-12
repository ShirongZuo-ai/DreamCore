import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AlphaSessionViewer } from '../src/components/alpha/AlphaSessionViewer';
import { parseFixtureManifest } from '../src/mocks/sessionFixtures';
import type { ReplaySource } from '../src/services/replaySource';
import type {
  AnnotationWindowResponse,
  DerivedWindowResponse,
  EyeMovementEventRecord,
  EyeMovementFeatureRecord,
  SessionManifest,
  SonificationControlFrameRecord,
} from '../src/types';
import fixtureAJson from '../../tests/fixtures/session_packages/fixture-neuro/fixture-a/manifest.json';

function manifest(): SessionManifest {
  const value = structuredClone(parseFixtureManifest(fixtureAJson));
  value.session.session_id = 'eye-session';
  value.recording.duration_seconds = 100;
  value.signals = [
    {
      id: 'eeg',
      modality: 'eeg',
      channel_name: 'EEG Front',
      unit: 'uV',
      sampling_rate_hz: 4,
      source: 'raw',
      available: true,
    },
    {
      id: 'eog',
      modality: 'eog',
      channel_name: 'EOG horizontal',
      unit: 'uV',
      sampling_rate_hz: 4,
      source: 'raw',
      available: true,
    },
    {
      id: 'eog-filtered',
      modality: 'eog',
      channel_name: 'EOG horizontal · filtered',
      unit: 'uV',
      sampling_rate_hz: 4,
      source: 'derived',
      available: true,
    },
  ];
  value.capabilities.eeg = { status: 'AVAILABLE', source: 'raw' };
  value.capabilities.eog = { status: 'AVAILABLE', source: 'raw' };
  value.capabilities.eye_movement_activity = {
    status: 'AVAILABLE',
    source: 'derived',
  };
  value.capabilities.eye_movement_events = {
    status: 'AVAILABLE',
    source: 'derived',
  };
  value.capabilities.sonification_controls = {
    status: 'AVAILABLE',
    source: 'derived',
  };
  value.capabilities.alpha_power = { status: 'AVAILABLE', source: 'derived' };
  const viewer = {
    default_start_s: 0,
    default_time_s: 10,
    default_window_duration_s: 20,
    window_duration_options_s: [10, 20],
    display_max_points_per_signal: 100,
    feature_timestamp_semantics: 'window_end',
    stage_jump_time_s: 20,
    activity_jump_time_s: 12,
    replay: {
      enabled: true,
      tick_interval_ms: 20,
      default_speed: 1,
      speed_options: [0.5, 1, 2],
      cache_max_windows: 2,
      prefetch_threshold_fraction: 0.75,
      seek_cursor_fraction: 0.25,
      intervention_notice_duration_ms: 1000,
      intervention_marker_color: '#E1AA5A',
      provenance_notice: 'SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED',
    },
    audio: {
      master_gain: 0.1,
      attack_s: 0.01,
      release_s: 0.1,
      note_duration_s: 0.05,
      oscillator_type: 'sine',
    },
    baseline_controls: {
      tempo_bpm: 60,
      density: 0.05,
      intensity: 0.04,
      brightness_hz: 220,
      midi_note: 48,
    },
  };
  value.derived.eye_movement_activity_v1 = {
    available: true,
    source: 'derived',
    version: 'eye-movement-v1',
    metadata: {
      viewer,
      coverage: {
        coverage_start_s: 4,
        coverage_end_s: 100,
        window_s: 4,
        step_s: 1,
        row_count: 97,
        source_channel: 'EOG horizontal',
      },
    },
  };
  value.derived.eye_movement_events_v1 = {
    available: true,
    source: 'derived',
  };
  value.derived.sonification_control_v1 = {
    available: true,
    source: 'derived',
    metadata: {
      coverage_by_source: {
        eye_movement: { coverage_start_s: 4, coverage_end_s: 100 },
        alpha: { coverage_start_s: 8, coverage_end_s: 80 },
      },
    },
  };
  value.derived.alpha_power = {
    available: true,
    source: 'derived',
    metadata: { viewer },
  };
  return value;
}

const eyeRows: EyeMovementFeatureRecord[] = [8, 9, 10, 11, 12, 13].map(
  (time) => ({
    session_id: 'eye-session',
    source_channel: 'EOG horizontal',
    window_start_s: time - 4,
    window_end_s: time,
    recording_start_time: null,
    absolute_window_start: null,
    absolute_window_end: null,
    eog_rms_uv: 10 + time,
    peak_to_peak_uv: 40 + time,
    mean_absolute_derivative_uv_per_s: 20 + time,
    robust_deviation_z: time === 12 ? 5 : 1,
    activity_score: time / 20,
    amplitude_score: time / 20,
    event_rate_per_min: time === 12 ? 2 : 0,
    event_candidate: time === 12,
    signal_quality: 'valid',
    signal_quality_reasons: null,
    feature_version: 'eye-movement-v1',
    feature_provenance: 'derived',
  }),
);

const candidate: EyeMovementEventRecord = {
  event_id: 'eye-1',
  session_id: 'eye-session',
  timestamp: 12,
  window_start_s: 11.8,
  window_end_s: 12.2,
  duration_s: 0.4,
  amplitude_uv: -75,
  polarity: 'negative',
  confidence: 0.8,
  robust_deviation_z: 5,
  source_channel: 'EOG horizontal',
  feature_version: 'eye-movement-v1',
  provenance: 'derived',
  event_type: 'eye_movement_candidate',
};

const controls: SonificationControlFrameRecord[] = eyeRows.map((row) => ({
  session_id: 'eye-session',
  source: 'eye_movement',
  source_feature: 'eye_movement_activity_v1',
  window_start_s: row.window_start_s,
  window_end_s: row.window_end_s,
  available: true,
  tempo_bpm: 60 + row.window_end_s,
  density: row.activity_score,
  intensity: row.amplitude_score,
  brightness_hz: 300 + row.window_end_s * 10,
  trigger: row.window_end_s === 12,
  event_id: row.window_end_s === 12 ? 'eye-1' : null,
  note_midi: row.window_end_s === 12 ? 55 : null,
  note_velocity: row.window_end_s === 12 ? 0.5 : null,
  mapping_version: 'sonification-mapping-v1',
  control_version: 'sonification-control-v1',
  seed: 42,
  provenance: 'sonification_control',
}));

class EyeReplaySource implements ReplaySource {
  constructor(private readonly value: SessionManifest) {}

  getSession() {
    return this.value;
  }
  getDuration() {
    return this.value.recording.duration_seconds;
  }
  getSignalMetadata() {
    return this.value.signals;
  }
  async readSignalWindow(
    signalId: string,
    startSeconds: number,
    durationSeconds: number,
  ) {
    const signal = this.value.signals.find((item) => item.id === signalId)!;
    const samples = Array.from({ length: durationSeconds * 4 }, (_, index) =>
      Math.sin((index / 4) * Math.PI),
    );
    return {
      signal,
      startSeconds,
      durationSeconds,
      timestamps: samples.map((_, index) => startSeconds + index / 4),
      samples,
    };
  }
  async readAnnotations(
    startSeconds: number,
    endSeconds: number,
  ): Promise<AnnotationWindowResponse> {
    return {
      session_id: 'eye-session',
      start_s: startSeconds,
      end_s: endSeconds,
      descriptors: {},
      annotations: [
        {
          annotation_type: 'sleep_stages',
          start_seconds: startSeconds,
          duration_seconds: endSeconds - startSeconds,
          label: 'W',
          provenance: 'imported',
        },
      ],
    };
  }
  async readDerived(
    metric: string,
    startSeconds: number,
    endSeconds: number,
  ): Promise<DerivedWindowResponse> {
    const records =
      metric === 'eye_movement_activity_v1'
        ? eyeRows
        : metric === 'eye_movement_events_v1'
          ? [candidate]
          : metric === 'sonification_control_v1'
            ? controls
            : [];
    return {
      session_id: 'eye-session',
      metric,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: this.value.derived[metric]!,
      records,
    };
  }
  async readEvents(startSeconds: number, endSeconds: number) {
    return {
      session_id: 'eye-session',
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: null,
      events: [],
    };
  }
}

class MockParam {
  value = 0;
  setValueAtTime = vi.fn();
  linearRampToValueAtTime = vi.fn();
}

class MockNode {
  connect = vi.fn();
}

class MockGain extends MockNode {
  gain = new MockParam();
}

class MockOscillator extends MockNode {
  type: OscillatorType = 'sine';
  frequency = new MockParam();
  start = vi.fn();
  stop = vi.fn();
}

class MockFilter extends MockNode {
  type: BiquadFilterType = 'lowpass';
  frequency = new MockParam();
}

class MockAudioContext {
  static instances: MockAudioContext[] = [];
  currentTime = 0;
  destination = new MockNode();
  resume = vi.fn(() => Promise.resolve());
  close = vi.fn(() => Promise.resolve());
  createGain = vi.fn(() => new MockGain());
  createOscillator = vi.fn(() => new MockOscillator());
  createBiquadFilter = vi.fn(() => new MockFilter());

  constructor() {
    MockAudioContext.instances.push(this);
  }
}

describe('Eye Movement primary viewer integration', () => {
  beforeEach(() => {
    MockAudioContext.instances = [];
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
  });

  it('renders synchronized raw/filtered EOG, activity, events and controls before Alpha', async () => {
    render(
      <AlphaSessionViewer
        manifest={manifest()}
        replaySource={new EyeReplaySource(manifest())}
      />,
    );

    expect(await screen.findByTestId('raw-eog-track')).toBeVisible();
    expect(screen.getByTestId('filtered-eog-track')).toBeVisible();
    expect(screen.getByTestId('eye-movement-panel')).toHaveAttribute(
      'data-coverage-state',
      'available',
    );
    expect(screen.getByTestId('eye-activity-chart')).toHaveAttribute(
      'data-display-end-timestamp',
      '10',
    );
    expect(screen.getByTestId('sonification-panel')).toHaveAttribute(
      'data-source',
      'eye_movement',
    );
    expect(screen.getByLabelText('Eye Movement')).toBeChecked();
    const primary = screen.getByTestId('eye-movement-panel');
    const alpha = screen.getByLabelText('Alpha V1 derived metrics');
    expect(
      primary.compareDocumentPosition(alpha) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('updates candidates and shared cursor after seek and exposes outside coverage', async () => {
    const user = userEvent.setup();
    render(
      <AlphaSessionViewer
        manifest={manifest()}
        replaySource={new EyeReplaySource(manifest())}
      />,
    );
    await screen.findByTestId('eye-movement-panel');
    const jump = screen.getByLabelText('Jump to seconds');
    await user.clear(jump);
    await user.type(jump, '13');
    await user.click(screen.getByRole('button', { name: 'Seek' }));
    expect(
      await screen.findByText(/12.00 s · Eye Movement Candidate/),
    ).toBeVisible();
    expect(screen.getByTestId('eye-activity-chart')).toHaveAttribute(
      'data-display-end-timestamp',
      '13',
    );

    await user.clear(jump);
    await user.type(jump, '2');
    await user.click(screen.getByRole('button', { name: 'Seek' }));
    await waitFor(() =>
      expect(screen.getByTestId('eye-movement-panel')).toHaveAttribute(
        'data-coverage-state',
        'outside_coverage',
      ),
    );
    expect(
      screen.getByText('No precomputed eye-movement feature at this time.'),
    ).toBeVisible();
  });

  it('starts real Web Audio only on user action and supports comparison sources', async () => {
    const user = userEvent.setup();
    render(
      <AlphaSessionViewer
        manifest={manifest()}
        replaySource={new EyeReplaySource(manifest())}
      />,
    );
    await screen.findByTestId('sonification-panel');
    expect(MockAudioContext.instances).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Play Sound' }));
    await waitFor(() =>
      expect(screen.getByTestId('audio-state')).toHaveTextContent(
        'audio enabled',
      ),
    );
    expect(MockAudioContext.instances).toHaveLength(1);
    expect(MockAudioContext.instances[0].resume).toHaveBeenCalled();

    await user.click(screen.getByLabelText('Alpha'));
    expect(screen.getByTestId('sonification-panel')).toHaveAttribute(
      'data-source',
      'alpha',
    );
    await user.click(screen.getByLabelText('None / baseline'));
    expect(screen.getByText(/intentionally constant/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Mute' }));
    expect(screen.getByTestId('audio-state')).toHaveTextContent('audio muted');
    await user.click(screen.getByRole('button', { name: 'Reset sound' }));
    expect(screen.getByTestId('audio-state')).toHaveTextContent(
      'audio stopped',
    );
  });
});
