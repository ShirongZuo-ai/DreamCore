import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { AlphaSessionViewer } from '../src/components/alpha/AlphaSessionViewer';
import { parseFixtureManifest } from '../src/mocks/sessionFixtures';
import type { ReplaySource } from '../src/services/replaySource';
import { HttpReplaySource } from '../src/services/replaySource';
import { HttpSessionCatalogService } from '../src/services/sessionCatalogService';
import type {
  AlphaFeatureRecord,
  AnnotationWindowResponse,
  EventWindowResponse,
  SessionManifest,
} from '../src/types';
import fixtureAJson from '../../tests/fixtures/session_packages/fixture-neuro/fixture-a/manifest.json';

function jsonResponse(data: unknown, ok = true) {
  return Promise.resolve({
    ok,
    statusText: ok ? 'OK' : 'Error',
    json: () => Promise.resolve(data),
  } as Response);
}

function realManifest(): SessionManifest {
  const fixture = structuredClone(parseFixtureManifest(fixtureAJson));
  fixture.dataset = { id: 'public-eeg', display_name: 'Public EEG' };
  fixture.session.session_id = 'public-alpha';
  fixture.signals = [
    {
      id: 'front',
      modality: 'eeg',
      channel_name: 'EEG Front',
      unit: 'uV',
      sampling_rate_hz: 4,
      source: 'raw',
      available: true,
    },
    {
      id: 'posterior',
      modality: 'eeg',
      channel_name: 'EEG Posterior',
      unit: 'uV',
      sampling_rate_hz: 4,
      source: 'raw',
      available: true,
    },
  ];
  fixture.derived.alpha_power = {
    available: true,
    source: 'derived',
    derived_by: 'alpha-v1',
    metadata: {
      viewer: {
        default_start_s: 10,
        default_time_s: 10,
        default_window_duration_s: 20,
        window_duration_options_s: [10, 20],
        display_max_points_per_signal: 100,
        feature_timestamp_semantics: 'window_end',
        stage_jump_time_s: 20,
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
      },
      analysis: {
        time_reference: 'recording_relative',
        timestamp_field: 'window_end_s',
        timestamp_unit: 'seconds',
        evaluation_start_s: 0,
        evaluation_end_s: 100,
        analysis_window_s: 30,
        step_s: 30,
        attempted_windows: 3,
        accepted_windows: 3,
        rejected_windows: 0,
        rejection_reasons: {},
        feature_row_count: 3,
        first_feature_time_s: 30,
        last_feature_time_s: 90,
        channels: ['EEG Posterior'],
        product_display_min_iaf_confidence: 0.5,
        product_display_context_s: 300,
      },
    },
  };
  fixture.capabilities.eeg = { status: 'AVAILABLE', source: 'raw' };
  fixture.capabilities.alpha_power = { status: 'AVAILABLE', source: 'derived' };
  fixture.capabilities.stimulation_demand = {
    status: 'AVAILABLE',
    source: 'simulated',
  };
  fixture.provenance = {
    classification: 'imported',
    source_dataset_uri: 'public-test',
    notes: 'REAL PUBLIC EEG DATA',
  };
  return fixture;
}

function feature(channel: string, start: number): AlphaFeatureRecord {
  return {
    channel,
    window_start_s: start,
    window_end_s: start + 10,
    stage: start < 20 ? 'W' : 'N1',
    absolute_alpha_power: channel.includes('Posterior') ? 8 : 3,
    relative_alpha_power: channel.includes('Posterior') ? 0.12 : 0.02,
    individual_alpha_frequency_hz: channel.includes('Posterior') ? 12.5 : null,
    iaf_confidence: channel.includes('Posterior') ? 0.398 : 0,
    iaf_available: channel.includes('Posterior'),
    iaf_reason: channel.includes('Posterior') ? null : 'no_reliable_alpha_peak',
    window_iaf_hz: null,
    window_iaf_confidence: null,
    alpha_trend: 'falling',
    alpha_trend_slope: -0.01,
    alpha_change_from_baseline: -0.2,
    drowsiness_score: 0.6,
    state_confidence: 0.8,
    stimulation_demand: 0.3,
    demand_available: true,
    ready_to_remove: false,
    feature_provenance: 'derived',
    demand_provenance: 'SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE',
  };
}

