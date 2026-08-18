import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type AudioConfig,
  type BaselineControls,
  useSonificationAudio,
} from '../src/audio/useSonificationAudio';
import type { ReplayStatus } from '../src/replay/replayClock';
import type {
  SonificationControlFrameRecord,
  SonificationSource,
} from '../src/types';

class MockParam {
  value = 0;
  setValueAtTime = vi.fn();
  linearRampToValueAtTime = vi.fn();
}

class MockNode {
  connect = vi.fn();
}

class MockGain extends MockNode {
  gain = new MockParam();
}

class MockOscillator extends MockNode {
  type: OscillatorType = 'sine';
  frequency = new MockParam();
  start = vi.fn();
  stop = vi.fn();
}

class MockFilter extends MockNode {
  type: BiquadFilterType = 'lowpass';
  frequency = new MockParam();
  Q = new MockParam();
}

class MockAudioContext {
  static instances: MockAudioContext[] = [];
  currentTime = 2;
  state: AudioContextState = 'suspended';
  destination = new MockNode();
  gains: MockGain[] = [];
  oscillators: MockOscillator[] = [];
  filters: MockFilter[] = [];
  stateListeners = new Set<() => void>();
  resume = vi.fn(async () => {
    this.state = 'running';
    this.stateListeners.forEach((listener) => listener());
  });
  close = vi.fn(async () => {
    this.state = 'closed';
    this.stateListeners.forEach((listener) => listener());
  });
  addEventListener = vi.fn((name: string, listener: () => void) => {
    if (name === 'statechange') this.stateListeners.add(listener);
  });
  createGain = vi.fn(() => {
    const node = new MockGain();
    this.gains.push(node);
    return node;
  });
  createOscillator = vi.fn(() => {
    const node = new MockOscillator();
    this.oscillators.push(node);
    return node;
  });
  createBiquadFilter = vi.fn(() => {
    const node = new MockFilter();
    this.filters.push(node);
    return node;
  });

  constructor() {
    MockAudioContext.instances.push(this);
  }
}

const audioConfig: AudioConfig = {
  master_gain: 0.16,
  minimum_rendered_velocity: 0.12,
  attack_s: 0.01,
  release_s: 0.24,
  note_duration_s: 0.16,
  oscillator_type: 'sine',
  filter_q: 0.7,
  test_sound: {
    midi_note: 69,
    velocity: 0.35,
    brightness_hz: 2400,
    duration_s: 0.25,
  },
};

const baseline: BaselineControls = {
  tempo_bpm: 60,
  density: 1,
  intensity: 0.2,
  brightness_hz: 1200,
  midi_note: 60,
};

function frame(
  windowEnd: number,
  trigger = false,
): SonificationControlFrameRecord {
  return {
    session_id: 'session',
    source: 'eye_movement',
    source_feature: 'eye_movement_activity_v1',
    window_start_s: windowEnd - 2,
    window_end_s: windowEnd,
    available: true,
    tempo_bpm: 60,
    density: 0,
    intensity: 0.08,
    brightness_hz: 630,
    trigger,
    event_id: trigger ? `event-${windowEnd}` : null,
    note_midi: trigger ? 55 : null,
    note_velocity: trigger ? 0.32 : null,
    mapping_version: 'mapping-v1',
    control_version: 'control-v1',
    seed: 42,
    provenance: 'sonification_control',
  };
}

type HookProps = {
  frames: SonificationControlFrameRecord[];
  source: SonificationSource;
  currentTimeSeconds: number;
  replayStatus: ReplayStatus;
};

function renderAudioHook(initialProps: HookProps) {
  return renderHook(
    (props: HookProps) =>
      useSonificationAudio({ ...props, audioConfig, baseline }),
    { initialProps },
  );
}

