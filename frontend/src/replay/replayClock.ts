import { useCallback, useEffect, useReducer, useRef } from 'react';

export type ReplayStatus = 'idle' | 'playing' | 'paused' | 'ended' | 'error';

export type ReplayClockState = {
  status: ReplayStatus;
  sessionTimeSeconds: number;
  sessionDurationSeconds: number;
  replayStartTimeSeconds: number;
  playbackSpeed: number;
  error: string | null;
};

export type ReplayClockAction =
  | { type: 'play' }
  | { type: 'pause' }
  | { type: 'tick'; elapsedSeconds: number }
  | { type: 'seek'; timeSeconds: number }
  | { type: 'restart' }
  | { type: 'set-speed'; speed: number }
  | { type: 'error'; message: string };

function clampTime(timeSeconds: number, durationSeconds: number) {
  return Math.max(0, Math.min(timeSeconds, durationSeconds));
}

export function createReplayClockState(
  sessionDurationSeconds: number,
  replayStartTimeSeconds: number,
  playbackSpeed: number,
): ReplayClockState {
  if (sessionDurationSeconds <= 0 || playbackSpeed <= 0) {
    throw new Error('Replay duration and playback speed must be positive');
  }
  return {
    status: 'idle',
    sessionTimeSeconds: clampTime(
      replayStartTimeSeconds,
      sessionDurationSeconds,
    ),
    sessionDurationSeconds,
    replayStartTimeSeconds: clampTime(
      replayStartTimeSeconds,
      sessionDurationSeconds,
    ),
    playbackSpeed,
    error: null,
  };
}

export function replayClockReducer(
  state: ReplayClockState,
  action: ReplayClockAction,
): ReplayClockState {
  switch (action.type) {
    case 'play':
      if (state.status === 'error') return state;
      if (state.sessionTimeSeconds >= state.sessionDurationSeconds) {
        return { ...state, status: 'ended' };
      }
      return { ...state, status: 'playing', error: null };
    case 'pause':
      return state.status === 'playing'
        ? { ...state, status: 'paused' }
        : state;
    case 'tick': {
      if (state.status !== 'playing' || action.elapsedSeconds <= 0)
        return state;
      const next = clampTime(
        state.sessionTimeSeconds + action.elapsedSeconds * state.playbackSpeed,
        state.sessionDurationSeconds,
      );
      return {
        ...state,
        sessionTimeSeconds: next,
        status: next >= state.sessionDurationSeconds ? 'ended' : 'playing',
      };
    }
    case 'seek': {
      const next = clampTime(action.timeSeconds, state.sessionDurationSeconds);
      return {
        ...state,
        sessionTimeSeconds: next,
        status: next >= state.sessionDurationSeconds ? 'ended' : 'paused',
        error: null,
      };
    }
    case 'restart':
      return {
        ...state,
        sessionTimeSeconds: state.replayStartTimeSeconds,
        status: 'idle',
        error: null,
      };
    case 'set-speed':
      if (action.speed <= 0) return state;
      return { ...state, playbackSpeed: action.speed };
    case 'error':
      return { ...state, status: 'error', error: action.message };
  }
}

export function useReplayClock({
  durationSeconds,
  startTimeSeconds,
  defaultSpeed,
  tickIntervalMs,
}: {
  durationSeconds: number;
  startTimeSeconds: number;
  defaultSpeed: number;
  tickIntervalMs: number;
}) {
  const [state, dispatch] = useReducer(
    replayClockReducer,
    createReplayClockState(durationSeconds, startTimeSeconds, defaultSpeed),
  );
  const lastTickMs = useRef<number | null>(null);

  useEffect(() => {
    if (state.status !== 'playing') {
      lastTickMs.current = null;
      return;
    }
    lastTickMs.current = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const previous = lastTickMs.current ?? now;
      lastTickMs.current = now;
      dispatch({ type: 'tick', elapsedSeconds: (now - previous) / 1000 });
    }, tickIntervalMs);
    return () => window.clearInterval(timer);
  }, [state.status, tickIntervalMs]);

  return {
    state,
    play: useCallback(() => dispatch({ type: 'play' }), []),
    pause: useCallback(() => dispatch({ type: 'pause' }), []),
    restart: useCallback(() => dispatch({ type: 'restart' }), []),
    seek: useCallback(
      (timeSeconds: number) => dispatch({ type: 'seek', timeSeconds }),
      [],
    ),
    setSpeed: useCallback(
      (speed: number) => dispatch({ type: 'set-speed', speed }),
      [],
    ),
    fail: useCallback(
      (message: string) => dispatch({ type: 'error', message }),
      [],
    ),
  };
}
