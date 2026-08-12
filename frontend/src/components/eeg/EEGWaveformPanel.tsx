import { Activity, SlidersHorizontal } from 'lucide-react';
import { useMemo } from 'react';

import type { EEGChannel, EEGSampleWindow } from '../../types';
import type { ReplaySignalWindow } from '../../services/replaySource';
import { UPlotTimeSeries, type TimeMarker } from '../charts/UPlotTimeSeries';
import { PanelHeader } from '../common/PanelHeader';

const SVG_WIDTH = 1000;
const SVG_HEIGHT = 56;

function signalPath(channel: EEGChannel): string {
  const maxAbs = Math.max(...channel.samples.map(Math.abs), 1);
  return channel.samples
    .map((sample, index) => {
      const x = (index / (channel.samples.length - 1)) * SVG_WIDTH;
      const y = SVG_HEIGHT / 2 - (sample / maxAbs) * (SVG_HEIGHT * 0.35);
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

export function RealEEGWaveformPanel({
  windows,
  maxDisplayPoints,
  replayCursorSeconds,
  interventionMarkers,
}: {
  windows: readonly ReplaySignalWindow[];
  maxDisplayPoints: number;
  replayCursorSeconds: number;
  interventionMarkers: readonly TimeMarker[];
}) {
  const first = windows[0];
  const plotLines = useMemo(
    () =>
      windows.map((window, index) => ({
        label: window.signal.channel_name,
        values: window.samples,
        stroke: index === 0 ? '#3db5d8' : '#9b8cf4',
        dash: index === 0 ? undefined : [8, 5],
      })),
    [windows],
  );
  if (!first || !first.timestamps?.length) return null;
  const endSeconds = first.startSeconds + first.durationSeconds;
  return (
    <section className="panel overflow-hidden" aria-labelledby="real-eeg-title">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3.5">
        <PanelHeader
          title="Recorded EEG Replay"
          eyebrow="Observed · Public Sleep-EDF"
          action={<span className="demo-chip">OFFLINE PUBLIC EEG REPLAY</span>}
        />
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-secondary">
          <span>
            {first.startSeconds.toFixed(1)}–{endSeconds.toFixed(1)} s
          </span>
          <span>{first.signal.sampling_rate_hz.toLocaleString()} Hz</span>
          <span>{first.signal.unit}</span>
        </div>
      </div>
      <div
        className="bg-[#111d2a] px-3 pb-2 pt-3"
        data-testid="real-eeg-window"
      >
        <div className="mb-2 flex flex-wrap gap-4 text-xs text-secondary">
          {windows.map((window, index) => (
            <span
              key={window.signal.id}
              className="inline-flex items-center gap-2"
            >
              <span
                aria-hidden="true"
                className={`h-0.5 w-5 ${index === 0 ? 'bg-accent' : 'bg-[#9b8cf4]'}`}
              />
              <strong className="text-primary">
                {window.signal.channel_name}
              </strong>
              ·{' '}
              {window.signal.source === 'raw'
                ? 'Observed'
                : window.signal.source}
            </span>
          ))}
          <span className="inline-flex items-center gap-2">
            <span className="h-3 w-px bg-white/70" aria-hidden="true" />
            Offline replay cursor
          </span>
          <span className="inline-flex items-center gap-2 text-warning">
            <span className="h-3 w-0.5 bg-warning" aria-hidden="true" />
            Simulated intervention marker
          </span>
        </div>
        <UPlotTimeSeries
          timestamps={first.timestamps}
          lines={plotLines}
          unit={first.signal.unit}
          height={250}
          maxPoints={maxDisplayPoints}
          testId="real-eeg-uplot"
          cursorTimestamp={replayCursorSeconds}
          xRange={[first.startSeconds, endSeconds]}
          revealUntilTimestamp={replayCursorSeconds}
          markers={interventionMarkers}
          showMarkerLabels
        />
      </div>
      <p className="border-t border-line px-4 py-2.5 text-[0.6875rem] text-secondary">
        Windowed read only · display downsampling does not alter transport
        samples or statistics · intervention markers never modify EEG
      </p>
    </section>
  );
}

function WaveRow({ channel }: { channel: EEGChannel }) {
  return (
    <div className="grid min-w-0 grid-cols-[2.75rem_minmax(0,1fr)] items-center border-t border-line/70 first:border-t-0 sm:grid-cols-[3.5rem_minmax(0,1fr)_4.5rem]">
      <div className="px-2 text-center font-mono text-xs font-semibold text-primary sm:px-3">
        {channel.label}
      </div>
      <div className="relative min-w-0 border-x border-line/70">
        <svg
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
          preserveAspectRatio="none"
          className="block h-14 w-full"
          role="img"
          aria-label={`${channel.label} simulated EEG waveform`}
        >
          <line
            x1="0"
            y1={SVG_HEIGHT / 2}
            x2={SVG_WIDTH}
            y2={SVG_HEIGHT / 2}
            stroke="var(--color-border)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          {[200, 400, 600, 800].map((x) => (
            <line
              key={x}
              x1={x}
              y1="0"
              x2={x}
              y2={SVG_HEIGHT}
              stroke="var(--color-border)"
              strokeOpacity="0.45"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <path
            d={signalPath(channel)}
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="1.35"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="hidden px-2 text-center sm:block">
        <span
          className={`text-[0.625rem] font-semibold uppercase tracking-wide ${
            channel.quality === 'good' ? 'text-success' : 'text-warning'
          }`}
        >
          {channel.quality}
        </span>
      </div>
    </div>
  );
}

export function EEGWaveformPanel({
  window,
  sourceLabel = 'Simulated',
}: {
  window: EEGSampleWindow;
  sourceLabel?: string;
}) {
  return (
    <section
      className="panel min-h-[29rem] overflow-hidden"
      aria-labelledby="eeg-title"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3.5">
        <PanelHeader
          title="EEG Signal Monitor"
          eyebrow="Shared time axis"
          action={<span className="demo-chip">{sourceLabel}</span>}
        />
        <div className="flex items-center gap-4 text-xs text-secondary">
          <span className="inline-flex items-center gap-1.5">
            <Activity aria-hidden="true" size={14} className="text-accent" />
            {window.durationSeconds} s Demo Window
          </span>
          <span className="hidden items-center gap-1.5 sm:inline-flex">
            <SlidersHorizontal aria-hidden="true" size={14} />
            Signal Quality
          </span>
          <span className="font-mono">µV</span>
        </div>
      </div>

      <div className="bg-[#111d2a]" data-testid="eeg-channel-list">
        {window.channels.map((channel) => (
          <WaveRow channel={channel} key={channel.id} />
        ))}
      </div>

      <div className="grid grid-cols-[2.75rem_minmax(0,1fr)] border-t border-line bg-elevated sm:grid-cols-[3.5rem_minmax(0,1fr)_4.5rem]">
        <div />
        <div className="flex justify-between border-x border-line px-1.5 py-2 font-mono text-[0.625rem] text-secondary">
          <span>0 s</span>
          <span>2 s</span>
          <span>4 s</span>
          <span>6 s</span>
          <span>8 s</span>
          <span>10 s</span>
        </div>
        <div />
      </div>
      <p className="border-t border-line px-4 py-2.5 text-[0.6875rem] text-secondary">
        Deterministic display waveform · no subject data · {sourceLabel} · uPlot
        adapter boundary
      </p>
    </section>
  );
}
