import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { parseFixtureManifest } from '../src/mocks/sessionFixtures';
import { useReplayWindow } from '../src/replay/useReplayWindow';
import type {
  ReplaySignalWindow,
  ReplaySource,
} from '../src/services/replaySource';
import type { DerivedWindowResponse, SessionManifest } from '../src/types';
import fixtureAJson from '../../tests/fixtures/session_packages/fixture-neuro/fixture-a/manifest.json';

function manifest(): SessionManifest {
  const value = structuredClone(parseFixtureManifest(fixtureAJson));
  value.recording.duration_seconds = 100;
  value.signals = [
    {
      id: 'eeg',
      modality: 'eeg',
      channel_name: 'EEG Test',
      unit: 'uV',
      sampling_rate_hz: 1,
      source: 'raw',
      available: true,
    },
  ];
  value.capabilities.alpha_power = {
    status: 'UNAVAILABLE',
    source: 'derived',
  };
  return value;
}

class DeferredReplaySource implements ReplaySource {
  readonly controllers: AbortSignal[] = [];
  readonly signalRequests: number[] = [];
  readonly resolvers = new Map<number, (value: ReplaySignalWindow) => void>();

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
  readSignalWindow(
    _signalId: string,
    startSeconds: number,
    durationSeconds: number,
    signal?: AbortSignal,
  ) {
    this.signalRequests.push(startSeconds);
    if (signal) this.controllers.push(signal);
    return new Promise<ReplaySignalWindow>((resolve) => {
      this.resolvers.set(startSeconds, resolve);
    }).then((result) => result);
  }
  async readAnnotations(startSeconds: number, endSeconds: number) {
    return {
      session_id: this.value.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptors: {},
      annotations: [],
    };
  }
  async readDerived(
    metric: string,
    startSeconds: number,
    endSeconds: number,
  ): Promise<DerivedWindowResponse> {
    void metric;
    void startSeconds;
    void endSeconds;
    throw new Error('derived should not be requested');
  }
  async readEvents(startSeconds: number, endSeconds: number) {
    return {
      session_id: this.value.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: null,
      events: [],
    };
  }

  resolve(startSeconds: number, durationSeconds = 10) {
    const resolve = this.resolvers.get(startSeconds);
    if (!resolve) throw new Error(`No request for ${startSeconds}`);
    resolve({
      signal: this.value.signals[0],
      startSeconds,
      durationSeconds,
      timestamps: [startSeconds],
      samples: [startSeconds],
    });
  }
}

class BatchedReplaySource implements ReplaySource {
  readonly batchRequests: string[][] = [];

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
  async readSignalWindow(): Promise<ReplaySignalWindow> {
    throw new Error('Viewer should use the available multi-signal primitive');
  }
  async readSignalWindows(
    signalIds: readonly string[],
    startSeconds: number,
    durationSeconds: number,
  ) {
    this.batchRequests.push([...signalIds]);
    return signalIds.map((signalId) => ({
      signal: this.value.signals.find((item) => item.id === signalId)!,
      startSeconds,
      durationSeconds,
      timestamps: [startSeconds],
      samples: [startSeconds],
    }));
  }
  async readAnnotations(startSeconds: number, endSeconds: number) {
    return {
      session_id: this.value.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptors: {},
      annotations: [],
    };
  }
  async readDerived(
    metric: string,
    startSeconds: number,
    endSeconds: number,
  ): Promise<DerivedWindowResponse> {
    void metric;
    void startSeconds;
    void endSeconds;
    throw new Error('derived should not be requested');
  }
  async readEvents(startSeconds: number, endSeconds: number) {
    return {
      session_id: this.value.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: null,
      events: [],
    };
  }
}

class AlphaContextReplaySource extends BatchedReplaySource {
  readonly derivedRequests: Array<{
    metric: string;
    startSeconds: number;
    endSeconds: number;
  }> = [];

  async readDerived(
    metric: string,
    startSeconds: number,
    endSeconds: number,
  ): Promise<DerivedWindowResponse> {
    this.derivedRequests.push({ metric, startSeconds, endSeconds });
    return {
      session_id: this.getSession().session.session_id,
      metric,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: this.getSession().derived.alpha_power!,
      records: [],
    };
  }
}

