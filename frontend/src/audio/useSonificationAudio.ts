import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ReplayStatus } from '../replay/replayClock';
import type {
  SonificationControlFrameRecord,
  SonificationSource,
} from '../types';

export type AudioConfig = {
  master_gain: number;
  minimum_rendered_velocity: number;
  attack_s: number;
  release_s: number;
  note_duration_s: number;
  oscillator_type: OscillatorType;
  filter_q: number;
  test_sound: {
    midi_note: number;
    velocity: number;
    brightness_hz: number;
    duration_s: number;
  };
};

export type BaselineControls = {
  tempo_bpm: number;
  density: number;
  intensity: number;
  brightness_hz: number;
  midi_note: number;
};

export type ActiveSonificationControl = {
  available: boolean;
  tempoBpm: number | null;
  density: number | null;
  intensity: number | null;
  brightnessHz: number | null;
  noteMidi: number | null;
  noteVelocity: number | null;
  trigger: boolean;
  eventId: string | null;
  seed: number;
  timestamp: number | null;
  sourceFeature: string;
};

export type PlayedTone = {
  kind: 'candidate_event' | 'beat' | 'audio_output_test';
  noteMidi: number;
  frequencyHz: number;
  controlVelocity: number;
  renderedVelocity: number;
  effectivePeakGain: number;
  brightnessHz: number;
  filterQ: number;
  sessionTimeSeconds: number | null;
};

export type AudioContextDiagnosticState =
  AudioContextState | 'not-created' | 'unavailable';

function clampUnit(value: number) {
  return Math.max(0, Math.min(1, value));
}

function midiFrequency(note: number) {
  return 440 * 2 ** ((note - 69) / 12);
}

function deterministicUnit(seed: number, beat: number) {
  let value = (seed ^ Math.imul(beat + 1, 0x9e3779b1)) | 0;
  value ^= value << 13;
  value ^= value >>> 17;
  value ^= value << 5;
  return (value >>> 0) / 0xffffffff;
}

function reachedControl(
  frames: readonly SonificationControlFrameRecord[],
  source: SonificationSource,
  currentTimeSeconds: number,
  baseline: BaselineControls,
): ActiveSonificationControl {
  if (source === 'baseline') {
    return {
      available: true,
      tempoBpm: baseline.tempo_bpm,
      density: baseline.density,
      intensity: baseline.intensity,
      brightnessHz: baseline.brightness_hz,
      noteMidi: baseline.midi_note,
      noteVelocity: baseline.intensity,
      trigger: false,
      eventId: null,
      seed: 0,
      timestamp: currentTimeSeconds,
      sourceFeature: 'configured_baseline',
    };
  }
  const candidates = frames.filter(
    (frame) =>
      frame.source === source && frame.window_end_s <= currentTimeSeconds,
  );
  const frame = candidates.reduce<SonificationControlFrameRecord | null>(
    (latest, item) =>
      latest === null || item.window_end_s > latest.window_end_s
        ? item
        : latest,
    null,
  );
  if (!frame || !frame.available) {
    return {
      available: false,
      tempoBpm: null,
      density: null,
      intensity: null,
      brightnessHz: null,
      noteMidi: null,
      noteVelocity: null,
      trigger: false,
      eventId: null,
      seed: frame?.seed ?? 0,
      timestamp: frame?.window_end_s ?? null,
      sourceFeature: frame?.source_feature ?? source,
    };
  }
  return {
    available: true,
    tempoBpm: frame.tempo_bpm,
    density: frame.density,
    intensity: frame.intensity,
    brightnessHz: frame.brightness_hz,
    noteMidi: frame.note_midi,
    noteVelocity: frame.note_velocity,
    trigger: frame.trigger,
    eventId: frame.event_id,
    seed: frame.seed,
    timestamp: frame.window_end_s,
    sourceFeature: frame.source_feature,
  };
}

