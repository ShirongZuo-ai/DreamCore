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
  async readDerived(): Promise<DerivedWindowResponse> {
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