class ViewerReplaySource implements ReplaySource {
  constructor(
    private readonly manifest: SessionManifest,
    private readonly failure: Error | null = null,
  ) {}

  getSession() {
    return this.manifest;
  }
  getDuration() {
    return this.manifest.recording.duration_seconds;
  }
  getSignalMetadata() {
    return this.manifest.signals;
  }
  async readSignalWindow(
    signalId: string,
    startSeconds: number,
    durationSeconds: number,
  ) {
    if (this.failure) throw this.failure;
    const signal = this.manifest.signals.find((item) => item.id === signalId)!;
    const samples = Array.from({ length: durationSeconds * 4 }, (_, index) =>
      Math.sin((index / 4) * Math.PI * 2),
    );
    return {
      signal,
      startSeconds,
      durationSeconds,
      timestamps: samples.map((_, index) => startSeconds + index / 4),
      samples,
    };
  }
  async readAnnotations(startSeconds: number, endSeconds: number) {
    return {
      session_id: this.manifest.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptors: this.manifest.annotations,
      annotations: [
        {
          annotation_type: 'sleep_stages',
          start_seconds: startSeconds,
          duration_seconds: (endSeconds - startSeconds) / 2,
          label: 'W',
          raw_label: 'Sleep stage W',
          provenance: 'imported',
        },
        {
          annotation_type: 'sleep_stages',
          start_seconds: (startSeconds + endSeconds) / 2,
          duration_seconds: (endSeconds - startSeconds) / 2,
          label: 'N1',
          raw_label: 'Sleep stage 1',
          provenance: 'imported',
        },
      ],
    } satisfies AnnotationWindowResponse;
  }
  async readDerived(metric: string, startSeconds: number, endSeconds: number) {
    return {
      session_id: this.manifest.session.session_id,
      metric,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: this.manifest.derived.alpha_power,
      records: [
        feature('EEG Front', Math.max(0, endSeconds - 30)),
        feature('EEG Posterior', Math.max(0, endSeconds - 30)),
      ],
    };
  }
  async readEvents(startSeconds: number, endSeconds: number) {
    return {
      session_id: this.manifest.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: { available: true, source: 'simulated' },
      events: [
        {
          timestamp: startSeconds + 5,
          demand_before: 0.4,
          demand_after: 0.3,
          state: 'drowsy',
          alpha_power: 3,
          relative_alpha_power: 0.02,
          alpha_trend: 'falling',
          confidence: 0.8,
          event_type: 'stimulation_reduced',
          provenance: 'simulated',
          provenance_notice: 'SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE',
        },
      ],
    } satisfies EventWindowResponse;
  }
}

