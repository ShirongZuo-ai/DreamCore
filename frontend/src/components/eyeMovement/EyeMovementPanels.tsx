import { RotateCcw, Volume2, VolumeX } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  type AudioConfig,
  type BaselineControls,
  useSonificationAudio,
} from '../../audio/useSonificationAudio';
import { coverageState, derivedCoverage } from '../../lib/derivedCoverage';
import type { ReplaySignalWindow } from '../../services/replaySource';
import type {
  ContentDescriptor,
  EyeMovementEventRecord,
  EyeMovementFeatureRecord,
  SonificationControlFrameRecord,
  SonificationSource,
} from '../../types';
import { UPlotTimeSeries, type TimeMarker } from '../charts/UPlotTimeSeries';
import { PanelHeader } from '../common/PanelHeader';

function featureLine(
  rows: readonly EyeMovementFeatureRecord[],
  field: keyof EyeMovementFeatureRecord,
  currentTime: number,
  label: string,
  stroke: string,
) {
  return {
    label,
    stroke,
    values: rows.map((row) => {
      const value = row[field];
      return row.window_end_s <= currentTime &&
        typeof value === 'number' &&
        Number.isFinite(value)
        ? value
        : null;
    }),
  };
}

function eventMarkers(events: readonly EyeMovementEventRecord[]): TimeMarker[] {
  return events.map((event) => ({
    id: event.event_id,
    timestamp: event.timestamp,
    label: `Eye Movement Candidate · ${event.polarity} · confidence ${event.confidence.toFixed(2)}`,
    color: '#e1aa5a',
    provenance: 'derived',
  }));
}

export function EOGSignalPanel({
  windows,
  currentTime,
  startSeconds,
  endSeconds,
  maxDisplayPoints,
  interventionMarkers,
  events,
}: {
  windows: readonly ReplaySignalWindow[];
  currentTime: number;
  startSeconds: number;
  endSeconds: number;
  maxDisplayPoints: number;
  interventionMarkers: readonly TimeMarker[];
  events: readonly EyeMovementEventRecord[];
}) {
  const markers = useMemo(
    () => [...eventMarkers(events), ...interventionMarkers],
    [events, interventionMarkers],
  );
  if (!windows.length) return null;
  return (
    <section className="panel overflow-hidden" aria-label="EOG signal tracks">
      <div className="border-b border-line px-4 py-3.5">
        <PanelHeader
          title="EOG Signal"
          eyebrow="Primary research signal · shared session time"
          action={<span className="demo-chip">REAL PUBLIC SLEEP-EDF</span>}
        />
        <p className="mt-2 text-xs text-secondary">
          One differential channel is available. Polarity describes the recorded
          deflection; it does not establish left/right eye direction.
        </p>
      </div>
      <div className="grid gap-px bg-line lg:grid-cols-2">
        {windows.map((window) => {
          const isRaw = window.signal.source === 'raw';
          return (
            <div
              key={window.signal.id}
              className="min-w-0 bg-[#111d2a] p-4"
              data-testid={isRaw ? 'raw-eog-track' : 'filtered-eog-track'}
            >
              <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                <div>
                  <span className="eyebrow">{isRaw ? 'RAW' : 'DERIVED'}</span>
                  <strong className="ml-2 text-primary">
                    {window.signal.channel_name}
                  </strong>
                </div>
                <span className="font-mono text-secondary">
                  {window.signal.sampling_rate_hz} Hz · {window.signal.unit}
                </span>
              </div>
              <UPlotTimeSeries
                timestamps={window.timestamps ?? []}
                lines={[
                  {
                    label: window.signal.channel_name,
                    values: window.samples,
                    stroke: isRaw ? '#3db5d8' : '#9b8cf4',
                  },
                ]}
                unit={window.signal.unit}
                height={180}
                maxPoints={maxDisplayPoints}
                testId={isRaw ? 'raw-eog-uplot' : 'filtered-eog-uplot'}
                cursorTimestamp={currentTime}
                xRange={[startSeconds, endSeconds]}
                revealUntilTimestamp={currentTime}
                markers={markers}
              />
            </div>
          );
        })}
      </div>
      <p className="border-t border-line px-4 py-2.5 text-[0.6875rem] text-secondary">
        RAW remains unchanged · filtered EOG is a reproducible derived display
        signal · candidate markers never alter either track
      </p>
    </section>
  );
}

