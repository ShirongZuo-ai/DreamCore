import type {
  CanonicalSignalMetadata,
  ContentDescriptor,
  SessionManifest,
} from '../types';

export type ReplaySignalWindow = {
  signal: CanonicalSignalMetadata;
  startSeconds: number;
  durationSeconds: number;
  samples: readonly number[];
};

export interface ReplaySource {
  getSession(): SessionManifest;
  getDuration(): number;
  getSignalMetadata(): readonly CanonicalSignalMetadata[];
  readSignalWindow(
    signalId: string,
    startSeconds: number,
    durationSeconds: number,
  ): Promise<ReplaySignalWindow>;
  getAnnotations(annotationType: string): Promise<ContentDescriptor | null>;
  getDerivedEvents(resultType: string): Promise<ContentDescriptor | null>;
}

export class FixtureReplaySource implements ReplaySource {
  constructor(private readonly manifest: SessionManifest) {}

  getSession() {
    return this.manifest;
  }

  getDuration() {
    return this.manifest.recording.duration_seconds;
  }

  getSignalMetadata() {
    return this.manifest.signals;
  }

  async readSignalWindow(): Promise<ReplaySignalWindow> {
    throw new Error(
      'Fixture transport contains metadata only; signal playback begins in Phase 2B',
    );
  }

  async getAnnotations(annotationType: string) {
    return Promise.resolve(this.manifest.annotations[annotationType] ?? null);
  }

  async getDerivedEvents(resultType: string) {
    return Promise.resolve(this.manifest.derived[resultType] ?? null);
  }
}
