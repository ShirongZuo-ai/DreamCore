import { demoSession } from '../mocks/demoData';
import type { SubjectSession } from '../types';

export interface SessionApi {
  getCurrentSession(signal?: AbortSignal): Promise<SubjectSession>;
  requestSessionExport(sessionId: string, signal?: AbortSignal): Promise<void>;
}

export class DemoSessionApi implements SessionApi {
  async getCurrentSession(): Promise<SubjectSession> {
    return Promise.resolve(demoSession);
  }

  async requestSessionExport(): Promise<void> {
    return Promise.resolve();
  }
}