function Harness({
  source,
  value,
  startSeconds,
  shouldPrefetch = false,
}: {
  source: ReplaySource;
  value: SessionManifest;
  startSeconds: number;
  shouldPrefetch?: boolean;
}) {
  const result = useReplayWindow({
    replaySource: source,
    manifest: value,
    signals: value.signals,
    startSeconds,
    durationSeconds: 10,
    cacheMaxWindows: 2,
    shouldPrefetch,
  });
  return (
    <p data-testid="window-state">
      {result.status}:{result.data?.signals[0]?.startSeconds ?? 'none'}
    </p>
  );
}

describe('windowed replay transport coordination', () => {
  it('loads all displayed channels through one bounded batch when supported', async () => {
    const value = manifest();
    value.signals.push({ ...value.signals[0], id: 'eog', modality: 'eog' });
    const source = new BatchedReplaySource(value);
    render(<Harness source={source} value={value} startSeconds={0} />);

    await waitFor(() =>
      expect(screen.getByTestId('window-state')).toHaveTextContent('ready:0'),
    );
    expect(source.batchRequests).toEqual([['eeg', 'eog']]);
  });

  it('requests a separate bounded recent context for sparse Alpha rows', async () => {
    const value = manifest();
    value.recording.duration_seconds = 1_000;
    value.capabilities.alpha_power = { status: 'AVAILABLE', source: 'derived' };
    value.derived.alpha_power = {
      available: true,
      source: 'derived',
      metadata: {
        analysis: {
          evaluation_start_s: 0,
          product_display_context_s: 300,
        },
      },
    };
    const source = new AlphaContextReplaySource(value);
    render(<Harness source={source} value={value} startSeconds={400} />);

    await waitFor(() =>
      expect(screen.getByTestId('window-state')).toHaveTextContent('ready:400'),
    );
    expect(source.derivedRequests).toEqual([
      { metric: 'alpha_power', startSeconds: 100, endSeconds: 410 },
    ]);
  });

  it('keeps the Alpha request valid before configured analysis coverage', async () => {
    const value = manifest();
    value.recording.duration_seconds = 1_000;
    value.capabilities.alpha_power = { status: 'AVAILABLE', source: 'derived' };
    value.derived.alpha_power = {
      available: true,
      source: 'derived',
      metadata: {
        analysis: {
          evaluation_start_s: 700,
          product_display_context_s: 300,
        },
      },
    };
    const source = new AlphaContextReplaySource(value);
    render(<Harness source={source} value={value} startSeconds={100} />);

    await waitFor(() =>
      expect(screen.getByTestId('window-state')).toHaveTextContent('ready:100'),
    );
    expect(source.derivedRequests).toEqual([
      { metric: 'alpha_power', startSeconds: 100, endSeconds: 110 },
    ]);
  });

  it('aborts the old request and ignores its stale response after seek', async () => {
    const value = manifest();
    const source = new DeferredReplaySource(value);
    const { rerender } = render(
      <Harness source={source} value={value} startSeconds={0} />,
    );
    await waitFor(() => expect(source.signalRequests).toEqual([0]));

    rerender(<Harness source={source} value={value} startSeconds={10} />);
    await waitFor(() => expect(source.signalRequests).toEqual([0, 10]));
    expect(source.controllers[0].aborted).toBe(true);

    source.resolve(10);
    await waitFor(() =>
      expect(screen.getByTestId('window-state')).toHaveTextContent('ready:10'),
    );
    source.resolve(0);
    await Promise.resolve();
    expect(screen.getByTestId('window-state')).toHaveTextContent('ready:10');
  });

  it('prefetches the next bounded window only after the current window is ready', async () => {
    const value = manifest();
    const source = new DeferredReplaySource(value);
    render(
      <Harness source={source} value={value} startSeconds={0} shouldPrefetch />,
    );
    await waitFor(() => expect(source.signalRequests).toEqual([0]));
    source.resolve(0);
    await waitFor(() => expect(source.signalRequests).toEqual([0, 10]));
    expect(source.signalRequests).toHaveLength(2);
  });
});
