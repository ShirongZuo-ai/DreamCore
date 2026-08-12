import { fixtureSessionManifests } from '../mocks/sessionFixtures';
import type {
  CapabilityName,
  DatasetSummary,
  SessionFilter,
  SessionManifest,
  SessionSummary,
} from '../types';

function containsN3(manifest: SessionManifest): boolean {
  const stages = manifest.annotations.sleep_stages?.metadata?.contains_stages;
  return Array.isArray(stages) && stages.includes('N3');
}

function toSummary(manifest: SessionManifest): SessionSummary {
  return {
    dataset: manifest.dataset,
    sessionId: manifest.session.session_id,
    subjectId: manifest.session.subject_id,
    visitId: manifest.session.visit_id,
    nightId: manifest.session.night_id,
    durationSeconds: manifest.recording.duration_seconds,
    capabilities: manifest.capabilities,
    hasSleepStage: Boolean(manifest.annotations.sleep_stages?.available),
    hasN3: containsN3(manifest),
    provenance: manifest.provenance.classification,
    catalogTransport: 'fixture',
  };
}

export function sessionMatchesFilter(
  session: SessionSummary,
  filter: SessionFilter,
): boolean {
  if (filter.datasetId && session.dataset.id !== filter.datasetId) return false;
  if (filter.subjectId && session.subjectId !== filter.subjectId) return false;
  if (
    filter.minimumDurationSeconds !== undefined &&
    session.durationSeconds < filter.minimumDurationSeconds
  ) {
    return false;
  }
  if (
    filter.hasSleepStage !== undefined &&
    session.hasSleepStage !== filter.hasSleepStage
  ) {
    return false;
  }
  if (filter.hasN3 !== undefined && session.hasN3 !== filter.hasN3) {
    return false;
  }
  return filter.requiredCapabilities.every(
    (name) => session.capabilities[name].status === 'AVAILABLE',
  );
}

function seededIndex(seed: number, length: number): number {
  let value = seed | 0;
  value ^= value << 13;
  value ^= value >>> 17;
  value ^= value << 5;
  return Math.abs(value) % length;
}

export class SessionCatalogService {
  private readonly manifests: readonly SessionManifest[];

  constructor(manifests: readonly SessionManifest[] = fixtureSessionManifests) {
    this.manifests = manifests;
  }

  listDatasets(): DatasetSummary[] {
    const groups = new Map<string, SessionManifest[]>();
    for (const manifest of this.manifests) {
      groups.set(manifest.dataset.id, [
        ...(groups.get(manifest.dataset.id) ?? []),
        manifest,
      ]);
    }
    return [...groups.values()]
      .map((items) => ({
        ...items[0].dataset,
        sessionCount: items.length,
        availableCapabilities: new Set(
          items.flatMap((item) =>
            (Object.keys(item.capabilities) as CapabilityName[]).filter(
              (name) => item.capabilities[name].status === 'AVAILABLE',
            ),
          ),
        ).size,
      }))
      .sort((left, right) => left.id.localeCompare(right.id));
  }

  listSessions(): SessionSummary[] {
    return this.manifests
      .map(toSummary)
      .sort((left, right) =>
        `${left.dataset.id}/${left.sessionId}`.localeCompare(
          `${right.dataset.id}/${right.sessionId}`,
        ),
      );
  }

  searchSessions(query: string, datasetId?: string): SessionSummary[] {
    const normalized = query.trim().toLocaleLowerCase();
    return this.listSessions().filter((session) => {
      if (datasetId && session.dataset.id !== datasetId) return false;
      if (!normalized) return true;
      return [
        session.dataset.id,
        session.dataset.display_name,
        session.sessionId,
        session.subjectId,
        session.visitId ?? '',
      ]
        .join(' ')
        .toLocaleLowerCase()
        .includes(normalized);
    });
  }

  filterSessions(
    candidates: readonly SessionSummary[],
    filter: SessionFilter,
  ): SessionSummary[] {
    return candidates.filter((session) =>
      sessionMatchesFilter(session, filter),
    );
  }

  getSession(datasetId: string, sessionId: string): SessionManifest {
    const manifest = this.manifests.find(
      (item) =>
        item.dataset.id === datasetId && item.session.session_id === sessionId,
    );
    if (!manifest)
      throw new Error(`Session not found: ${datasetId}/${sessionId}`);
    return manifest;
  }