export function EyeMovementFeaturePanel({
  rows,
  events,
  descriptor,
  currentTime,
  startSeconds,
  endSeconds,
  interventionMarkers,
}: {
  rows: readonly EyeMovementFeatureRecord[];
  events: readonly EyeMovementEventRecord[];
  descriptor: ContentDescriptor | undefined;
  currentTime: number;
  startSeconds: number;
  endSeconds: number;
  interventionMarkers: readonly TimeMarker[];
}) {
  const coverage = derivedCoverage(descriptor);
  const state = coverageState(coverage, currentTime);
  const reached = rows.filter((row) => row.window_end_s <= currentTime);
  const latest = reached.reduce<EyeMovementFeatureRecord | null>(
    (current, row) =>
      current === null || row.window_end_s > current.window_end_s
        ? row
        : current,
    null,
  );
  const timestamps = rows.map((row) => row.window_end_s);
  const markers = useMemo(
    () => [...eventMarkers(events), ...interventionMarkers],
    [events, interventionMarkers],
  );
  const reachedEvents = events.filter(
    (event) => event.timestamp <= currentTime,
  );
  return (
    <section
      className="panel overflow-hidden border-accent/40"
      aria-label="Eye Movement derived features"
      data-testid="eye-movement-panel"
      data-coverage-state={state}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <p className="eyebrow text-accent">
            DERIVED · PRIMARY RESEARCH SIGNAL
          </p>
          <h2 className="mt-1 font-semibold text-primary">
            Eye Movement Activity
          </h2>
          <p className="mt-1 text-xs text-secondary">
            Activity and candidates are EOG-derived; they are not REM or dream
            labels.
          </p>
        </div>
        <div className="text-right font-mono text-[0.6875rem] text-secondary">
          <p data-testid="eye-feature-coverage">
            Coverage{' '}
            {coverage
              ? `${coverage.coverageStartSeconds.toFixed(1)}–${coverage.coverageEndSeconds.toFixed(1)} s`
              : 'missing'}
          </p>
          <p>
            {coverage
              ? `${coverage.windowSeconds.toFixed(1)} s window · ${coverage.stepSeconds?.toFixed(1) ?? '—'} s step`
              : 'Window metadata unavailable'}
          </p>
          <p data-testid="reached-eye-feature-count">
            Reached feature rows: {reached.length}
          </p>
        </div>
      </div>
      {state === 'outside_coverage' ? (
        <div className="p-5 text-sm text-secondary" role="status">
          <p className="font-semibold text-warning">
            No precomputed eye-movement feature at this time.
          </p>
          <p className="mt-1">
            Actual coverage: {coverage?.coverageStartSeconds.toFixed(1)}–
            {coverage?.coverageEndSeconds.toFixed(1)} s. Missing data is not
            shown as zero.
          </p>
        </div>
      ) : state === 'missing' ? (
        <p className="p-5 text-sm text-secondary">
          Eye-movement coverage metadata is missing; no value is inferred.
        </p>
      ) : (
        <>
          <div className="grid gap-px bg-line lg:grid-cols-2">
            <div className="min-w-0 bg-surface p-4">
              <p className="text-xs font-semibold text-primary">
                Activity envelope
              </p>
              <UPlotTimeSeries
                timestamps={timestamps}
                lines={[
                  featureLine(
                    rows,
                    'activity_score',
                    currentTime,
                    'EOG activity',
                    '#3db5d8',
                  ),
                  featureLine(
                    rows,
                    'amplitude_score',
                    currentTime,
                    'Amplitude score',
                    '#9b8cf4',
                  ),
                ]}
                unit="normalized [0,1]"
                height={170}
                maxPoints={500}
                testId="eye-activity-chart"
                cursorTimestamp={currentTime}
                xRange={[startSeconds, endSeconds]}
                revealUntilTimestamp={currentTime}
                extendLastValueToCursor
                markers={markers}
              />
            </div>
            <div className="min-w-0 bg-surface p-4">
              <p className="text-xs font-semibold text-primary">
                Candidate event rate
              </p>
              <UPlotTimeSeries
                timestamps={timestamps}
                lines={[
                  featureLine(
                    rows,
                    'event_rate_per_min',
                    currentTime,
                    'Candidate event rate',
                    '#e1aa5a',
                  ),
                ]}
                unit="events / min"
                height={170}
                maxPoints={500}
                testId="eye-event-rate-chart"
                cursorTimestamp={currentTime}
                xRange={[startSeconds, endSeconds]}
                revealUntilTimestamp={currentTime}
                extendLastValueToCursor
                markers={markers}
              />
            </div>
          </div>
          <div className="border-t border-line p-4">
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                ['EOG RMS', latest?.eog_rms_uv, 'µV'],
                ['Peak-to-peak', latest?.peak_to_peak_uv, 'µV'],
                [
                  'Mean absolute derivative',
                  latest?.mean_absolute_derivative_uv_per_s,
                  'µV/s',
                ],
                ['Robust deviation', latest?.robust_deviation_z, 'z'],
              ].map(([label, value, unit]) => (
                <div
                  key={String(label)}
                  className="rounded-control bg-elevated p-3 text-xs"
                >
                  <p className="text-secondary">{label}</p>
                  <p className="mt-1 font-mono font-semibold text-primary">
                    {typeof value === 'number'
                      ? `${value.toFixed(2)} ${unit}`
                      : 'Unavailable'}
                  </p>
                </div>
              ))}
            </div>
            <div
              className="mt-3 flex flex-wrap gap-2"
              aria-label="Eye Movement Candidate markers"
              data-testid="eye-event-markers"
            >
              {reachedEvents.length ? (
                reachedEvents.map((event) => (
                  <span
                    key={event.event_id}
                    className="rounded-full border border-warning/40 bg-warning/10 px-2 py-1 font-mono text-[0.625rem] text-warning"
                    data-provenance="derived"
                  >
                    {event.timestamp.toFixed(2)} s · Eye Movement Candidate ·{' '}
                    {event.polarity} · {event.confidence.toFixed(2)}
                  </span>
                ))
              ) : (
                <span className="text-xs text-secondary">
                  No reached Eye Movement Candidate in this bounded window.
                </span>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function controlLine(
  rows: readonly SonificationControlFrameRecord[],
  field: keyof SonificationControlFrameRecord,
  currentTime: number,
  label: string,
) {
  return {
    label,
    stroke: '#9b8cf4',
    values: rows.map((row) => {
      const value = row[field];
      return row.window_end_s <= currentTime &&
        row.available &&
        typeof value === 'number'
        ? value
        : null;
    }),
  };
}

export function SonificationPanel({
  rows,
  descriptor,
  currentTime,
  startSeconds,
  endSeconds,
  replayStatus,
  audioConfig,
  baseline,
  interventionMarkers,
}: {
  rows: readonly SonificationControlFrameRecord[];
  descriptor: ContentDescriptor | undefined;
  currentTime: number;
  startSeconds: number;
  endSeconds: number;
  replayStatus: string;
  audioConfig: AudioConfig;
  baseline: BaselineControls;
  interventionMarkers: readonly TimeMarker[];
}) {
  const [source, setSource] = useState<SonificationSource>('eye_movement');
  const sourceRows = rows.filter((row) => row.source === source);
  const timestamps = sourceRows.map((row) => row.window_end_s);
  const coverageBySource = descriptor?.metadata?.coverage_by_source as
    Record<string, Record<string, unknown>> | undefined;
  const sourceCoverage =
    source === 'baseline' ? null : coverageBySource?.[source];
  const coverageStart =
    typeof sourceCoverage?.coverage_start_s === 'number'
      ? sourceCoverage.coverage_start_s
      : null;
  const coverageEnd =
    typeof sourceCoverage?.coverage_end_s === 'number'
      ? sourceCoverage.coverage_end_s
      : null;
  const outsideCoverage =
    source !== 'baseline' &&
    (coverageStart === null ||
      coverageEnd === null ||
      currentTime < coverageStart ||
      currentTime > coverageEnd);
  const audio = useSonificationAudio({
    frames: rows,
    source,
    currentTimeSeconds: currentTime,
    replayStatus,
    audioConfig,
    baseline,
  });
  const charts = [
    ['Tempo', 'tempo_bpm', 'BPM', 'sonification-tempo-chart'],
    ['Density', 'density', '[0,1]', 'sonification-density-chart'],
    ['Intensity', 'intensity', '[0,1]', 'sonification-intensity-chart'],
    ['Brightness', 'brightness_hz', 'Hz', 'sonification-brightness-chart'],
  ] as const;
  return (
    <section
      className="panel overflow-hidden border-[#9b8cf4]/40"
      aria-label="Sonification controls and playback"
      data-testid="sonification-panel"
      data-source={source}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-4 py-3">
        <div>
          <p className="eyebrow text-[#b8acf8]">SONIFICATION CONTROL</p>
          <h2 className="mt-1 font-semibold text-primary">
            EOG-driven Sonification V1
          </h2>
          <p className="mt-1 text-xs text-secondary">
            Deterministic musical mappings—not measured physiology or
            therapeutic output.
          </p>
        </div>
        <fieldset className="flex flex-wrap items-center gap-3 text-xs text-secondary">
          <legend className="mb-1 font-semibold text-primary">
            Sonification source
          </legend>
          {[
            ['eye_movement', 'Eye Movement'],
            ['alpha', 'Alpha'],
            ['baseline', 'None / baseline'],
          ].map(([value, label]) => (
            <label key={value} className="inline-flex items-center gap-1.5">
              <input
                type="radio"
                name="sonification-source"
                value={value}
                checked={source === value}
                onChange={() => setSource(value as SonificationSource)}
              />
              {label}
            </label>
          ))}
        </fieldset>
      </div>
      {outsideCoverage ? (
        <div
          className="border-b border-line p-4 text-sm text-secondary"
          role="status"
        >
          <p className="font-semibold text-warning">
            No precomputed {source === 'alpha' ? 'Alpha' : 'eye-movement'}{' '}
            control at this time.
          </p>
          <p className="mt-1">
            Actual coverage: {coverageStart?.toFixed(1) ?? 'missing'}–
            {coverageEnd?.toFixed(1) ?? 'missing'} s. Missing controls are not
            shown as zero.
          </p>
        </div>
      ) : source === 'baseline' ? (
        <p className="border-b border-line p-4 text-xs text-secondary">
          Configured baseline is intentionally constant and is not a derived
          physiological value.
        </p>
      ) : (
        <div className="grid gap-px bg-line lg:grid-cols-2">
          {charts.map(([label, field, unit, testId]) => (
            <div key={field} className="min-w-0 bg-surface p-4">
              <p className="text-xs font-semibold text-primary">{label}</p>
              <UPlotTimeSeries
                timestamps={timestamps}
                lines={[controlLine(sourceRows, field, currentTime, label)]}
                unit={unit}
                height={135}
                maxPoints={500}
                testId={testId}
                cursorTimestamp={currentTime}
                xRange={[startSeconds, endSeconds]}
                revealUntilTimestamp={currentTime}
                extendLastValueToCursor
                markers={interventionMarkers}
              />
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line p-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void audio.start()}
            disabled={outsideCoverage}
            className="inline-flex min-h-10 items-center gap-1.5 rounded-control bg-accent px-3 text-xs font-semibold text-canvas disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Volume2 size={14} />{' '}
            {audio.enabled ? 'Sound enabled' : 'Play Sound'}
          </button>
          <button
            type="button"
            onClick={audio.toggleMute}
            disabled={!audio.enabled}
            className="inline-flex min-h-10 items-center gap-1.5 rounded-control border border-line px-3 text-xs text-primary disabled:opacity-40"
          >
            {audio.muted ? <Volume2 size={14} /> : <VolumeX size={14} />}
            {audio.muted ? 'Unmute' : 'Mute'}
          </button>
          <button
            type="button"
            onClick={audio.reset}
            className="inline-flex min-h-10 items-center gap-1.5 rounded-control border border-line px-3 text-xs text-primary"
          >
            <RotateCcw size={14} /> Reset sound
          </button>
        </div>
        <div className="text-right font-mono text-[0.6875rem] text-secondary">
          <p data-testid="audio-state">
            audio{' '}
            {audio.enabled ? (audio.muted ? 'muted' : 'enabled') : 'stopped'} ·
            replay {replayStatus}
          </p>
          <p>
            current control{' '}
            {audio.control.timestamp?.toFixed(2) ?? 'unavailable'} s ·{' '}
            {audio.control.sourceFeature}
          </p>
          {audio.error ? <p className="text-danger">{audio.error}</p> : null}
        </div>
      </div>
    </section>
  );
}
