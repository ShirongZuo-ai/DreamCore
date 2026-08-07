import { ChevronLeft, ChevronRight, LocateFixed } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type {
  ReplaySignalWindow,
  ReplaySource,
} from '../../services/replaySource';
import type {
  AlphaFeatureRecord,
  AnnotationWindowResponse,
  EventWindowResponse,
  SessionManifest,
} from '../../types';
import { UPlotTimeSeries } from '../charts/UPlotTimeSeries';
import { RealEEGWaveformPanel } from '../eeg/EEGWaveformPanel';
import { MissingDataState } from '../common/MissingDataState';

type ViewerConfig = {
  default_start_s: number;
  default_window_duration_s: number;
  window_duration_options_s: number[];
  display_max_points_per_signal: number;
};

type WindowData = {
  signals: ReplaySignalWindow[];
  annotations: AnnotationWindowResponse;
  features: AlphaFeatureRecord[];
  events: EventWindowResponse;
};

function viewerConfig(manifest: SessionManifest): ViewerConfig | null {
  const raw = manifest.derived.alpha_power?.metadata?.viewer;
  if (typeof raw !== 'object' || raw === null) return null;
  const config = raw as Record<string, unknown>;
  if (
    typeof config.default_start_s !== 'number' ||
    typeof config.default_window_duration_s !== 'number' ||
    !Array.isArray(config.window_duration_options_s) ||
    !config.window_duration_options_s.every(
      (value) => typeof value === 'number',
    ) ||
    typeof config.display_max_points_per_signal !== 'number'
  ) {
    return null;
  }
  return config as ViewerConfig;
}