describe('HTTP catalog and replay transports', () => {
  afterEach(() => vi.restoreAllMocks());

  it('loads a versioned HTTP catalog and maps real sessions', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() =>
        jsonResponse({
          api_version: 'v1',
          data: [
            {
              id: 'public-eeg',
              display_name: 'Public EEG',
              session_count: 1,
              available_capabilities: ['eeg', 'alpha_power'],
            },
          ],
        }),
      )
      .mockImplementationOnce(() =>
        jsonResponse({
          api_version: 'v1',
          data: [
            {
              dataset: { id: 'public-eeg', display_name: 'Public EEG' },
              session: { session_id: 'public-alpha', subject_id: 'PUBLIC-1' },
              recording: { duration_seconds: 100 },
              capabilities: realManifest().capabilities,
              has_sleep_stage: true,
              has_n3: false,
              provenance: 'imported',
            },
          ],
        }),
      );
    const service = new HttpSessionCatalogService('/api/v1');
    const datasets = await service.listDatasets();
    const sessions = await service.listSessions(datasets[0].id);
    expect(datasets[0]).toMatchObject({
      sessionCount: 1,
      availableCapabilities: 2,
    });
    expect(sessions[0]).toMatchObject({
      sessionId: 'public-alpha',
      catalogTransport: 'http',
      provenance: 'imported',
    });
  });

  it('validates the explicit signal unit and sample/time contract', async () => {
    const manifest = realManifest();
    vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      jsonResponse({
        api_version: 'v1',
        data: {
          session_id: 'public-alpha',
          signal_id: 'front',
          channel: 'EEG Front',
          provenance: 'raw',
          start_s: 10,
          end_s: 11,
          duration_s: 1,
          sampling_rate_hz: 4,
          unit: 'uV',
          n_samples: 4,
          timestamps: [10, 10.25, 10.5, 10.75],
          samples: [1, 2, 3, 4],
        },
      }),
    );
    const window = await new HttpReplaySource(manifest).readSignalWindow(
      'front',
      10,
      1,
    );
    expect(window.signal.unit).toBe('uV');
    expect(window.samples).toHaveLength(4);
    expect(window.timestamps).toEqual([10, 10.25, 10.5, 10.75]);
  });

  it('uses one bounded request for an ordered multi-signal window', async () => {
    const manifest = realManifest();
    const requested = vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      jsonResponse({
        api_version: 'v1',
        data: {
          session_id: 'public-alpha',
          start_s: 10,
          duration_s: 1,
          windows: manifest.signals.map((signal, index) => ({
            session_id: 'public-alpha',
            signal_id: signal.id,
            channel: signal.channel_name,
            provenance: 'raw',
            start_s: 10,
            end_s: 11,
            duration_s: 1,
            sampling_rate_hz: 4,
            unit: 'uV',
            n_samples: 4,
            timestamps: [10, 10.25, 10.5, 10.75],
            samples: [index, index, index, index],
          })),
        },
      }),
    );
    const signalIds = manifest.signals.map((signal) => signal.id);

    const windows = await new HttpReplaySource(manifest).readSignalWindows(
      signalIds,
      10,
      1,
    );

    expect(requested).toHaveBeenCalledTimes(1);
    expect(String(requested.mock.calls[0][0])).toContain(
      '/signals/window?start_s=10&duration_s=1&signal_id=front&signal_id=posterior',
    );
    expect(windows.map((window) => window.signal.id)).toEqual(signalIds);
  });
});

