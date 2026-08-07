import type {
  AnnotationWindowResponse,
  CanonicalSignalMetadata,
  DerivedWindowResponse,
  EventWindowResponse,
  SessionManifest,
  SignalWindowResponse,
} from '../types';

export type ReplaySignalWindow = {
  signal: CanonicalSignalMetadata;
  startSeconds: number;
  durationSeconds: number;
  timestamps?: readonly number[];
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
  readAnnotations(
    startSeconds: number,
    endSeconds: number,
  ): Promise<AnnotationWindowResponse>;
  readDerived(
    metric: string,
    startSeconds: number,
    endSeconds: number,
  ): Promise<DerivedWindowResponse>;
  readEvents(
    startSeconds: number,
    endSeconds: number,
  ): Promise<EventWindowResponse>;
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

  async readAnnotations(startSeconds: number, endSeconds: number) {
    return Promise.resolve({
      session_id: this.manifest.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptors: this.manifest.annotations,
      annotations: [],
    });
  }

  async readDerived(metric: string, startSeconds: number, endSeconds: number) {
    const descriptor = this.manifest.derived[metric];
    if (!descriptor) throw new Error(`Derived metric unavailable: ${metric}`);
    return Promise.resolve({
      session_id: this.manifest.session.session_id,
      metric,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor,
      records: [],
    });
  }

  async readEvents(startSeconds: number, endSeconds: number) {
    return Promise.resolve({
      session_id: this.manifest.session.session_id,
      start_s: startSeconds,
      end_s: endSeconds,
      descriptor: null,
      events: [],
    });
  }
}

type ApiEnvelope<T> = { api_version: 'v1'; data: T };
type ApiFailure = {
  api_version: 'v1';
  error: { code: string; message: string };
};

export class HttpReplaySource implements ReplaySource {
  constructor(
    private readonly manifest: SessionManifest,
    private readonly baseUrl = '/api/v1',
  ) {}

  getSession() {
    return this.manifest;
  }

  getDuration() {
    return this.manifest.recording.duration_seconds;
  }

  getSignalMetadata() {
    return this.manifest.signals;
  }

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`);
    const payload = (await response.json()) as ApiEnvelope<T> | ApiFailure;
    if (!response.ok || 'error' in payload) {
      throw new Error(
        'error' in payload ? payload.error.message : response.statusText,
      );
    }
    return payload.data;
  }

  async readSignalWindow(
    signalId: string,
    startSeconds: number,
    durationSeconds: number,
  ) {
    const data = await this.get<SignalWindowResponse>(
      `/sessions/${encodeURIComponent(this.manifest.session.session_id)}/signals/${encodeURIComponent(signalId)}/window?start_s=${startSeconds}&duration_s=${durationSeconds}`,
    );
    const signal = this.manifest.signals.find((item) => item.id === signalId);
    if (!signal) throw new Error(`Signal metadata unavailable: ${signalId}`);
    if (
      data.n_samples !== data.samples.length ||
      data.timestamps.length !== data.samples.length ||
      data.unit !== signal.unit ||
      data.sampling_rate_hz !== signal.sampling_rate_hz ||
      Math.abs(
        data.end_s - data.start_s - data.n_samples / data.sampling_rate_hz,
      ) > 1e-9
    ) {
      throw new Error('Signal window contract is internally inconsistent');
    }
    return {
      signal,
      startSeconds: data.start_s,
      durationSeconds: data.duration_s,
      timestamps: data.timestamps,
      samples: data.samples,
    };
  }

  readAnnotations(startSeconds: number, endSeconds: number) {
    return this.get<AnnotationWindowResponse>(
      `/sessions/${encodeURIComponent(this.manifest.session.session_id)}/annotations?start_s=${startSeconds}&end_s=${endSeconds}`,
    );
  }

  readDerived(metric: string, startSeconds: number, endSeconds: number) {
    return this.get<DerivedWindowResponse>(
      `/sessions/${encodeURIComponent(this.manifest.session.session_id)}/derived?metric=${encodeURIComponent(metric)}&start_s=${startSeconds}&end_s=${endSeconds}`,
    );
  }

  readEvents(startSeconds: number, endSeconds: number) {
    return this.get<EventWindowResponse>(
      `/sessions/${encodeURIComponent(this.manifest.session.session_id)}/events?start_s=${startSeconds}&end_s=${endSeconds}`,
    );
  }
}
