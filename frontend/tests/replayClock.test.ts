import { describe, expect, it } from 'vitest';

import {
  createReplayClockState,
  replayClockReducer,
} from '../src/replay/replayClock';

describe('offline replay clock state machine', () => {
  it('supports play, pause, speed, seek, and restart with one authoritative time', () => {
    const initial = createReplayClockState(100, 10, 1);
    expect(initial).toMatchObject({ status: 'idle', sessionTimeSeconds: 10 });

    const playing = replayClockReducer(initial, { type: 'play' });
    const advanced = replayClockReducer(playing, {
      type: 'tick',
      elapsedSeconds: 2,
    });
    expect(advanced.sessionTimeSeconds).toBe(12);

    const faster = replayClockReducer(advanced, {
      type: 'set-speed',
      speed: 5,
    });
    const fastAdvanced = replayClockReducer(faster, {
      type: 'tick',
      elapsedSeconds: 2,
    });
    expect(fastAdvanced.sessionTimeSeconds).toBe(22);
    expect(replayClockReducer(fastAdvanced, { type: 'pause' }).status).toBe(
      'paused',
    );

    const sought = replayClockReducer(fastAdvanced, {
      type: 'seek',
      timeSeconds: 70,
    });
    expect(sought).toMatchObject({
      status: 'paused',
      sessionTimeSeconds: 70,
    });
    expect(replayClockReducer(sought, { type: 'restart' })).toMatchObject({
      status: 'idle',
      sessionTimeSeconds: 10,
    });
  });

  it('stops exactly at the session end and ignores ticks while paused', () => {
    const initial = createReplayClockState(12, 10, 2);
    const ended = replayClockReducer(
      replayClockReducer(initial, { type: 'play' }),
      { type: 'tick', elapsedSeconds: 2 },
    );
    expect(ended).toMatchObject({ status: 'ended', sessionTimeSeconds: 12 });
    expect(
      replayClockReducer(ended, { type: 'tick', elapsedSeconds: 1 }),
    ).toEqual(ended);
  });

  it('enters an explicit error state', () => {
    const initial = createReplayClockState(100, 10, 1);
    expect(
      replayClockReducer(initial, { type: 'error', message: 'transport' }),
    ).toMatchObject({ status: 'error', error: 'transport' });
  });
});