describe('real Alpha viewer states', () => {
  it('renders real EEG, stages, Alpha unavailability, and simulated provenance', async () => {
    const manifest = realManifest();
    render(
      <AlphaSessionViewer
        manifest={manifest}
        replaySource={new ViewerReplaySource(manifest)}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading bounded signal window',
    );
    expect(await screen.findByTestId('real-eeg-window')).toBeVisible();
    expect(
      screen.getByRole('region', { name: 'Recording source metadata' }),
    ).toHaveTextContent('Public EEG · public-alpha');
    expect(screen.getAllByText('EEG Front').length).toBeGreaterThan(0);
    expect(screen.getAllByText('EEG Posterior').length).toBeGreaterThan(0);
    expect(screen.getAllByText('uV').length).toBeGreaterThan(0);
    expect(screen.getByText('Imported sleep-stage annotation')).toBeVisible();
    expect(screen.getAllByText('W').length).toBeGreaterThan(0);
    expect(screen.getAllByText('N1').length).toBeGreaterThan(0);
    const alpha = screen.getByLabelText('Alpha V1 derived metrics');
    expect(alpha).toHaveTextContent('Primary signal EEG Posterior');
    expect(alpha).not.toHaveTextContent('Primary signal EEG Front');
    expect(screen.getByTestId('product-iaf')).toHaveTextContent(
      'No clear Alpha peak',
    );
    expect(screen.getByTestId('product-iaf')).not.toHaveTextContent('12.50 Hz');
    expect(screen.getByText('SIMULATED CONTROL DEMAND')).toBeVisible();
    expect(screen.getByText('NOT ULTRASOUND DOSE')).toBeVisible();
    expect(screen.queryByText(/ultrasound applied/i)).not.toBeInTheDocument();
  });

  it('keeps all panels on the same range after manual navigation', async () => {
    const user = userEvent.setup();
    const manifest = realManifest();
    render(
      <AlphaSessionViewer
        manifest={manifest}
        replaySource={new ViewerReplaySource(manifest)}
      />,
    );
    await screen.findByTestId('real-eeg-window');
    await user.click(screen.getByRole('button', { name: /Next/ }));
    expect(await screen.findByTestId('window-range')).toHaveTextContent(
      '30.0–50.0 s',
    );
    await waitFor(() =>
      expect(screen.getByTestId('real-eeg-window')).toBeInTheDocument(),
    );
  });

  it('shows raw EOG without exposing internal missing-artifact language', async () => {
    const manifest = realManifest();
    manifest.signals.push({
      id: 'eog-left',
      modality: 'eog',
      channel_name: 'E1-M2',
      original_channel_name: 'E1-M2',
      canonical_role: 'EOG_LEFT',
      unit: 'uV',
      sampling_rate_hz: 4,
      source: 'raw',
      available: true,
    });
    manifest.capabilities.eog = { status: 'AVAILABLE', source: 'raw' };
    manifest.capabilities.eye_movement_activity = {
      status: 'PLANNED',
      source: 'derived',
      reason: 'Source available; Eye Movement not computed',
    };
    manifest.capabilities.alpha_power = {
      status: 'PLANNED',
      source: 'derived',
      reason: 'Source available; Alpha diagnostic not computed',
    };
    manifest.derived.eye_movement_activity_v1 = {
      available: false,
      source: 'derived',
      reason: 'Available EOG source; Eye Movement analysis not computed',
      metadata: { availability_state: 'not_computed' },
    };

    render(
      <AlphaSessionViewer
        manifest={manifest}
        replaySource={new ViewerReplaySource(manifest)}
      />,
    );

    expect(await screen.findByTestId('raw-eog-track')).toHaveTextContent(
      'E1-M2',
    );
    expect(screen.getByTestId('sleep-insights')).toBeVisible();
    expect(
      screen.queryByText(/analysis not computed/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/derived artifact missing/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('eye-movement-panel')).not.toBeInTheDocument();
  });

  it('advances an offline replay cursor and records only simulated intervention markers', async () => {
    const user = userEvent.setup();
    const manifest = realManifest();
    render(
      <AlphaSessionViewer
        manifest={manifest}
        replaySource={new ViewerReplaySource(manifest)}
      />,
    );
    await screen.findByTestId('real-eeg-window');
    const range = screen.getByTestId('window-range');
    expect(range).toHaveTextContent('cursor 10.00 s · idle');
    expect(screen.getByTestId('alpha-absolute-chart')).toHaveAttribute(
      'data-display-mode',
      'observed-samples',
    );
    expect(screen.getByTestId('alpha-absolute-chart')).toHaveAttribute(
      'data-point-rendering',
      'observed-glyphs',
    );
    expect(screen.getByTestId('alpha-absolute-chart')).toHaveAttribute(
      'data-point-connection',
      'discrete',
    );
    expect(screen.getByTestId('alpha-absolute-chart')).toHaveAttribute(
      'data-display-end-timestamp',
      '10',
    );
    expect(screen.getByTestId('real-eeg-uplot')).toHaveAttribute(
      'data-last-visible-timestamp',
      '10',
    );

    await user.click(screen.getByRole('button', { name: 'Start replay' }));
    await waitFor(() => expect(range).toHaveTextContent(/playing 1×/));
    await waitFor(() => expect(range).not.toHaveTextContent('cursor 10.00 s'));
    await user.click(screen.getByRole('button', { name: 'Pause replay' }));
    await user.click(
      screen.getByRole('button', { name: 'Mark simulated intervention' }),
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('SIMULATED INTERVENTION MARKED');
    expect(alert).toHaveTextContent(
      'SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED',
    );
    expect(alert).toHaveTextContent(
      'Observed EEG and derived Alpha values remain unchanged',
    );
    expect(
      screen.getAllByLabelText(/SIMULATED INTERVENTION.* at/).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/ultrasound applied/i)).not.toBeInTheDocument();
  });

  it('shows an HTTP error without fabricating physiology', async () => {
    const manifest = realManifest();
    render(
      <AlphaSessionViewer
        manifest={manifest}
        replaySource={
          new ViewerReplaySource(manifest, new Error('transport failed'))
        }
      />,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'transport failed',
    );
    expect(screen.queryByText(/bpm/i)).not.toBeInTheDocument();
  });
});
