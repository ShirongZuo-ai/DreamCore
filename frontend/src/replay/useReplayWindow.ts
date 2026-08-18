import { useEffect, useMemo, useRef, useState } from 'react';

import type {
  ReplaySource,
  ReplaySignalWindow,
} from '../services/replaySource';
import type {
  AlphaFeatureRecord,
  AnnotationWindowResponse,
  CanonicalSignalMetadata,
  EyeMovementEventRecord,
  EyeMovementFeatureRecord,
  EventWindowResponse,
  SessionManifest,
  SonificationControlFrameRecord,
} from '../types';
import { BoundedWindowCache } from './windowCache';

export type ReplayWindowData = {
  signals: ReplaySignalWindow[];
  annotations: AnnotationWindowResponse;
  features: AlphaFeatureRecord[];
  eyeMovementFeatures: EyeMovementFeatureRecord[];
  eyeMovementEvents: EyeMovementEventRecord[];
  sonificationControls: SonificationControlFrameRecord[];
  events: EventWindowResponse;
};

export type ReplayWindowStatus = 'loading' | 'ready' | 'error';

function keyFor(startSeconds: number, durationSeconds: number) {
  return `${startSeconds.toFixed(6)}:${durationSeconds.toFixed(6)}`;
}

function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError';
}

function alphaFeatureRange(
  manifest: SessionManifest,
  startSeconds: number,
  endSeconds: number,
) {
  const analysis = manifest.derived.alpha_power?.metadata?.analysis;
  if (!analysis || typeof analysis !== 'object') {
    return { startSeconds, endSeconds };
  }
  const metadata = analysis as Record<string, unknown>;
  const context = metadata.product_display_context_s;
  const evaluationStart = metadata.evaluation_start_s;
  if (
    typeof context !== 'number' ||
    !Number.isFinite(context) ||
    context <= 0 ||
    typeof evaluationStart !== 'number' ||
    !Number.isFinite(evaluationStart)
  ) {
    return { startSeconds, endSeconds };
  }
  if (endSeconds <= evaluationStart) {
    return { startSeconds, endSeconds };
  }
  return {
    startSeconds: Math.max(evaluationStart, startSeconds - context),
    endSeconds,
  };
}

async function readWindow(
  replaySource: ReplaySource,
  manifest: SessionManifest,
  signals: readonly CanonicalSignalMetadata[],
  startSeconds: number,
  durationSeconds: number,
  signal: AbortSignal,
): Promise<ReplayWindowData> {
  const endSeconds = Math.min(
    startSeconds + durationSeconds,
    replaySource.getDuration(),
  );
  const alphaRange = alphaFeatureRange(manifest, startSeconds, endSeconds);
  const [
    signalWindows,
    annotations,
    alphaDerived,
    eyeMovementDerived,
    eyeMovementEvents,
    sonificationControls,
    events,
  ] = await Promise.all([
    replaySource.readSignalWindows
      ? replaySource.readSignalWindows(
          signals.map((item) => item.id),
          startSeconds,
          endSeconds - startSeconds,
          signal,
        )
      : Promise.all(
          signals.map((item) =>
            replaySource.readSignalWindow(
              item.id,
              startSeconds,
              endSeconds - startSeconds,
              signal,
            ),
          ),
        ),
    replaySource.readAnnotations(startSeconds, endSeconds, signal),
    manifest.capabilities.alpha_power.status === 'AVAILABLE'
      ? replaySource.readDerived(
          'alpha_power',
          alphaRange.startSeconds,
          alphaRange.endSeconds,
          signal,
        )
      : Promise.resolve(null),
    manifest.capabilities.eye_movement_activity.status === 'AVAILABLE'
      ? replaySource.readDerived(
          'eye_movement_activity_v1',
          startSeconds,
          endSeconds,
          signal,
        )
      : Promise.resolve(null),
    manifest.capabilities.eye_movement_events.status === 'AVAILABLE'
      ? replaySource.readDerived(
          'eye_movement_events_v1',
          startSeconds,
          endSeconds,
          signal,
        )
      : Promise.resolve(null),
    manifest.capabilities.sonification_controls.status === 'AVAILABLE'
      ? replaySource.readDerived(
          'sonification_control_v1',
          startSeconds,
          endSeconds,
          signal,
        )
      : Promise.resolve(null),
    replaySource.readEvents(startSeconds, endSeconds, signal),
  ]);
  return {
    signals: signalWindows,
    annotations,
    features: (alphaDerived?.records ?? []) as AlphaFeatureRecord[],
    eyeMovementFeatures: (eyeMovementDerived?.records ??
      []) as EyeMovementFeatureRecord[],
    eyeMovementEvents: (eyeMovementEvents?.records ??
      []) as EyeMovementEventRecord[],
    sonificationControls: (sonificationControls?.records ??
      []) as SonificationControlFrameRecord[],
    events,
  };
}