export function useSonificationAudio({
  frames,
  source,
  currentTimeSeconds,
  replayStatus,
  audioConfig,
  baseline,
}: {
  frames: readonly SonificationControlFrameRecord[];
  source: SonificationSource;
  currentTimeSeconds: number;
  replayStatus: ReplayStatus;
  audioConfig: AudioConfig;
  baseline: BaselineControls;
}) {
  const [enabled, setEnabled] = useState(false);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contextState, setContextState] = useState<AudioContextDiagnosticState>(
    () =>
      typeof window !== 'undefined' && typeof window.AudioContext === 'function'
        ? 'not-created'
        : 'unavailable',
  );
  const [lastTone, setLastTone] = useState<PlayedTone | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const masterRef = useRef<GainNode | null>(null);
  const lastBeatRef = useRef<number | null>(null);
  const playedEventIdsRef = useRef(new Set<string>());
  const previousReplayTimeRef = useRef(currentTimeSeconds);
  const currentTimeRef = useRef(currentTimeSeconds);
  const previousSourceRef = useRef(source);
  const mutedRef = useRef(muted);
  const control = useMemo(
    () => reachedControl(frames, source, currentTimeSeconds, baseline),
    [baseline, currentTimeSeconds, frames, source],
  );
  currentTimeRef.current = currentTimeSeconds;

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  const ensureContext = useCallback(async () => {
    if (!contextRef.current) {
      if (typeof window.AudioContext !== 'function') {
        setContextState('unavailable');
        throw new Error('Web Audio API is unavailable in this browser');
      }
      const context = new window.AudioContext();
      const master = context.createGain();
      master.gain.value = clampUnit(audioConfig.master_gain);
      master.connect(context.destination);
      const updateContextState = () => setContextState(context.state);
      context.addEventListener('statechange', updateContextState);
      contextRef.current = context;
      masterRef.current = master;
      setContextState(context.state);
    }
    const context = contextRef.current;
    await context.resume();
    setContextState(context.state);
    if (context.state !== 'running') {
      throw new Error(`AudioContext remained ${context.state}`);
    }
    return context;
  }, [audioConfig.master_gain]);

  const playTone = useCallback(
    ({
      noteMidi,
      velocity,
      brightnessHz,
      kind,
      sessionTimeSeconds,
      durationSeconds = audioConfig.note_duration_s,
    }: {
      noteMidi: number;
      velocity: number;
      brightnessHz: number;
      kind: PlayedTone['kind'];
      sessionTimeSeconds: number | null;
      durationSeconds?: number;
    }) => {
      const context = contextRef.current;
      const master = masterRef.current;
      if (
        !context ||
        !master ||
        context.state !== 'running' ||
        mutedRef.current
      ) {
        return false;
      }
      const controlVelocity = clampUnit(velocity);
      const renderedVelocity =
        controlVelocity === 0
          ? 0
          : Math.max(
              clampUnit(audioConfig.minimum_rendered_velocity),
              controlVelocity,
            );
      const frequencyHz = midiFrequency(noteMidi);
      const oscillator = context.createOscillator();
      const filter = context.createBiquadFilter();
      const envelope = context.createGain();
      const now = context.currentTime;
      oscillator.type = audioConfig.oscillator_type;
      oscillator.frequency.setValueAtTime(frequencyHz, now);
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(brightnessHz, now);
      filter.Q.setValueAtTime(audioConfig.filter_q, now);
      envelope.gain.setValueAtTime(0, now);
      envelope.gain.linearRampToValueAtTime(
        renderedVelocity,
        now + audioConfig.attack_s,
      );
      envelope.gain.setValueAtTime(renderedVelocity, now + durationSeconds);
      envelope.gain.linearRampToValueAtTime(
        0,
        now + durationSeconds + audioConfig.release_s,
      );
      oscillator.connect(filter);
      filter.connect(envelope);
      envelope.connect(master);
      oscillator.start(now);
      oscillator.stop(now + durationSeconds + audioConfig.release_s);
      setLastTone({
        kind,
        noteMidi,
        frequencyHz,
        controlVelocity,
        renderedVelocity,
        effectivePeakGain:
          clampUnit(audioConfig.master_gain) * renderedVelocity,
        brightnessHz,
        filterQ: audioConfig.filter_q,
        sessionTimeSeconds,
      });
      return true;
    },
    [audioConfig],
  );

  const start = useCallback(async () => {
    if (!control.available) {
      setError('No sonification control is available at the current cursor');
      return false;
    }
    try {
      await ensureContext();
      setEnabled(true);
      setMuted(false);
      mutedRef.current = false;
      masterRef.current?.gain.setValueAtTime(
        clampUnit(audioConfig.master_gain),
        contextRef.current?.currentTime ?? 0,
      );
      setError(null);
      return true;
    } catch (startError) {
      setEnabled(false);
      setError(
        startError instanceof Error
          ? startError.message
          : 'Unable to start audio',
      );
      return false;
    }
  }, [audioConfig.master_gain, control.available, ensureContext]);

  const testSound = useCallback(async () => {
    try {
      await ensureContext();
      if (mutedRef.current) {
        throw new Error(
          'Audio is muted; unmute before running the output test',
        );
      }
      const played = playTone({
        noteMidi: audioConfig.test_sound.midi_note,
        velocity: audioConfig.test_sound.velocity,
        brightnessHz: audioConfig.test_sound.brightness_hz,
        kind: 'audio_output_test',
        sessionTimeSeconds: null,
        durationSeconds: audioConfig.test_sound.duration_s,
      });
      if (!played)
        throw new Error('Audio output test could not schedule a tone');
      setError(null);
      return true;
    } catch (testError) {
      setError(
        testError instanceof Error
          ? testError.message
          : 'Unable to test audio output',
      );
      return false;
    }
  }, [audioConfig.test_sound, ensureContext, playTone]);

  const toggleMute = useCallback(async () => {
    if (!enabled) return;
    if (!mutedRef.current) {
      mutedRef.current = true;
      setMuted(true);
      masterRef.current?.gain.setValueAtTime(
        0,
        contextRef.current?.currentTime ?? 0,
      );
      return;
    }
    try {
      await ensureContext();
      mutedRef.current = false;
      setMuted(false);
      masterRef.current?.gain.setValueAtTime(
        clampUnit(audioConfig.master_gain),
        contextRef.current?.currentTime ?? 0,
      );
      setError(null);
    } catch (unmuteError) {
      setError(
        unmuteError instanceof Error
          ? unmuteError.message
          : 'Unable to resume audio',
      );
    }
  }, [audioConfig.master_gain, enabled, ensureContext]);

  const reset = useCallback(() => {
    const context = contextRef.current;
    contextRef.current = null;
    masterRef.current = null;
    void context?.close();
    lastBeatRef.current = null;
    playedEventIdsRef.current.clear();
    previousReplayTimeRef.current = currentTimeRef.current;
    setEnabled(false);
    setMuted(false);
    mutedRef.current = false;
    setContextState(context ? 'closed' : 'not-created');
    setLastTone(null);
    setError(null);
  }, []);

  useEffect(() => reset, [reset]);

  useEffect(() => {
    if (previousSourceRef.current !== source) {
      previousSourceRef.current = source;
      previousReplayTimeRef.current = currentTimeSeconds;
      lastBeatRef.current = null;
      playedEventIdsRef.current.clear();
      setLastTone(null);
      return;
    }
    if (replayStatus !== 'playing') {
      if (currentTimeSeconds !== previousReplayTimeRef.current) {
        lastBeatRef.current = null;
        playedEventIdsRef.current.clear();
        setLastTone(null);
      }
      previousReplayTimeRef.current = currentTimeSeconds;
      return;
    }
    const previousTime = previousReplayTimeRef.current;
    previousReplayTimeRef.current = currentTimeSeconds;
    if (!enabled || muted || !control.available) return;

    let playedEvent = false;
    if (source !== 'baseline' && currentTimeSeconds >= previousTime) {
      const crossedEvents = frames
        .filter(
          (frame) =>
            frame.source === source &&
            frame.available &&
            frame.trigger &&
            frame.event_id !== null &&
            frame.note_midi !== null &&
            frame.brightness_hz !== null &&
            frame.window_end_s > previousTime &&
            frame.window_end_s <= currentTimeSeconds,
        )
        .sort((left, right) => left.window_end_s - right.window_end_s);
      for (const frame of crossedEvents) {
        if (playedEventIdsRef.current.has(frame.event_id!)) continue;
        if (
          playTone({
            noteMidi: frame.note_midi!,
            velocity: frame.note_velocity ?? frame.intensity ?? 0,
            brightnessHz: frame.brightness_hz!,
            kind: 'candidate_event',
            sessionTimeSeconds: frame.window_end_s,
          })
        ) {
          playedEventIdsRef.current.add(frame.event_id!);
          playedEvent = true;
        }
      }
    }
    if (
      playedEvent ||
      control.tempoBpm === null ||
      control.density === null ||
      control.intensity === null ||
      control.brightnessHz === null
    ) {
      return;
    }
    const beat = Math.floor((currentTimeSeconds * control.tempoBpm) / 60);
    if (beat === lastBeatRef.current) return;
    lastBeatRef.current = beat;
    if (deterministicUnit(control.seed, beat) > control.density) return;
    playTone({
      noteMidi: control.noteMidi ?? 48 + (beat % 12),
      velocity: control.noteVelocity ?? control.intensity,
      brightnessHz: control.brightnessHz,
      kind: 'beat',
      sessionTimeSeconds: currentTimeSeconds,
    });
  }, [
    control,
    currentTimeSeconds,
    enabled,
    frames,
    muted,
    playTone,
    replayStatus,
    source,
  ]);

  return {
    control,
    contextState,
    enabled,
    muted,
    error,
    lastTone,
    start,
    testSound,
    toggleMute,
    reset,
  };
}
