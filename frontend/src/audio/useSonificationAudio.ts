import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type {
  SonificationControlFrameRecord,
  SonificationSource,
} from '../types';

export type AudioConfig = {
  master_gain: number;
  attack_s: number;
  release_s: number;
  note_duration_s: number;
  oscillator_type: OscillatorType;
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
  replayStatus: string;
  audioConfig: AudioConfig;
  baseline: BaselineControls;
}) {
  const [enabled, setEnabled] = useState(false);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const masterRef = useRef<GainNode | null>(null);
  const lastBeatRef = useRef<number | null>(null);
  const lastEventRef = useRef<string | null>(null);
  const control = useMemo(
    () => reachedControl(frames, source, currentTimeSeconds, baseline),
    [baseline, currentTimeSeconds, frames, source],
  );

  const ensureContext = useCallback(async () => {
    if (!contextRef.current) {
      if (typeof window.AudioContext !== 'function') {
        throw new Error('Web Audio API is unavailable in this browser');
      }
      const context = new window.AudioContext();
      const master = context.createGain();
      master.gain.value = Math.max(0, Math.min(1, audioConfig.master_gain));
      master.connect(context.destination);
      contextRef.current = context;
      masterRef.current = master;
    }
    await contextRef.current.resume();
  }, [audioConfig.master_gain]);

  const playTone = useCallback(
    (noteMidi: number, velocity: number, brightnessHz: number) => {
      const context = contextRef.current;
      const master = masterRef.current;
      if (!context || !master || muted) return;
      const oscillator = context.createOscillator();
      const filter = context.createBiquadFilter();
      const envelope = context.createGain();
      const now = context.currentTime;
      const duration = audioConfig.note_duration_s;
      oscillator.type = audioConfig.oscillator_type;
      oscillator.frequency.setValueAtTime(midiFrequency(noteMidi), now);
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(brightnessHz, now);
      envelope.gain.setValueAtTime(0, now);
      envelope.gain.linearRampToValueAtTime(
        Math.max(0, Math.min(1, velocity)),
        now + audioConfig.attack_s,
      );
      envelope.gain.setValueAtTime(
        Math.max(0, Math.min(1, velocity)),
        now + duration,
      );
      envelope.gain.linearRampToValueAtTime(
        0,
        now + duration + audioConfig.release_s,
      );
      oscillator.connect(filter);
      filter.connect(envelope);
      envelope.connect(master);
      oscillator.start(now);
      oscillator.stop(now + duration + audioConfig.release_s);
    },
    [audioConfig, muted],
  );

  const start = useCallback(async () => {
    try {
      await ensureContext();
      setEnabled(true);
      setMuted(false);
      setError(null);
    } catch (startError) {
      setError(
        startError instanceof Error
          ? startError.message
          : 'Unable to start audio',
      );
    }
  }, [ensureContext]);

  const reset = useCallback(() => {
    void contextRef.current?.close();
    contextRef.current = null;
    masterRef.current = null;
    lastBeatRef.current = null;
    lastEventRef.current = null;
    setEnabled(false);
    setMuted(false);
    setError(null);
  }, []);

  useEffect(() => reset, [reset]);

  useEffect(() => {
    lastBeatRef.current = null;
    lastEventRef.current = null;
  }, [source]);

  useEffect(() => {
    if (!enabled || muted || replayStatus !== 'playing' || !control.available)
      return;
    if (
      control.trigger &&
      control.eventId &&
      control.eventId !== lastEventRef.current &&
      control.noteMidi !== null &&
      control.brightnessHz !== null
    ) {
      playTone(
        control.noteMidi,
        control.noteVelocity ?? control.intensity ?? 0,
        control.brightnessHz,
      );
      lastEventRef.current = control.eventId;
    }
    if (
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
    playTone(
      control.noteMidi ?? 48 + (beat % 12),
      control.noteVelocity ?? control.intensity,
      control.brightnessHz,
    );
  }, [control, currentTimeSeconds, enabled, muted, playTone, replayStatus]);

  return {
    control,
    enabled,
    muted,
    error,
    start,
    toggleMute: () => setMuted((value) => !value),
    reset,
  };
}