describe('useSonificationAudio', () => {
  beforeEach(() => {
    MockAudioContext.instances = [];
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: MockAudioContext,
    });
  });

  it('creates and resumes Web Audio, then schedules a connected envelope only while replay plays', async () => {
    const hook = renderAudioHook({
      frames: [],
      source: 'baseline',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });

    await act(async () => expect(await hook.result.current.start()).toBe(true));
    const context = MockAudioContext.instances[0];
    expect(context.resume).toHaveBeenCalledOnce();
    expect(context.state).toBe('running');
    expect(context.oscillators).toHaveLength(0);
    expect(context.gains[0].connect).toHaveBeenCalledWith(context.destination);

    hook.rerender({
      frames: [],
      source: 'baseline',
      currentTimeSeconds: 10.1,
      replayStatus: 'playing',
    });
    await waitFor(() => expect(context.oscillators).toHaveLength(1));
    const oscillator = context.oscillators[0];
    const filter = context.filters[0];
    const envelope = context.gains[1];
    expect(oscillator.connect).toHaveBeenCalledWith(filter);
    expect(filter.connect).toHaveBeenCalledWith(envelope);
    expect(envelope.connect).toHaveBeenCalledWith(context.gains[0]);
    expect(envelope.gain.linearRampToValueAtTime).toHaveBeenCalledWith(
      0.2,
      2.01,
    );
    expect(oscillator.start).toHaveBeenCalledWith(2);
    expect(oscillator.stop.mock.calls[0][0]).toBeCloseTo(2.4);
    expect(hook.result.current.lastTone).toMatchObject({
      kind: 'beat',
      noteMidi: 60,
      controlVelocity: 0.2,
      renderedVelocity: 0.2,
      effectivePeakGain: 0.032,
    });
  });

  it('plays a direct output test without enabling or advancing sonification', async () => {
    const hook = renderAudioHook({
      frames: [],
      source: 'baseline',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    await act(async () =>
      expect(await hook.result.current.testSound()).toBe(true),
    );
    const context = MockAudioContext.instances[0];
    expect(context.oscillators).toHaveLength(1);
    expect(hook.result.current.enabled).toBe(false);
    expect(hook.result.current.lastTone).toMatchObject({
      kind: 'audio_output_test',
      noteMidi: 69,
      frequencyHz: 440,
      sessionTimeSeconds: null,
    });
  });

  it('does not start without an available physiological control', async () => {
    const hook = renderAudioHook({
      frames: [],
      source: 'eye_movement',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    await act(async () =>
      expect(await hook.result.current.start()).toBe(false),
    );
    expect(MockAudioContext.instances).toHaveLength(0);
    expect(hook.result.current.error).toMatch(/No sonification control/);
  });

  it('reports a suspended context instead of claiming audio is enabled', async () => {
    class SuspendedAudioContext extends MockAudioContext {
      override resume = vi.fn(async () => undefined);
    }
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: SuspendedAudioContext,
    });
    const hook = renderAudioHook({
      frames: [],
      source: 'baseline',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    await act(async () =>
      expect(await hook.result.current.start()).toBe(false),
    );
    expect(hook.result.current.contextState).toBe('suspended');
    expect(hook.result.current.enabled).toBe(false);
    expect(hook.result.current.error).toBe('AudioContext remained suspended');
  });

  it('mutes future tones and reset closes the context', async () => {
    const hook = renderAudioHook({
      frames: [],
      source: 'baseline',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    await act(async () => void (await hook.result.current.start()));
    const context = MockAudioContext.instances[0];
    await act(async () => void (await hook.result.current.toggleMute()));
    expect(context.gains[0].gain.setValueAtTime).toHaveBeenLastCalledWith(0, 2);
    hook.rerender({
      frames: [],
      source: 'baseline',
      currentTimeSeconds: 11.1,
      replayStatus: 'playing',
    });
    expect(context.oscillators).toHaveLength(0);
    act(() => hook.result.current.reset());
    expect(context.close).toHaveBeenCalledOnce();
    expect(hook.result.current.enabled).toBe(false);
    expect(hook.result.current.contextState).toBe('closed');
  });

  it('plays trigger frames crossed between replay updates once without requiring the latest frame to trigger', async () => {
    const frames = [frame(10), frame(11, true), frame(12)];
    const hook = renderAudioHook({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    await act(async () => void (await hook.result.current.start()));
    const context = MockAudioContext.instances[0];
    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 12.1,
      replayStatus: 'playing',
    });
    await waitFor(() => expect(context.oscillators).toHaveLength(1));
    expect(hook.result.current.lastTone).toMatchObject({
      kind: 'candidate_event',
      noteMidi: 55,
      sessionTimeSeconds: 11,
    });
    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 12.2,
      replayStatus: 'playing',
    });
    expect(context.oscillators).toHaveLength(1);
  });

  it('resets crossed-event scheduling after backward and forward seeks', async () => {
    const frames = [frame(10), frame(11, true), frame(12)];
    const hook = renderAudioHook({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    await act(async () => void (await hook.result.current.start()));
    const context = MockAudioContext.instances[0];
    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 12,
      replayStatus: 'playing',
    });
    await waitFor(() => expect(context.oscillators).toHaveLength(1));

    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 10,
      replayStatus: 'paused',
    });
    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 12,
      replayStatus: 'playing',
    });
    await waitFor(() => expect(context.oscillators).toHaveLength(2));

    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 12,
      replayStatus: 'paused',
    });
    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 13,
      replayStatus: 'paused',
    });
    hook.rerender({
      frames,
      source: 'eye_movement',
      currentTimeSeconds: 13.1,
      replayStatus: 'playing',
    });
    expect(context.oscillators).toHaveLength(2);
  });
});
