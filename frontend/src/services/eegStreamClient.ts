import { demoEEGWindow } from '../mocks/demoData';
import type { EEGSampleWindow } from '../types';

export type EEGStreamConnectionState =
  'idle' | 'connecting' | 'connected' | 'closed' | 'error';

export interface EEGStreamClient {
  readonly state: EEGStreamConnectionState;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  subscribe(listener: (window: EEGSampleWindow) => void): () => void;
}

/**
 * Deterministic, network-free adapter. A future WebSocket implementation should
 * decode packets into a ring buffer outside React, then publish display windows
 * at a bounded UI refresh rate.
 */
export class DemoEEGStreamClient implements EEGStreamClient {
  readonly state: EEGStreamConnectionState = 'idle';

  async connect(): Promise<void> {
    return Promise.resolve();
  }

  async disconnect(): Promise<void> {
    return Promise.resolve();
  }

  subscribe(listener: (window: EEGSampleWindow) => void): () => void {
    listener(demoEEGWindow);
    return () => undefined;
  }
}
