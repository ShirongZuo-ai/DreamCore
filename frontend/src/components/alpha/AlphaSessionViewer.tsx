import {
  ChevronLeft,
  ChevronRight,
  LocateFixed,
  Pause,
  Play,
  RotateCcw,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type {
  AudioConfig,
  BaselineControls,
} from '../../audio/useSonificationAudio';
import { useReplayClock } from '../../replay/replayClock';
import { useReplayWindow } from '../../replay/useReplayWindow';
import { WakeMusicPanel } from '../wakeMusic/WakeMusicPanel';
import {
  HttpReplaySource,
  type ReplaySource,
} from '../../services/replaySource';
import type { AutomaticAnalysisApi } from '../../services/automaticAnalysisApi';
import {
  kComplexApi as defaultKComplexApi,
  type KComplexApi,
  type KComplexEvent,
  type KComplexPayload,
} from '../../services/kComplexApi';
import type {
  AlphaFeatureRecord,
  AnnotationWindowResponse,
  EventWindowResponse,
  SessionManifest,
} from '../../types';
import {
  alphaAnalysisCoverage,
  emptyAlphaWindowMessage,
  productIafIsReliable,
  reachedAlphaFeatureRows,
  type AlphaAnalysisCoverage,
} from '../../lib/alphaReplayDiagnostics';
import { UPlotTimeSeries, type TimeMarker } from '../charts/UPlotTimeSeries';
import { MissingDataState } from '../common/MissingDataState';
import { RealEEGWaveformPanel } from '../eeg/EEGWaveformPanel';
import {
  EOGSignalPanel,
  EyeMovementFeaturePanel,
  SonificationPanel,
} from '../eyeMovement/EyeMovementPanels';
import { EogValidationPanel } from '../eyeMovement/EogValidationPanel';
import { SleepInsightsPanel } from '../insights/SleepInsightsPanel';
import { useAutomaticAnalysis } from '../../hooks/useAutomaticAnalysis';

type ViewerConfig = {
  default_start_s: number;
  default_time_s: number;
  default_window_duration_s: number;
  window_duration_options_s: number[];
  display_max_points_per_signal: number;
  feature_timestamp_semantics: 'window_end';
  stage_jump_time_s: number | null;
  activity_jump_time_s?: number | null;
  audio?: AudioConfig;
  baseline_controls?: BaselineControls;
  replay: {
    enabled: boolean;
    tick_interval_ms: number;
    default_speed: number;
    speed_options: number[];
    cache_max_windows: number;
    prefetch_threshold_fraction: number;
    seek_cursor_fraction: number;
    intervention_notice_duration_ms: number;
    intervention_marker_color: string;
    provenance_notice: string;
  };
};

type SimulatedIntervention = TimeMarker & {
  eventType: 'simulated_intervention_marker';
  provenanceNotice: string;
};

function viewerConfig(manifest: SessionManifest): ViewerConfig | null {
  const raw =
    manifest.derived.eye_movement_activity_v1?.metadata?.viewer ??
    manifest.derived.alpha_power?.metadata?.viewer;
  if (!raw || typeof raw !== 'object') return null;
  const config = raw as Record<string, unknown>;
  const replay = config.replay as Record<string, unknown> | undefined;
  if (
    typeof config.default_start_s !== 'number' ||
    typeof config.default_time_s !== 'number' ||
    typeof config.default_window_duration_s !== 'number' ||
    !Array.isArray(config.window_duration_options_s) ||
    !config.window_duration_options_s.every(
      (value) => typeof value === 'number' && value > 0,
    ) ||
    typeof config.display_max_points_per_signal !== 'number' ||
    config.feature_timestamp_semantics !== 'window_end' ||
    !(
      typeof config.stage_jump_time_s === 'number' ||
      config.stage_jump_time_s === null
    ) ||
    !replay ||
    typeof replay.enabled !== 'boolean' ||
    typeof replay.tick_interval_ms !== 'number' ||
    replay.tick_interval_ms <= 0 ||
    typeof replay.default_speed !== 'number' ||
    replay.default_speed <= 0 ||
    !Array.isArray(replay.speed_options) ||
    !replay.speed_options.every(
      (value) => typeof value === 'number' && value > 0,
    ) ||
    !replay.speed_options.includes(replay.default_speed) ||
    typeof replay.cache_max_windows !== 'number' ||
    replay.cache_max_windows <= 0 ||
    typeof replay.prefetch_threshold_fraction !== 'number' ||
    replay.prefetch_threshold_fraction <= 0 ||
    replay.prefetch_threshold_fraction >= 1 ||
    typeof replay.seek_cursor_fraction !== 'number' ||
    replay.seek_cursor_fraction < 0 ||
    replay.seek_cursor_fraction >= 1 ||
    typeof replay.intervention_notice_duration_ms !== 'number' ||
    typeof replay.intervention_marker_color !== 'string' ||
    typeof replay.provenance_notice !== 'string'
  ) {
    return null;
  }
  return config as ViewerConfig;
}

function featureSeries(
  rows: AlphaFeatureRecord[],
  channels: string[],
  field: keyof AlphaFeatureRecord,
  currentTime: number,
) {
  const timestamps = [...new Set(rows.map((row) => row.window_end_s))].sort(
    (left, right) => left - right,
  );
  return {
    timestamps,
    lines: channels.map((channel, index) => {
      const values = new Map(
        rows
          .filter((row) => row.channel === channel)
          .map((row) => [
            row.window_end_s,
            row.window_end_s <= currentTime ? row[field] : null,
          ]),
      );
      return {
        label: channel,
        values: timestamps.map((timestamp) => {
          const value = values.get(timestamp);
          return typeof value === 'number' ? value : null;
        }),
        stroke: index === 0 ? '#3db5d8' : '#9b8cf4',
        dash: index === 0 ? undefined : [8, 5],
      };
    }),
  };
}

function StageTrack({
  data,
  startSeconds,
  endSeconds,
  currentTime,
  markers,
}: {
  data: AnnotationWindowResponse;
  startSeconds: number;
  endSeconds: number;
  currentTime: number;
  markers: readonly SimulatedIntervention[];
}) {
  const colors: Record<string, string> = {
    W: '#60758a',
    N1: '#3db5d8',
    N2: '#39799b',
    N3: '#2f5472',
    REM: '#9b8cf4',
    UNKNOWN: '#354657',
    MOVEMENT: '#b8844b',
  };
  const currentStage = data.annotations.find(
    (annotation) =>
      annotation.start_seconds <= currentTime &&
      currentTime < annotation.start_seconds + annotation.duration_seconds,
  );
  const position = (time: number) =>
    `${((time - startSeconds) / (endSeconds - startSeconds)) * 100}%`;
  return (
    <section
      className="panel overflow-hidden p-4"
      aria-label="Sleep stage overlay"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="eyebrow">Imported · Hypnogram</p>
          <h2 className="mt-1 font-semibold text-primary">
            Sleep-stage annotation
          </h2>
        </div>
        <div className="text-right text-xs text-secondary">
          <p>Imported sleep-stage annotation</p>
          <p
            className="mt-1 font-semibold text-primary"
            data-testid="current-imported-stage"
          >
            Current imported stage: {currentStage?.label ?? 'Unavailable'}
          </p>
        </div>
      </div>
      <div className="relative mt-3 h-11 overflow-hidden rounded-control border border-line bg-canvas">
        {data.annotations.map((annotation, index) => {
          const left = Math.max(annotation.start_seconds, startSeconds);
          const right = Math.min(
            annotation.start_seconds + annotation.duration_seconds,
            endSeconds,
          );
          if (right <= left) return null;
          return (
            <div
              key={`${annotation.start_seconds}-${index}`}
              className="absolute inset-y-0 grid place-items-center border-r border-canvas/40 text-[0.625rem] font-semibold text-primary"
              style={{
                left: position(left),
                width: `${((right - left) / (endSeconds - startSeconds)) * 100}%`,
                background: colors[annotation.label] ?? '#354657',
              }}
              title={`${annotation.label} · ${annotation.raw_label ?? 'imported'}`}
            >
              {annotation.label}
            </div>
          );
        })}
        <div
          className="pointer-events-none absolute inset-y-0 z-20 w-px bg-white/80"
          style={{ left: position(currentTime) }}
          aria-label={`Offline replay cursor at ${currentTime.toFixed(2)} seconds`}
        />
        {markers
          .filter(
            (marker) =>
              marker.timestamp >= startSeconds &&
              marker.timestamp <= endSeconds,
          )
          .map((marker) => (
            <div
              key={marker.id}
              className="pointer-events-none absolute inset-y-0 z-30 w-0.5"
              style={{
                left: position(marker.timestamp),
                backgroundColor: marker.color,
              }}
              data-provenance="simulated"
            />
          ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[0.6875rem] text-secondary">
        {['W', 'N1', 'N2', 'N3', 'REM', 'UNKNOWN', 'MOVEMENT'].map((stage) => (
          <span key={stage} className="inline-flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ background: colors[stage] }}
            />
            {stage}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5 text-warning">
          <span className="h-2.5 w-0.5 bg-warning" /> Simulated intervention
        </span>
      </div>
    </section>
  );
}

function AlphaPanels({
  rows,
  channels,
  coverage,
  currentTime,
  startSeconds,
  endSeconds,
  markers,
}: {
  rows: AlphaFeatureRecord[];
  channels: string[];
  coverage: AlphaAnalysisCoverage | null;
  currentTime: number;
  startSeconds: number;
  endSeconds: number;
  markers: readonly SimulatedIntervention[];
}) {
  const primaryChannel = channels[0] ?? rows[0]?.channel ?? 'Unavailable';
  const series = useMemo(
    () => ({
      absolute: featureSeries(
        rows,
        channels,
        'absolute_alpha_power',
        currentTime,
      ),
      relative: featureSeries(
        rows,
        channels,
        'relative_alpha_power',
        currentTime,
      ),
      change: featureSeries(
        rows,
        channels,
        'alpha_change_from_baseline',
        currentTime,
      ),
      drowsiness: featureSeries(
        rows,
        channels,
        'drowsiness_score',
        currentTime,
      ),
      confidence: featureSeries(
        rows,
        channels,
        'state_confidence',
        currentTime,
      ),
    }),
    [channels, currentTime, rows],
  );
  const reached = reachedAlphaFeatureRows(rows, currentTime);
  const primaryLatest = [...reached]
    .reverse()
    .find((row) => row.channel === primaryChannel);
  const reliableIaf = productIafIsReliable(primaryLatest, coverage);
  const featureCadenceSeconds = useMemo(() => {
    const times = [...new Set(rows.map((row) => row.window_end_s))].sort(
      (left, right) => left - right,
    );
    const intervals = times
      .slice(1)
      .map((time, index) => time - times[index])
      .filter((value) => value > 0);
    return intervals.length ? Math.min(...intervals) : null;
  }, [rows]);
  const charts = [
    ['Absolute Alpha', series.absolute, 'µV²', 'alpha-absolute-chart'],
    ['Relative Alpha', series.relative, 'ratio', 'alpha-relative-chart'],
  ] as const;
  const contextStartSeconds = coverage
    ? Math.max(
        coverage.evaluationStartSeconds,
        currentTime - coverage.productDisplayContextSeconds,
      )
    : startSeconds;
  const contextEndSeconds = Math.max(
    contextStartSeconds + (coverage?.stepSeconds ?? endSeconds - startSeconds),
    currentTime,
  );
  return (
    <section
      className="panel overflow-hidden"
      aria-label="Alpha V1 derived metrics"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="eyebrow">Derived · DreamCore Alpha V1</p>
          <h2 className="mt-1 font-semibold text-primary">Alpha Activity</h2>
          <p className="mt-1 text-xs text-secondary">
            Primary signal{' '}
            <span className="font-mono text-primary">{primaryChannel}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3 text-right text-[0.6875rem] text-secondary">
          {channels.map((channel) => (
            <span key={channel} className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-accent" />
              {channel}
            </span>
          ))}
          <div>
            <p>
              Alpha context {contextStartSeconds.toFixed(1)}–
              {contextEndSeconds.toFixed(1)} s · cursor {currentTime.toFixed(2)}{' '}
              s
            </p>
            <p>
              Discrete observed points · no physiological interpolation
              {featureCadenceSeconds !== null
                ? ` · ${featureCadenceSeconds.toFixed(0)} s cadence`
                : ''}
            </p>
            <p
              data-testid="visible-feature-count"
              data-current-feature-time={
                reached.length
                  ? Math.max(...reached.map((row) => row.window_end_s))
                  : ''
              }
              data-total-session-feature-rows={coverage?.featureRowCount ?? ''}
            >
              Observed feature points: {reached.length}
            </p>
          </div>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="p-5 text-sm text-secondary">
          {emptyAlphaWindowMessage(coverage, currentTime)}
        </p>
      ) : (
        <div className="grid min-w-0 gap-px bg-line lg:grid-cols-2">
          {charts.map(([title, chart, unit, testId]) => (
            <div key={title} className="min-w-0 bg-surface p-4">
              <p className="text-xs font-semibold text-primary">{title}</p>
              <UPlotTimeSeries
                timestamps={chart.timestamps}
                lines={chart.lines}
                unit={unit}
                height={150}
                maxPoints={500}
                testId={testId}
                cursorTimestamp={currentTime}
                xRange={[contextStartSeconds, contextEndSeconds]}
                revealUntilTimestamp={currentTime}
                showPoints
                connectPoints={false}
                markers={markers}
              />
            </div>
          ))}
          <div className="min-w-0 bg-surface p-4 lg:col-span-2">
            <div className="grid gap-3 sm:grid-cols-3">
              <div
                className="rounded-control bg-elevated p-3 text-xs"
                data-testid="product-iaf"
              >
                <p className="text-secondary">Peak / IAF</p>
                <p className="mt-1 font-semibold text-primary">
                  {reliableIaf &&
                  typeof primaryLatest?.individual_alpha_frequency_hz ===
                    'number'
                    ? `${primaryLatest.individual_alpha_frequency_hz.toFixed(2)} Hz`
                    : 'No clear Alpha peak'}
                </p>
              </div>
              <div className="rounded-control bg-elevated p-3 text-xs">
                <p className="text-secondary">Trend</p>
                <p className="mt-1 font-semibold capitalize text-primary">
                  {primaryLatest?.alpha_trend ?? 'Unavailable'}
                </p>
              </div>
              <div className="rounded-control bg-elevated p-3 text-xs">
                <p className="text-secondary">Activity confidence</p>
                <p className="mt-1 font-semibold text-primary">
                  {primaryLatest?.state_confidence?.toFixed(3) ?? 'Unavailable'}
                </p>
              </div>
            </div>
            <details className="mt-3 rounded-control border border-line bg-elevated p-3 text-xs">
              <summary className="cursor-pointer font-semibold text-primary">
                Advanced Alpha diagnostics
              </summary>
              <div className="mt-3 grid gap-2 text-secondary sm:grid-cols-2">
                <p>
                  Spectral peak candidate:{' '}
                  <span className="font-mono text-primary">
                    {primaryLatest?.individual_alpha_frequency_hz?.toFixed(2) ??
                      'NA'}{' '}
                    Hz
                  </span>
                </p>
                <p>
                  IAF confidence:{' '}
                  <span className="font-mono text-primary">
                    {primaryLatest?.iaf_confidence?.toFixed(3) ?? 'NA'}
                  </span>
                </p>
                <p>
                  Product display criterion:{' '}
                  <span className="font-mono text-primary">
                    {coverage?.productDisplayMinIafConfidence?.toFixed(3) ??
                      'not declared'}
                  </span>
                </p>
                <p>
                  Peak status:{' '}
                  <span className="text-primary">
                    {primaryLatest?.iaf_reason ??
                      (reliableIaf
                        ? 'clear'
                        : 'below product confidence criterion')}
                  </span>
                </p>
              </div>
            </details>
          </div>
        </div>
      )}
    </section>
  );
}

function SimulatedControlPanel({
  rows,
  events,
  channels,
  currentTime,
  startSeconds,
  endSeconds,
  markers,
}: {
  rows: AlphaFeatureRecord[];
  events: EventWindowResponse;
  channels: string[];
  currentTime: number;
  startSeconds: number;
  endSeconds: number;
  markers: readonly SimulatedIntervention[];
}) {
  const demand = featureSeries(
    rows.filter((row) => row.demand_available),
    channels,
    'stimulation_demand',
    currentTime,
  );
  const reachedEvents = events.events.filter(
    (event) => event.timestamp <= currentTime,
  );
  const ready = rows.some(
    (row) => row.window_end_s <= currentTime && row.ready_to_remove,
  );
  return (
    <section
      className="panel overflow-hidden border-[#9b8cf4]/40"
      aria-label="Simulated control demand"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="eyebrow text-[#b8acf8]">
            Simulated · Research control quantity
          </p>
          <h2 className="mt-1 font-semibold text-primary">
            SIMULATED CONTROL DEMAND
          </h2>
          <p className="mt-1 text-xs font-semibold text-warning">
            NOT ULTRASOUND DOSE
          </p>
        </div>
        <span className="rounded-full border border-line px-2.5 py-1 text-xs text-secondary">
          ready_to_remove: {ready ? 'true' : 'false'}
        </span>
      </div>
      <div className="p-4">
        {demand.timestamps.length ? (
          <UPlotTimeSeries
            timestamps={demand.timestamps}
            lines={demand.lines.map((line) => ({ ...line, stroke: '#9b8cf4' }))}
            unit="demand [0,1]"
            height={160}
            maxPoints={500}
            testId="simulated-demand-chart"
            cursorTimestamp={currentTime}
            xRange={[startSeconds, endSeconds]}
            revealUntilTimestamp={currentTime}
            extendLastValueToCursor
            markers={markers}
            showMarkerLabels
          />
        ) : (
          <p className="text-sm text-secondary">
            Demand unavailable / held in this window.
          </p>
        )}
        <div
          className="mt-3 flex flex-wrap gap-2"
          aria-label="Simulated event markers"
        >
          {reachedEvents.length ? (
            reachedEvents.map((event, index) => (
              <span
                key={`${event.timestamp}-${index}`}
                className="rounded-full border border-[#9b8cf4]/40 bg-[#9b8cf4]/10 px-2 py-1 font-mono text-[0.625rem] text-[#c8befb]"
                data-provenance="simulated"
              >
                {event.timestamp.toFixed(0)} s ·{' '}
                {event.event_type.replace('stimulation_', '')}
              </span>
            ))
          ) : (
            <span className="text-xs text-secondary">
              No reached simulated events in this window.
            </span>
          )}
        </div>
      </div>
    </section>
  );
}

export function AlphaSessionViewer({
  manifest,
  replaySource,
  analysisApi,
  kComplexApi,
}: {
  manifest: SessionManifest;
  replaySource: ReplaySource;
  analysisApi?: AutomaticAnalysisApi;
  kComplexApi?: KComplexApi;
}) {
  const config = useMemo(() => viewerConfig(manifest), [manifest]);
  if (!config) {
    return (
      <section className="panel p-5 text-sm text-secondary">
        Viewer configuration unavailable in this Session Package.
      </section>
    );
  }
  return (
    <ConfiguredAlphaSessionViewer
      key={manifest.session.session_id}
      manifest={manifest}
      replaySource={replaySource}
      config={config}
      analysisApi={analysisApi}
      kComplexApi={kComplexApi}
    />
  );
}

function ConfiguredAlphaSessionViewer({
  manifest: initialManifest,
  replaySource,
  config,
  analysisApi,
  kComplexApi: providedKComplexApi,
}: {
  manifest: SessionManifest;
  replaySource: ReplaySource;
  config: ViewerConfig;
  analysisApi?: AutomaticAnalysisApi;
  kComplexApi?: KComplexApi;
}) {
  const analysisStatus = useAutomaticAnalysis({
    sessionId: initialManifest.session.session_id,
    enabled: Boolean(analysisApi) || replaySource instanceof HttpReplaySource,
    ...(analysisApi ? { api: analysisApi } : {}),
  });
  const eyeMovementReady =
    analysisStatus?.features.eye_movement.state === 'READY';
  const alphaReady = analysisStatus?.features.alpha.state === 'READY';
  const eyeDescriptorMetadata =
    analysisStatus?.features.eye_movement.descriptor_metadata;
  const alphaDescriptorMetadata =
    analysisStatus?.features.alpha.descriptor_metadata;
  const eyeDescriptorMetadataKey = JSON.stringify(
    eyeDescriptorMetadata ?? null,
  );
  const alphaDescriptorMetadataKey = JSON.stringify(
    alphaDescriptorMetadata ?? null,
  );
  const manifest = useMemo(
    () =>
      productManifest(
        initialManifest,
        eyeMovementReady,
        alphaReady,
        eyeDescriptorMetadata,
        alphaDescriptorMetadata,
      ),
    // Keep the effective manifest stable while progress polling updates.
    // Replay window requests should restart only when derived availability changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stable serialized metadata keys
    [
      alphaDescriptorMetadataKey,
      alphaReady,
      eyeDescriptorMetadataKey,
      eyeMovementReady,
      initialManifest,
    ],
  );
  const duration = replaySource.getDuration();
  const clock = useReplayClock({
    durationSeconds: duration,
    startTimeSeconds: config.default_time_s,
    defaultSpeed: config.replay.default_speed,
    tickIntervalMs: config.replay.tick_interval_ms,
  });
  const currentTime = clock.state.sessionTimeSeconds;
  const kComplexApi = providedKComplexApi ?? defaultKComplexApi;
  const [kComplexPayload, setKComplexPayload] =
    useState<KComplexPayload | null>(null);
  const [selectedKComplex, setSelectedKComplex] =
    useState<KComplexEvent | null>(null);
  const [selectedEyeMovement, setSelectedEyeMovement] = useState<string | null>(
    null,
  );
  const refreshKComplex = useCallback(async () => {
    const payload = await kComplexApi.get(initialManifest.session.session_id);
    setKComplexPayload(payload);
  }, [initialManifest.session.session_id, kComplexApi]);
  useEffect(() => {
    if (analysisStatus?.features.k_complex.state !== 'READY') return;
    const controller = new AbortController();
    void kComplexApi
      .get(initialManifest.session.session_id, controller.signal)
      .then(setKComplexPayload)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setKComplexPayload(null);
        }
      });
    return () => controller.abort();
  }, [
    analysisStatus?.features.k_complex.state,
    initialManifest.session.session_id,
    kComplexApi,
  ]);
  const failReplay = clock.fail;
  const [startSeconds, setStartSeconds] = useState(config.default_start_s);
  const [durationSeconds, setDurationSeconds] = useState(
    config.default_window_duration_s,
  );
  const [jumpValue, setJumpValue] = useState(String(config.default_time_s));
  const [markers, setMarkers] = useState<SimulatedIntervention[]>([]);
  const [activeMarker, setActiveMarker] =
    useState<SimulatedIntervention | null>(null);
  const markerSequence = useRef(0);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const eegSignals = useMemo(
    () =>
      manifest.signals.filter(
        (signal) => signal.available && signal.modality === 'eeg',
      ),
    [manifest.signals],
  );
  const eogSignals = useMemo(
    () =>
      manifest.signals.filter(
        (signal) => signal.available && signal.modality === 'eog',
      ),
    [manifest.signals],
  );
  const signals = useMemo(
    () => [...eegSignals, ...eogSignals],
    [eegSignals, eogSignals],
  );
  const channels = useMemo(
    () => eegSignals.map((signal) => signal.channel_name),
    [eegSignals],
  );
  const coverage = useMemo(
    () => alphaAnalysisCoverage(manifest.derived.alpha_power),
    [manifest.derived.alpha_power],
  );
  const alphaChannels = useMemo(() => {
    if (coverage?.channels.length) return coverage.channels;
    return channels;
  }, [channels, coverage]);
  const endSeconds = Math.min(startSeconds + durationSeconds, duration);
  const shouldPrefetch =
    clock.state.status === 'playing' &&
    currentTime >=
      startSeconds +
        durationSeconds * config.replay.prefetch_threshold_fraction;
  const windowState = useReplayWindow({
    replaySource,
    manifest,
    signals,
    startSeconds,
    durationSeconds: endSeconds - startSeconds,
    cacheMaxWindows: config.replay.cache_max_windows,
    shouldPrefetch,
  });
  const reachedRows = reachedAlphaFeatureRows(
    windowState.data?.features ?? [],
    currentTime,
  );
  const currentFeatureTime = reachedRows.length
    ? Math.max(...reachedRows.map((row) => row.window_end_s))
    : null;
  const currentTimeRef = useRef(currentTime);
  currentTimeRef.current = currentTime;

  useEffect(() => {
    if (!import.meta.env.DEV || windowState.status !== 'ready') return;
    const rows = windowState.data?.features ?? [];
    const firstFetchedFeatureTime = rows.length
      ? Math.min(...rows.map((row) => row.window_end_s))
      : null;
    const lastFetchedFeatureTime = rows.length
      ? Math.max(...rows.map((row) => row.window_end_s))
      : null;
    console.info('[DreamCore Alpha]', {
      session: manifest.session.session_id,
      cursorSeconds: currentTimeRef.current,
      samplesAvailable: Object.fromEntries(
        (windowState.data?.signals ?? []).map((signal) => [
          signal.signal.channel_name,
          signal.samples.length,
        ]),
      ),
      boundedWindowSeconds: [startSeconds, endSeconds],
      analysisWindowSeconds: coverage?.analysisWindowSeconds ?? null,
      strideSeconds: coverage?.stepSeconds ?? null,
      totalFeatureRows: coverage?.featureRowCount ?? null,
      fetchedFeatureRows: rows.length,
      firstFeatureTimeSeconds: coverage?.firstFeatureTimeSeconds ?? null,
      lastFeatureTimeSeconds: coverage?.lastFeatureTimeSeconds ?? null,
      firstFetchedFeatureTimeSeconds: firstFetchedFeatureTime,
      lastFetchedFeatureTimeSeconds: lastFetchedFeatureTime,
      reachedRows: reachedRows.length,
      currentFeatureTimeSeconds: currentFeatureTime,
      ...(coverage?.featureRowCount === 0
        ? {
            attemptedWindows: coverage.attemptedWindows,
            acceptedWindows: coverage.acceptedWindows,
            rejectedWindows: coverage.rejectedWindows,
            rejectionReasons: coverage.rejectionReasons,
          }
        : {}),
    });
  }, [
    coverage,
    currentFeatureTime,
    endSeconds,
    manifest.session.session_id,
    reachedRows.length,
    startSeconds,
    windowState.data,
    windowState.status,
  ]);

  useEffect(() => {
    if (
      clock.state.status !== 'playing' ||
      currentTime < endSeconds ||
      endSeconds >= duration
    )
      return;
    setStartSeconds(endSeconds);
  }, [clock.state.status, currentTime, duration, endSeconds]);

  useEffect(() => {
    if (windowState.status === 'error' && windowState.error) {
      failReplay(windowState.error);
    }
  }, [failReplay, windowState.error, windowState.status]);

  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    },
    [],
  );

  const seek = (target: number, forceWindow = false) => {
    const clippedTime = Math.max(0, Math.min(target, duration));
    clock.seek(clippedTime);
    if (
      forceWindow ||
      clippedTime < startSeconds ||
      clippedTime >= endSeconds
    ) {
      const desiredStart =
        clippedTime - durationSeconds * config.replay.seek_cursor_fraction;
      setStartSeconds(
        Math.max(0, Math.min(desiredStart, duration - durationSeconds)),
      );
    }
    setJumpValue(String(clippedTime));
  };
  const focusKComplex = (event: KComplexEvent) => {
    const halfWindow = kComplexPayload?.analysis.focus_half_window_s ?? 0;
    const focusDuration = halfWindow * 2;
    const start = Math.max(
      0,
      Math.min(event.negative_trough_s - halfWindow, duration - focusDuration),
    );
    setSelectedKComplex(event);
    setDurationSeconds(focusDuration);
    setStartSeconds(start);
    clock.seek(event.negative_trough_s);
    setJumpValue(String(event.negative_trough_s));
  };
  const kComplexMarkers = useMemo<TimeMarker[]>(() => {
    if (!kComplexPayload) return [];
    const automatic = kComplexPayload.events
      .filter(
        (event) =>
          event.verification_status === 'accepted' ||
          event.event_id === selectedKComplex?.event_id,
      )
      .flatMap((event) => {
        if (event.event_id !== selectedKComplex?.event_id) {
          return [
            {
              id: event.event_id,
              timestamp: event.negative_trough_s,
              label: 'KC',
              color: '#e1aa5a',
              provenance: 'derived' as const,
            },
          ];
        }
        return [
          {
            id: `${event.event_id}:onset`,
            timestamp: event.onset_s,
            label: 'KC onset',
            color: '#91a4b7',
            provenance: 'derived' as const,
          },
          {
            id: `${event.event_id}:trough`,
            timestamp: event.negative_trough_s,
            label: 'KC trough',
            color: '#e1aa5a',
            provenance: 'derived' as const,
          },
          ...(event.positive_peak_s === null
            ? []
            : [
                {
                  id: `${event.event_id}:peak`,
                  timestamp: event.positive_peak_s,
                  label: 'KC positive peak',
                  color: '#9b8cf4',
                  provenance: 'derived' as const,
                },
              ]),
          {
            id: `${event.event_id}:end`,
            timestamp: event.end_s,
            label: 'KC end',
            color: '#91a4b7',
            provenance: 'derived' as const,
          },
        ];
      });
    return [
      ...automatic,
      ...kComplexPayload.manual_events.map((event) => ({
        id: event.manual_event_id,
        timestamp: event.negative_trough_s,
        label: 'Manual KC',
        color: '#f2c879',
        provenance: 'manual' as const,
      })),
    ];
  }, [kComplexPayload, selectedKComplex]);
  const moveWindow = (offset: number) => {
    const next = Math.max(
      0,
      Math.min(startSeconds + offset, duration - durationSeconds),
    );
    setStartSeconds(next);
    clock.seek(next);
    setJumpValue(String(next));
  };
  const markIntervention = () => {
    markerSequence.current += 1;
    const marker: SimulatedIntervention = {
      id: `${manifest.session.session_id}-simulated-${markerSequence.current}`,
      timestamp: currentTime,
      label: config.replay.provenance_notice,
      color: config.replay.intervention_marker_color,
      provenance: 'simulated',
      eventType: 'simulated_intervention_marker',
      provenanceNotice: config.replay.provenance_notice,
    };
    setMarkers((current) => [...current, marker]);
    setActiveMarker(marker);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(
      () => setActiveMarker(null),
      config.replay.intervention_notice_duration_ms,
    );
  };

  return (
    <div className="min-w-0 space-y-4" data-testid="alpha-session-viewer">
      <section className="panel p-4" aria-label="Recording source metadata">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Source recording</p>
            <h2 className="mt-1 font-semibold text-primary">
              {manifest.dataset.display_name} · {manifest.session.session_id}
            </h2>
          </div>
          <p className="font-mono text-xs text-secondary">
            {(manifest.recording.duration_seconds / 3600).toFixed(2)} h ·{' '}
            {manifest.dataset.version ?? 'version unavailable'}
          </p>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {manifest.signals.map((signal) => (
            <span
              key={signal.id}
              className="rounded-full border border-line px-2 py-1 font-mono text-[0.6875rem] text-secondary"
            >
              {signal.original_channel_name ?? signal.channel_name} ·{' '}
              {signal.canonical_role ?? 'OTHER'} · {signal.sampling_rate_hz} Hz
              · {signal.unit}
            </span>
          ))}
        </div>
        <p className="mt-3 text-[0.6875rem] text-secondary">
          Original labels and native sampling rates are retained. Canonical
          roles support cross-dataset navigation without replacing source
          montage metadata.
        </p>
      </section>
      <SleepInsightsPanel
        status={analysisStatus}
        sessionId={manifest.session.session_id}
        kComplex={kComplexPayload}
        selectedKComplex={selectedKComplex}
        currentTime={currentTime}
        kComplexApi={kComplexApi}
        onSelectKComplex={focusKComplex}
        onRefreshKComplex={refreshKComplex}
      />
      {analysisStatus?.features.wake_music_profile.state === 'READY' ||
      (!analysisStatus &&
        manifest.capabilities.eye_movement_activity.status === 'AVAILABLE') ? (
        <WakeMusicPanel
          sessionId={manifest.session.session_id}
          preparedProfile={analysisStatus?.features.wake_music_profile.profile}
        />
      ) : null}
      {activeMarker ? (
        <section
          className="sticky top-16 z-40 rounded-card border border-warning/60 bg-[#2b2518] px-4 py-3 shadow-card"
          role="alert"
          data-provenance="simulated"
        >
          <p className="font-semibold text-warning">
            SIMULATED INTERVENTION MARKED · {activeMarker.timestamp.toFixed(2)}{' '}
            s
          </p>
          <p className="mt-1 text-xs text-primary">
            {activeMarker.provenanceNotice}
          </p>
          <p className="mt-1 text-xs text-secondary">
            No hardware command was sent. Observed EEG and derived Alpha values
            remain unchanged; observed EOG and eye-movement features are also
            unchanged.
          </p>
        </section>
      ) : null}

      <section className="panel p-4" aria-label="Offline replay controls">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="eyebrow">OFFLINE PUBLIC EEG REPLAY</p>
            <h2 className="mt-1 font-semibold text-primary">
              Authoritative synchronized replay clock
            </h2>
            <p
              className="mt-1 font-mono text-xs text-secondary"
              data-testid="window-range"
            >
              window {startSeconds.toFixed(1)}–{endSeconds.toFixed(1)} s ·
              cursor {currentTime.toFixed(2)} s · {clock.state.status}{' '}
              {clock.state.playbackSpeed}×
            </p>
            <p
              className="mt-1 text-[0.6875rem] text-secondary"
              data-testid="replay-diagnostics"
            >
              bounded cache ≤ {windowState.diagnostics.cacheMaxWindows} windows
              · requests {windowState.diagnostics.requestCount}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <button
              type="button"
              onClick={
                clock.state.status === 'playing' ? clock.pause : clock.play
              }
              className="inline-flex min-h-10 items-center gap-1.5 rounded-control bg-accent px-3 text-xs font-semibold text-canvas"
            >
              {clock.state.status === 'playing' ? (
                <Pause size={14} />
              ) : (
                <Play size={14} />
              )}
              {clock.state.status === 'playing'
                ? 'Pause replay'
                : 'Start replay'}
            </button>
            <button
              type="button"
              onClick={() => {
                clock.restart();
                setStartSeconds(config.default_start_s);
                setJumpValue(String(config.default_time_s));
              }}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-control border border-line px-3 text-xs text-primary"
            >
              <RotateCcw size={14} /> Restart
            </button>
            <label className="text-xs text-secondary">
              Playback speed
              <select
                aria-label="Replay speed"
                value={clock.state.playbackSpeed}
                onChange={(event) => clock.setSpeed(Number(event.target.value))}
                className="ml-2 min-h-10 rounded-control border border-line bg-canvas px-2 text-primary"
              >
                {config.replay.speed_options.map((speed) => (
                  <option key={speed} value={speed}>
                    {speed}×
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-secondary">
              Window duration
              <select
                aria-label="Window duration"
                value={durationSeconds}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setDurationSeconds(next);
                  const nextStart = Math.max(
                    0,
                    Math.min(
                      currentTime - next * config.replay.seek_cursor_fraction,
                      duration - next,
                    ),
                  );
                  setStartSeconds(nextStart);
                  clock.seek(currentTime);
                }}
                className="ml-2 min-h-10 rounded-control border border-line bg-canvas px-2 text-primary"
              >
                {config.window_duration_options_s.map((value) => (
                  <option key={value} value={value}>
                    {value} s
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => moveWindow(-durationSeconds)}
              className="inline-flex min-h-10 items-center gap-1 rounded-control border border-line px-3 text-xs text-primary"
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <button
              type="button"
              onClick={() => moveWindow(durationSeconds)}
              className="inline-flex min-h-10 items-center gap-1 rounded-control border border-line px-3 text-xs text-primary"
            >
              Next <ChevronRight size={14} />
            </button>
            {config.stage_jump_time_s !== null ? (
              <button
                type="button"
                onClick={() => seek(config.stage_jump_time_s!, true)}
                className="inline-flex min-h-10 items-center gap-1 rounded-control border border-accent/50 px-3 text-xs text-accent"
              >
                Jump to W→N1
              </button>
            ) : null}
            {typeof config.activity_jump_time_s === 'number' ? (
              <button
                type="button"
                onClick={() => seek(config.activity_jump_time_s!, true)}
                className="inline-flex min-h-10 items-center gap-1 rounded-control border border-accent/50 px-3 text-xs text-accent"
              >
                Jump to EOG activity
              </button>
            ) : null}
            <label className="text-xs text-secondary">
              Jump to seconds
              <input
                aria-label="Jump to seconds"
                type="number"
                value={jumpValue}
                onChange={(event) => setJumpValue(event.target.value)}
                className="ml-2 min-h-10 w-28 rounded-control border border-line bg-canvas px-2 font-mono text-primary"
              />
            </label>
            <button
              type="button"
              onClick={() => seek(Number(jumpValue), true)}
              className="inline-flex min-h-10 items-center gap-1 rounded-control bg-accent px-3 text-xs font-semibold text-canvas"
            >
              <LocateFixed size={14} /> Seek
            </button>
            <button
              type="button"
              onClick={markIntervention}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-control border border-warning/60 bg-warning/10 px-3 text-xs font-semibold text-warning"
            >
              <Zap size={14} /> Mark simulated intervention
            </button>
          </div>
        </div>
        <label className="mt-4 block text-xs text-secondary">
          Session seek
          <input
            aria-label="Session seek"
            type="range"
            min={0}
            max={duration}
            step={config.replay.tick_interval_ms / 1000}
            value={currentTime}
            onChange={(event) => seek(Number(event.target.value), true)}
            className="mt-2 block w-full accent-accent"
          />
        </label>
      </section>

      <section
        className="panel grid gap-px overflow-hidden bg-line text-sm sm:grid-cols-4"
        aria-label="Closed-loop provenance flow"
      >
        {[
          ['Raw', 'Recorded public EEG and EOG'],
          ['Imported', 'Sleep-stage annotation'],
          ['Derived', 'Available analyses only; missing results stay explicit'],
          ['Playback', 'Bounded local source windows'],
        ].map(([kind, detail]) => (
          <div key={kind} className="bg-surface p-3">
            <p className="eyebrow">{kind}</p>
            <p className="mt-1 text-xs text-secondary">{detail}</p>
          </div>
        ))}
        <p className="bg-surface p-3 text-xs text-warning sm:col-span-4">
          Derived panels appear only when computed artifacts exist. Audio
          controls never modify physiology. Intervention markers remain local
          simulations and never alter recorded signals.
        </p>
      </section>

      {windowState.status === 'loading' ? (
        <section
          className="panel grid min-h-48 place-items-center"
          role="status"
        >
          <p className="text-sm text-secondary">
            Loading bounded signal window…
          </p>
        </section>
      ) : null}
      {windowState.status === 'error' ? (
        <section className="panel border-danger/40 p-5" role="alert">
          <p className="font-semibold text-danger">HTTP window unavailable</p>
          <p className="mt-1 text-sm text-secondary">{windowState.error}</p>
        </section>
      ) : null}
      {windowState.status === 'ready' && windowState.data ? (
        <>
          {windowState.data.signals.some(
            (window) => window.signal.modality === 'eeg',
          ) ? (
            <RealEEGWaveformPanel
              windows={windowState.data.signals.filter((window) => {
                if (window.signal.modality !== 'eeg') return false;
                if (!selectedKComplex || !kComplexPayload) return true;
                return kComplexPayload.analysis.focus_signals.some(
                  (signal) => signal.signal_id === window.signal.id,
                );
              })}
              maxDisplayPoints={config.display_max_points_per_signal}
              replayCursorSeconds={currentTime}
              interventionMarkers={markers}
              kComplexMarkers={kComplexMarkers}
              focused={selectedKComplex !== null}
              onKComplexMarkerClick={(marker) => {
                const eventId = marker.id.split(':')[0];
                const event = kComplexPayload?.events.find(
                  (candidate) => candidate.event_id === eventId,
                );
                if (event) focusKComplex(event);
              }}
            />
          ) : (
            <MissingDataState
              label="EEG"
              capability={manifest.capabilities.eeg}
            />
          )}
          <StageTrack
            data={windowState.data.annotations}
            startSeconds={startSeconds}
            endSeconds={endSeconds}
            currentTime={currentTime}
            markers={markers}
          />
          {manifest.capabilities.eog.status === 'AVAILABLE' ? (
            <>
              <EOGSignalPanel
                windows={windowState.data.signals.filter(
                  (window) => window.signal.modality === 'eog',
                )}
                currentTime={currentTime}
                startSeconds={startSeconds}
                endSeconds={endSeconds}
                maxDisplayPoints={config.display_max_points_per_signal}
                interventionMarkers={markers}
                events={windowState.data.eyeMovementEvents}
                selectedEventId={selectedEyeMovement}
                onSelectEvent={(event) =>
                  setSelectedEyeMovement(event.event_id)
                }
              />
              {manifest.capabilities.eye_movement_activity.status ===
              'AVAILABLE' ? (
                <EyeMovementFeaturePanel
                  rows={windowState.data.eyeMovementFeatures}
                  events={windowState.data.eyeMovementEvents}
                  descriptor={manifest.derived.eye_movement_activity_v1}
                  currentTime={currentTime}
                  startSeconds={startSeconds}
                  endSeconds={endSeconds}
                  interventionMarkers={markers}
                  stages={windowState.data.annotations.annotations}
                  selectedEventId={selectedEyeMovement}
                  onSelectEvent={(event) =>
                    setSelectedEyeMovement(event.event_id)
                  }
                />
              ) : null}
              {manifest.capabilities.sonification_controls.status ===
                'AVAILABLE' &&
              config.audio &&
              config.baseline_controls ? (
                <SonificationPanel
                  rows={windowState.data.sonificationControls}
                  descriptor={manifest.derived.sonification_control_v1}
                  currentTime={currentTime}
                  startSeconds={startSeconds}
                  endSeconds={endSeconds}
                  replayStatus={clock.state.status}
                  audioConfig={config.audio}
                  baseline={config.baseline_controls}
                  interventionMarkers={markers}
                  onStartReplay={clock.play}
                />
              ) : null}
            </>
          ) : (
            <MissingDataState
              label="EOG"
              capability={manifest.capabilities.eog}
            />
          )}
          {manifest.capabilities.alpha_power.status === 'AVAILABLE' ? (
            <div className="pt-2">
              <div className="mb-3 px-1">
                <p className="eyebrow">RESEARCH / DIAGNOSTICS · SECONDARY</p>
                <h2 className="mt-1 font-semibold text-primary">
                  Alpha comparison and diagnostic controls
                </h2>
                <p className="mt-1 max-w-4xl text-xs text-secondary">
                  Alpha is shown only from a computed DreamCore artifact and is
                  not substituted for missing analysis.
                </p>
              </div>
              <AlphaPanels
                rows={windowState.data.features}
                channels={alphaChannels}
                coverage={coverage}
                currentTime={currentTime}
                startSeconds={startSeconds}
                endSeconds={endSeconds}
                markers={markers}
              />
            </div>
          ) : null}
          {manifest.capabilities.stimulation_demand.status === 'AVAILABLE' ? (
            <SimulatedControlPanel
              rows={windowState.data.features}
              events={windowState.data.events}
              channels={channels}
              currentTime={currentTime}
              startSeconds={startSeconds}
              endSeconds={endSeconds}
              markers={markers}
            />
          ) : null}
        </>
      ) : null}
      <EogValidationPanel
        sessionId={manifest.session.session_id}
        onFocus={(focusStart, focusEnd, timestamp) => {
          const focusDuration = focusEnd - focusStart;
          setDurationSeconds(focusDuration);
          setStartSeconds(focusStart);
          clock.seek(timestamp);
          setJumpValue(String(timestamp));
        }}
      />
    </div>
  );
}

function productManifest(
  manifest: SessionManifest,
  eyeMovementReady: boolean,
  alphaReady: boolean,
  eyeDescriptorMetadata?: Record<string, unknown>,
  alphaDescriptorMetadata?: Record<string, unknown>,
): SessionManifest {
  if (!eyeMovementReady && !alphaReady) return manifest;
  const next = structuredClone(manifest);
  const viewer =
    manifest.derived.eye_movement_activity_v1?.metadata?.viewer ??
    manifest.derived.alpha_power?.metadata?.viewer;
  if (eyeMovementReady) {
    next.capabilities.eye_movement_activity = {
      status: 'AVAILABLE',
      source: 'derived',
      derived_by: 'eye-movement-v1',
      version: 'eye-movement-v1',
    };
    next.capabilities.eye_movement_events = {
      status: 'AVAILABLE',
      source: 'derived',
      derived_by: 'eye-movement-v1',
      version: 'eye-movement-v1',
    };
    if (!next.derived.eye_movement_activity_v1?.available) {
      next.derived.eye_movement_activity_v1 = {
        available: true,
        source: 'derived',
        version: 'eye-movement-v1',
        metadata: { viewer, ...eyeDescriptorMetadata },
      };
    }
    if (!next.derived.eye_movement_events_v1?.available) {
      next.derived.eye_movement_events_v1 = {
        available: true,
        source: 'derived',
        version: 'eye-movement-v1',
        metadata: { viewer, ...eyeDescriptorMetadata },
      };
    }
  }
  if (alphaReady) {
    next.capabilities.alpha_power = {
      status: 'AVAILABLE',
      source: 'derived',
      derived_by: 'alpha-product-v1',
      version: 'alpha-product-v1',
    };
    if (!next.derived.alpha_power?.available) {
      next.derived.alpha_power = {
        available: true,
        source: 'derived',
        version: 'alpha-product-v1',
        metadata: { viewer, ...alphaDescriptorMetadata },
      };
    }
  }
  return next;
}