  randomSession(
    candidates: readonly SessionSummary[],
    seed: number,
  ): SessionSummary {
    if (candidates.length === 0) throw new Error('No session candidates');
    const ordered = [...candidates].sort((left, right) =>
      `${left.dataset.id}/${left.sessionId}`.localeCompare(
        `${right.dataset.id}/${right.sessionId}`,
      ),
    );
    return ordered[seededIndex(seed, ordered.length)];
  }

  randomValidSession(
    candidates: readonly SessionSummary[],
    filter: SessionFilter,
    seed: number,
  ): SessionSummary {
    const valid = this.filterSessions(candidates, filter);
    if (valid.length === 0) {
      const requirements = [
        ...filter.requiredCapabilities.map((name) => `${name} available`),
        ...(filter.hasSleepStage ? ['sleep-stage labels available'] : []),
        ...(filter.hasN3 ? ['N3 present'] : []),
      ];
      throw new Error(`No session satisfies: ${requirements.join(', ')}`);
    }
    return this.randomSession(valid, seed);
  }

  async loadSession(
    datasetId: string,
    sessionId: string,
  ): Promise<SessionManifest> {
    return Promise.resolve(this.getSession(datasetId, sessionId));
  }
}

type ApiEnvelope<T> = { api_version: 'v1'; data: T };
type ApiFailure = {
  api_version: 'v1';
  error: { code: string; message: string; details: Record<string, unknown> };
};

export class HttpSessionCatalogService {
  constructor(private readonly baseUrl = '/api/v1') {}

  private async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, { signal });
    const payload = (await response.json()) as ApiEnvelope<T> | ApiFailure;
    if (!response.ok || 'error' in payload) {
      const message =
        'error' in payload ? payload.error.message : response.statusText;
      throw new Error(`DreamCore API: ${message}`);
    }
    if (payload.api_version !== 'v1')
      throw new Error('Unsupported DreamCore API version');
    return payload.data;
  }

  async listDatasets(signal?: AbortSignal): Promise<DatasetSummary[]> {
    const data = await this.get<
      Array<{
        id: string;
        display_name: string;
        version?: string;
        session_count: number;
        available_capabilities: string[];
      }>
    >('/datasets', signal);
    return data.map((item) => ({
      id: item.id,
      display_name: item.display_name,
      version: item.version,
      sessionCount: item.session_count,
      availableCapabilities: item.available_capabilities.length,
    }));
  }

  async listSessions(
    datasetId: string,
    signal?: AbortSignal,
  ): Promise<SessionSummary[]> {
    type ApiSummary = {
      dataset: SessionManifest['dataset'];
      session: SessionManifest['session'];
      recording: SessionManifest['recording'];
      capabilities: SessionManifest['capabilities'];
      has_sleep_stage: boolean;
      has_n3: boolean;
      provenance: SessionManifest['provenance']['classification'];
    };
    const data = await this.get<ApiSummary[]>(
      `/datasets/${encodeURIComponent(datasetId)}/sessions`,
      signal,
    );
    return data.map((item) => ({
      dataset: item.dataset,
      sessionId: item.session.session_id,
      subjectId: item.session.subject_id,
      visitId: item.session.visit_id,
      nightId: item.session.night_id,
      durationSeconds: item.recording.duration_seconds,
      capabilities: item.capabilities,
      hasSleepStage: item.has_sleep_stage,
      hasN3: item.has_n3,
      provenance: item.provenance,
      catalogTransport: 'http',
    }));
  }

  loadSession(_datasetId: string, sessionId: string, signal?: AbortSignal) {
    return this.get<SessionManifest>(
      `/sessions/${encodeURIComponent(sessionId)}`,
      signal,
    );
  }
}

export const sessionCatalogService = new SessionCatalogService();
export const httpSessionCatalogService = new HttpSessionCatalogService();

export const liveReplayEligibility: SessionFilter = {
  requiredCapabilities: ['eeg', 'sleep_stage_labels'],
  optionalCapabilities: ['phase_estimation', 'phase_precision'],
  hasSleepStage: true,
  hasN3: true,
};
