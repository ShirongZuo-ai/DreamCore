import { Music2, RefreshCw, RotateCcw, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { wakeMusicApi } from '../../services/wakeMusicApi';
import type { WakeMusicApi } from '../../services/wakeMusicApi';
import type { WakeMusicGeneration, WakeMusicStyle } from '../../types';

const styleOptions: ReadonlyArray<{ value: WakeMusicStyle; label: string }> = [
  { value: 'auto', label: 'Auto' },
  { value: 'soft_piano_ambient', label: 'Soft & Calm' },
  { value: 'bright_morning', label: 'Bright Morning' },
  { value: 'classical_chamber', label: 'Classical' },
  { value: 'neoclassical', label: 'Neo-Classical' },
  { value: 'gentle_acoustic', label: 'Gentle Acoustic' },
  { value: 'calm_ambient', label: 'Ambient' },
];

function directionLabel(value: string) {
  return value
    .replaceAll('_', ' ')
    .replace(/^./, (letter) => letter.toUpperCase());
}

function clockDuration(seconds: number) {
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}

export function WakeMusicPanel({
  sessionId,
  preparedProfile,
  api = wakeMusicApi,
}: {
  sessionId: string;
  preparedProfile?: WakeMusicGeneration['profile'];
  api?: WakeMusicApi;
}) {
  const [style, setStyle] = useState<WakeMusicStyle>('auto');
  const [manualWindow, setManualWindow] = useState(false);
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');
  const [status, setStatus] = useState<
    'idle' | 'generating' | 'success' | 'error'
  >('idle');
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState<WakeMusicGeneration | null>(
    null,
  );
  const [playbackVersion, setPlaybackVersion] = useState<'wake' | 'master'>(
    'wake',
  );
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let active = true;
    void api
      .latest?.(sessionId)
      .then((latest) => {
        if (active && latest) {
          setGeneration(latest);
          setStatus('success');
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [api, sessionId]);

  const run = async (variation: boolean) => {
    setStatus('generating');
    setError(null);
    try {
      const result =
        variation && generation
          ? await api.newVariation(generation.generation_id, style)
          : await api.generate({
              session_id: sessionId,
              style,
              ...(manualWindow
                ? {
                    window_start_s: Number(windowStart),
                    window_end_s: Number(windowEnd),
                  }
                : {}),
            });
      setGeneration(result);
      setPlaybackVersion('wake');
      setStatus('success');
    } catch (reason) {
      setStatus('error');
      setError(
        reason instanceof Error
          ? reason.message
          : 'Wake Music generation failed',
      );
    }
  };

  const current = generation?.profile ?? preparedProfile;
  const selectedAudio = generation
    ? playbackVersion === 'wake'
      ? generation.wake_version
      : generation.master_audio
    : null;
  return (
    <section
      className="panel overflow-hidden border-accent/50"
      aria-label="Wake Music"
      data-testid="wake-music-panel"
      data-generation-status={status}
    >
      <div className="border-b border-line bg-accent/5 px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="eyebrow text-accent">WAKE MUSIC · AI INSTRUMENTAL</p>
            <h2 className="mt-1 flex items-center gap-2 text-lg font-semibold text-primary">
              <Music2 aria-hidden="true" size={19} /> Tonight&apos;s Wake Music
            </h2>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-secondary">
              A reproducible exploratory mapping from recorded sleep physiology
              to musical directions used to condition generative instrumental
              music. This is not a clinical intervention or validated therapy.
            </p>
          </div>
          <span className="rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-[0.6875rem] font-semibold text-accent">
            PRODUCT EXPERIENCE
          </span>
        </div>
      </div>

      <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <div>
          <label className="block text-xs font-semibold text-primary">
            Wake Music Style
            <select
              aria-label="Wake Music Style"
              value={style}
              onChange={(event) =>
                setStyle(event.target.value as WakeMusicStyle)
              }
              className="mt-2 min-h-11 w-full rounded-control border border-line bg-canvas px-3 text-sm text-primary"
            >
              {styleOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-2 text-[0.6875rem] leading-5 text-secondary">
            Auto uses physiology plus the generation seed as an exploratory
            style choice. A selected style overrides Auto while keeping the
            physiological mapping.
          </p>

          <label className="mt-4 flex items-center gap-2 text-xs text-secondary">
            <input
              type="checkbox"
              checked={manualWindow}
              onChange={(event) => setManualWindow(event.target.checked)}
            />
            Manual research window
          </label>
          {manualWindow ? (
            <div className="mt-2 grid grid-cols-2 gap-2">
              <label className="text-[0.6875rem] text-secondary">
                Start (s)
                <input
                  aria-label="Wake Music window start"
                  type="number"
                  value={windowStart}
                  onChange={(event) => setWindowStart(event.target.value)}
                  className="mt-1 min-h-10 w-full rounded-control border border-line bg-canvas px-2 font-mono text-primary"
                />
              </label>
              <label className="text-[0.6875rem] text-secondary">
                End (s)
                <input
                  aria-label="Wake Music window end"
                  type="number"
                  value={windowEnd}
                  onChange={(event) => setWindowEnd(event.target.value)}
                  className="mt-1 min-h-10 w-full rounded-control border border-line bg-canvas px-2 font-mono text-primary"
                />
              </label>
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void run(false)}
              disabled={status === 'generating'}
              className="inline-flex min-h-11 items-center gap-2 rounded-control bg-accent px-4 text-xs font-semibold text-canvas disabled:opacity-50"
            >
              <Sparkles size={15} /> Generate Wake Music
            </button>
            <button
              type="button"
              onClick={() => void run(true)}
              disabled={!generation || status === 'generating'}
              className="inline-flex min-h-11 items-center gap-2 rounded-control border border-accent/50 px-4 text-xs font-semibold text-accent disabled:opacity-40"
            >
              <RefreshCw size={15} /> Generate New Variation
            </button>
          </div>
          <div className="mt-3 min-h-5 text-xs" aria-live="polite">
            {status === 'generating' ? (
              <span className="text-accent">
                Generating and saving instrumental music locally…
              </span>
            ) : null}
            {status === 'error' ? (
              <span className="text-danger">{error}</span>
            ) : null}
            {status === 'success' ? (
              <span className="text-success">
                {generation?.cached
                  ? 'Reused exact local generation.'
                  : 'Generation downloaded and stored locally.'}
              </span>
            ) : null}
          </div>
        </div>

        <div className="rounded-card border border-line bg-canvas/40 p-4">
          <p className="eyebrow">WAKE MUSIC PROFILE</p>
          {current ? (
            <>
              <dl className="mt-3 grid gap-x-5 gap-y-3 sm:grid-cols-2">
                <MappingItem
                  label="EOG activity"
                  value={`${current.physiology.activity_level.toFixed(2)} → ${directionLabel(current.music.register)} register`}
                />
                <MappingItem
                  label="Candidate event rate"
                  value={`${current.physiology.event_rate_per_min.toFixed(2)} / min → ${directionLabel(current.music.density)} note density`}
                />
                <MappingItem
                  label="Activity trend"
                  value={`${current.physiology.activity_trend.toFixed(3)} / min → ${directionLabel(current.music.brightness)} texture`}
                />
                <MappingItem
                  label="EOG amplitude"
                  value={`${current.physiology.amplitude_level.toFixed(2)} → ${directionLabel(current.music.expressive_strength)}`}
                />
                <MappingItem
                  label="Selected style"
                  value={current.music.style_label}
                />
                <MappingItem
                  label="Variation"
                  value={`${current.variation_id} · seed ${current.generation_seed}`}
                />
              </dl>
              <p className="mt-3 border-t border-line pt-3 text-[0.6875rem] text-secondary">
                Source window {current.source_window.start_s.toFixed(1)}–
                {current.source_window.end_s.toFixed(1)} s ·{' '}
                {current.source_window.selection.replaceAll('_', ' ')} ·{' '}
                {current.physiology.feature_row_count} derived EOG rows
              </p>
              {generation ? (
                <div className="mt-4 border-t border-line pt-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-semibold text-primary">
                      {playbackVersion === 'wake'
                        ? `Wake Version · ${clockDuration(generation.wake_version.duration_s)}`
                        : `Full Track · ${clockDuration(generation.master_audio.duration_s)}`}
                    </p>
                    <div
                      className="flex rounded-control border border-line p-0.5"
                      aria-label="Wake Music playback version"
                    >
                      <button
                        type="button"
                        aria-pressed={playbackVersion === 'wake'}
                        onClick={() => setPlaybackVersion('wake')}
                        className="rounded-control px-2.5 py-1.5 text-[0.6875rem] text-primary aria-pressed:bg-accent aria-pressed:text-canvas"
                      >
                        Wake Version · {generation.wake_version.duration_s} s
                      </button>
                      <button
                        type="button"
                        aria-pressed={playbackVersion === 'master'}
                        onClick={() => setPlaybackVersion('master')}
                        className="rounded-control px-2.5 py-1.5 text-[0.6875rem] text-primary aria-pressed:bg-accent aria-pressed:text-canvas"
                      >
                        Full Track
                      </button>
                    </div>
                  </div>
                  <audio
                    ref={audioRef}
                    key={selectedAudio?.audio_url}
                    controls
                    preload="metadata"
                    className="w-full"
                    aria-label="Generated Wake Music player"
                    src={selectedAudio?.audio_url}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (audioRef.current) audioRef.current.currentTime = 0;
                    }}
                    className="mt-2 inline-flex min-h-9 items-center gap-1.5 rounded-control border border-line px-3 text-xs text-primary"
                  >
                    <RotateCcw size={13} /> Restart track
                  </button>
                  <p className="mt-2 font-mono text-[0.625rem] leading-5 text-secondary">
                    {generation.generation_id} · {generation.provider}/
                    {generation.model} · {selectedAudio?.sample_rate_hz ?? 0} Hz
                    ·{' '}
                    {selectedAudio?.channels === 2
                      ? 'stereo'
                      : `${selectedAudio?.channels ?? 0} channels`}
                  </p>
                </div>
              ) : null}
            </>
          ) : (
            <p className="mt-3 text-sm leading-6 text-secondary">
              Generate a track to see the exact source window, EOG feature
              summary, musical mapping, style, seed, and variation.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function MappingItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-secondary">{label}</dt>
      <dd className="mt-0.5 font-mono text-sm text-primary">{value}</dd>
    </div>
  );
}