export function useReplayWindow({
  replaySource,
  manifest,
  signals,
  startSeconds,
  durationSeconds,
  cacheMaxWindows,
  shouldPrefetch,
}: {
  replaySource: ReplaySource;
  manifest: SessionManifest;
  signals: readonly CanonicalSignalMetadata[];
  startSeconds: number;
  durationSeconds: number;
  cacheMaxWindows: number;
  shouldPrefetch: boolean;
}) {
  const cache = useMemo(
    () => new BoundedWindowCache<ReplayWindowData>(cacheMaxWindows),
    [cacheMaxWindows],
  );
  const generation = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const prefetchController = useRef<AbortController | null>(null);
  const [data, setData] = useState<ReplayWindowData | null>(null);
  const [status, setStatus] = useState<ReplayWindowStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const requestCount = useRef(0);
  const staleResponsesIgnored = useRef(0);
  const currentKey = keyFor(startSeconds, durationSeconds);

  useEffect(() => {
    generation.current += 1;
    const requestGeneration = generation.current;
    activeController.current?.abort();
    prefetchController.current?.abort();
    const cached = cache.get(currentKey);
    if (cached) {
      setData(cached);
      setStatus('ready');
      setError(null);
      return;
    }
    const controller = new AbortController();
    activeController.current = controller;
    setStatus('loading');
    setError(null);
    requestCount.current += 1;
    void readWindow(
      replaySource,
      manifest,
      signals,
      startSeconds,
      durationSeconds,
      controller.signal,
    )
      .then((result) => {
        if (
          controller.signal.aborted ||
          requestGeneration !== generation.current
        ) {
          staleResponsesIgnored.current += 1;
          return;
        }
        cache.set(currentKey, result);
        setData(result);
        setStatus('ready');
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted || isAbort(loadError)) return;
        if (requestGeneration !== generation.current) {
          staleResponsesIgnored.current += 1;
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to read session window',
        );
        setStatus('error');
      });
    return () => controller.abort();
  }, [
    cache,
    currentKey,
    durationSeconds,
    manifest,
    replaySource,
    signals,
    startSeconds,
  ]);

  useEffect(() => {
    if (!shouldPrefetch || status !== 'ready') return;
    const nextStart = Math.min(
      startSeconds + durationSeconds,
      Math.max(0, replaySource.getDuration() - durationSeconds),
    );
    if (nextStart <= startSeconds) return;
    const nextKey = keyFor(nextStart, durationSeconds);
    if (cache.peek(nextKey)) return;
    prefetchController.current?.abort();
    const controller = new AbortController();
    prefetchController.current = controller;
    requestCount.current += 1;
    void readWindow(
      replaySource,
      manifest,
      signals,
      nextStart,
      durationSeconds,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) cache.set(nextKey, result);
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted && !isAbort(loadError)) {
          // Prefetch failure is non-fatal; the foreground request can retry.
        }
      });
    return () => controller.abort();
  }, [
    cache,
    durationSeconds,
    manifest,
    replaySource,
    shouldPrefetch,
    signals,
    startSeconds,
    status,
  ]);

  useEffect(
    () => () => {
      activeController.current?.abort();
      prefetchController.current?.abort();
      cache.clear();
    },
    [cache],
  );

  return {
    data,
    status,
    error,
    diagnostics: {
      cacheSize: cache.size,
      cacheMaxWindows,
      requestCount: requestCount.current,
      staleResponsesIgnored: staleResponsesIgnored.current,
      currentKey,
    },
  };
}