function alignedFeatureSeries(
  rows: AlphaFeatureRecord[],
  channels: string[],
  field: keyof AlphaFeatureRecord,
) {
  const timestamps = [
    ...new Set(rows.map((row) => (row.window_start_s + row.window_end_s) / 2)),
  ].sort((left, right) => left - right);
  return {
    timestamps,
    lines: channels.map((channel, index) => {
      const byTime = new Map(
        rows
          .filter((row) => row.channel === channel)
          .map((row) => [
            (row.window_start_s + row.window_end_s) / 2,
            row[field],
          ]),
      );
      return {
        label: channel,
        values: timestamps.map((timestamp) => {
          const value = byTime.get(timestamp);
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
}: {
  data: AnnotationWindowResponse;
  startSeconds: number;
  endSeconds: number;
}) {
  const colors: Record<string, string> = {
    W: '#60758a',
    N1: '#3db5d8',
    N2: '#39799b',
  };
  return (
    <section
      className="panel scroll-mt-20 overflow-hidden p-4"
      aria-label="Sleep stage overlay"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="eyebrow">Imported · Hypnogram</p>
          <h2 className="mt-1 font-semibold text-primary">
            Sleep-stage annotation
          </h2>
        </div>
        <span className="text-xs text-secondary">
          Imported sleep-stage annotation
        </span>
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
                left: `${((left - startSeconds) / (endSeconds - startSeconds)) * 100}%`,
                width: `${((right - left) / (endSeconds - startSeconds)) * 100}%`,
                background: colors[annotation.label] ?? '#354657',
              }}
              title={`${annotation.label} · ${annotation.raw_label ?? 'imported'} · ${left.toFixed(1)}–${right.toFixed(1)} s`}
            >
              {annotation.label}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[0.6875rem] text-secondary">
        {['W', 'N1', 'N2'].map((stage) => (
          <span key={stage} className="inline-flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ background: colors[stage] }}
            />
            {stage}
          </span>
        ))}
      </div>
    </section>
  );
}

function AlphaPanels({
  rows,
  channels,
}: {
  rows: AlphaFeatureRecord[];
  channels: string[];
}) {
  const absolute = alignedFeatureSeries(rows, channels, 'absolute_alpha_power');
  const relative = alignedFeatureSeries(rows, channels, 'relative_alpha_power');
  const change = alignedFeatureSeries(
    rows,
    channels,
    'alpha_change_from_baseline',
  );
  const drowsiness = alignedFeatureSeries(rows, channels, 'drowsiness_score');
  const confidence = alignedFeatureSeries(rows, channels, 'state_confidence');

  return (
    <section
      className="panel scroll-mt-20 overflow-hidden"
      aria-label="Alpha V1 derived metrics"
    >
      <div className="border-b border-line px-4 py-3">
        <p className="eyebrow">Derived · DreamCore Alpha V1</p>
        <h2 className="mt-1 font-semibold text-primary">
          Alpha and research state
        </h2>
      </div>
      {rows.length === 0 ? (
        <p className="p-5 text-sm text-secondary">
          Not computed / unavailable in this window.
        </p>
      ) : (
        <div className="grid min-w-0 gap-px bg-line lg:grid-cols-2">
          {[
            ['Absolute Alpha Power', absolute, 'µV²', 'alpha-absolute-chart'],
            ['Relative Alpha Power', relative, 'ratio', 'alpha-relative-chart'],
            [
              'Alpha change from baseline',
              change,
              'fraction',
              'alpha-change-chart',
            ],
          ].map(([title, series, unit, testId]) => (
            <div key={String(title)} className="min-w-0 bg-surface p-4">
              <p className="text-xs font-semibold text-primary">
                {String(title)}
              </p>
              <UPlotTimeSeries
                timestamps={(series as typeof absolute).timestamps}
                lines={(series as typeof absolute).lines}
                unit={String(unit)}
                height={150}
                maxPoints={500}
                testId={String(testId)}
              />
            </div>
          ))}
          <div className="min-w-0 bg-surface p-4">
            <p className="text-xs font-semibold text-primary">
              Drowsiness / state confidence
            </p>
            <UPlotTimeSeries
              timestamps={drowsiness.timestamps}
              lines={[
                ...drowsiness.lines,
                ...confidence.lines.map((line) => ({
                  ...line,
                  label: `${line.label} state confidence`,
                  dash: [3, 4],
                })),
              ]}
              unit="score [0,1]"
              height={150}
              maxPoints={500}
              testId="drowsiness-chart"
            />
          </div>
          <div className="min-w-0 bg-surface p-4 lg:col-span-2">
            <p className="text-xs font-semibold text-primary">
              IAF and trend status
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {channels.map((channel) => {
                const latest = [...rows]
                  .reverse()
                  .find((row) => row.channel === channel);
                return (
                  <div
                    key={channel}
                    className="rounded-control bg-elevated p-3"
                  >
                    <p className="font-mono text-xs text-primary">{channel}</p>
                    <div className="mt-2 grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <p className="text-secondary">
                          Individual Alpha Frequency
                        </p>
                        <p className="mt-1 font-semibold text-primary">
                          {latest?.iaf_available &&
                          latest.individual_alpha_frequency_hz !== null
                            ? `${latest.individual_alpha_frequency_hz.toFixed(2)} Hz`
                            : 'Unavailable'}
                        </p>
                        {!latest?.iaf_available ? (
                          <p className="mt-0.5 text-[0.6875rem] text-warning">
                            No reliable alpha peak
                          </p>
                        ) : null}
                      </div>
                      <div>
                        <p className="text-secondary">
                          IAF confidence · Alpha trend
                        </p>
                        <p className="mt-1 font-semibold text-primary">
                          {latest?.iaf_confidence?.toFixed(3) ?? 'Unavailable'}{' '}
                          · {latest?.alpha_trend ?? 'unavailable'}
                        </p>
                        <p className="mt-0.5 text-[0.6875rem] text-secondary">
                          State confidence{' '}
                          {latest?.state_confidence?.toFixed(3) ??
                            'Unavailable'}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
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
}: {
  rows: AlphaFeatureRecord[];
  events: EventWindowResponse;
  channels: string[];
}) {
  const demandRows = rows.filter((row) => row.demand_available);
  const demand = alignedFeatureSeries(
    demandRows,
    channels,
    'stimulation_demand',
  );
  const ready = rows.some((row) => row.ready_to_remove);
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
          {events.events.length ? (
            events.events.map((event, index) => (
              <span
                key={`${event.timestamp}-${index}`}
                className="rounded-full border border-[#9b8cf4]/40 bg-[#9b8cf4]/10 px-2 py-1 font-mono text-[0.625rem] text-[#c8befb]"
              >
                {event.timestamp.toFixed(0)} s ·{' '}
                {event.event_type.replace('stimulation_', '')}
              </span>
            ))
          ) : (
            <span className="text-xs text-secondary">
              No simulated events in this window.
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
}: {
  manifest: SessionManifest;
  replaySource: ReplaySource;
}) {
  const config = useMemo(() => viewerConfig(manifest), [manifest]);
  const [startSeconds, setStartSeconds] = useState(
    config?.default_start_s ?? 0,
  );
  const [durationSeconds, setDurationSeconds] = useState(
    config?.default_window_duration_s ?? 0,
  );
  const [jumpValue, setJumpValue] = useState(
    String(config?.default_start_s ?? 0),
  );
  const [data, setData] = useState<WindowData | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const eegSignals = useMemo(
    () =>
      manifest.signals.filter(
        (signal) => signal.available && signal.modality === 'eeg',
      ),
    [manifest.signals],
  );
  const endSeconds = Math.min(
    startSeconds + durationSeconds,
    replaySource.getDuration(),
  );

  useEffect(() => {
    if (!config || durationSeconds <= 0) return;
    let active = true;
    setStatus('loading');
    setError(null);
    void (async () => {
      try {
        const [signals, annotations, derived, events] = await Promise.all([
          Promise.all(
            eegSignals.map((signal) =>
              replaySource.readSignalWindow(
                signal.id,
                startSeconds,
                endSeconds - startSeconds,
              ),
            ),
          ),
          replaySource.readAnnotations(startSeconds, endSeconds),
          manifest.capabilities.alpha_power.status === 'AVAILABLE'
            ? replaySource.readDerived('alpha_power', startSeconds, endSeconds)
            : Promise.resolve(null),
          replaySource.readEvents(startSeconds, endSeconds),
        ]);
        if (!active) return;
        setData({
          signals,
          annotations,
          features: derived?.records ?? [],
          events,
        });
        setStatus('ready');
      } catch (loadError) {
        if (!active) return;
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to read session window',
        );
        setStatus('error');
      }
    })();
    return () => {
      active = false;
    };
  }, [
    config,
    durationSeconds,
    eegSignals,
    endSeconds,
    manifest,
    replaySource,
    startSeconds,
  ]);

  if (!config) {
    return (
      <section className="panel p-5 text-sm text-secondary">
        Viewer configuration unavailable in this Session Package.
      </section>
    );
  }

  const channels = eegSignals.map((signal) => signal.channel_name);
  const moveTo = (next: number) => {
    const clipped = Math.max(
      0,
      Math.min(next, replaySource.getDuration() - durationSeconds),
    );
    setStartSeconds(clipped);
    setJumpValue(String(clipped));
  };

  return (
    <div className="min-w-0 space-y-4" data-testid="alpha-session-viewer">
      <section
        className="panel p-4"
        aria-label="Synchronized window navigation"
      >
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="eyebrow">Manual offline navigation</p>
            <h2 className="mt-1 font-semibold text-primary">
              Synchronized window
            </h2>
            <p
              className="mt-1 font-mono text-xs text-secondary"
              data-testid="window-range"
            >
              {startSeconds.toFixed(1)}–{endSeconds.toFixed(1)} s · no playback
              timer
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-secondary">
              Window duration
              <select
                aria-label="Window duration"
                value={durationSeconds}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setDurationSeconds(next);
                  const clipped = Math.max(
                    0,
                    Math.min(startSeconds, replaySource.getDuration() - next),
                  );
                  setStartSeconds(clipped);
                  setJumpValue(String(clipped));
                }}
                className="ml-2 min-h-10 rounded-control border border-line bg-canvas px-2 text-primary"
              >
                {config.window_duration_options_s.map((duration) => (
                  <option key={duration} value={duration}>
                    {duration} s
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => moveTo(startSeconds - durationSeconds)}
              className="inline-flex min-h-10 items-center gap-1 rounded-control border border-line px-3 text-xs text-primary"
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <button
              type="button"
              onClick={() => moveTo(startSeconds + durationSeconds)}
              className="inline-flex min-h-10 items-center gap-1 rounded-control border border-line px-3 text-xs text-primary"
            >
              Next <ChevronRight size={14} />
            </button>
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
              onClick={() => moveTo(Number(jumpValue))}
              className="inline-flex min-h-10 items-center gap-1 rounded-control bg-accent px-3 text-xs font-semibold text-canvas"
            >
              <LocateFixed size={14} /> Jump
            </button>
            {data?.annotations.annotations
              .map((annotation) => annotation.start_seconds)
              .filter((value, index, values) => values.indexOf(value) === index)
              .map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => moveTo(value)}
                  className="sr-only"
                >
                  Jump to annotation {value}
                </button>
              ))}
          </div>
        </div>
      </section>

      {status === 'loading' ? (
        <section
          className="panel grid min-h-48 place-items-center"
          role="status"
        >
          <p className="text-sm text-secondary">
            Loading bounded signal window…
          </p>
        </section>
      ) : null}
      {status === 'error' ? (
        <section className="panel border-danger/40 p-5" role="alert">
          <p className="font-semibold text-danger">HTTP window unavailable</p>
          <p className="mt-1 text-sm text-secondary">{error}</p>
        </section>
      ) : null}
      {status === 'ready' && data ? (
        <>
          {data.signals.length ? (
            <RealEEGWaveformPanel
              windows={data.signals}
              maxDisplayPoints={config.display_max_points_per_signal}
            />
          ) : (
            <MissingDataState
              label="EEG"
              capability={manifest.capabilities.eeg}
            />
          )}
          <StageTrack
            data={data.annotations}
            startSeconds={startSeconds}
            endSeconds={endSeconds}
          />
          <AlphaPanels rows={data.features} channels={channels} />
          <SimulatedControlPanel
            rows={data.features}
            events={data.events}
            channels={channels}
          />
        </>
      ) : null}
    </div>
  );
}
