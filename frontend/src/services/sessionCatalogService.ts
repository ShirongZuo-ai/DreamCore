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

export const sessionCatalogService = new SessionCatalogService();

export const liveReplayEligibility: SessionFilter = {
  requiredCapabilities: ['eeg', 'sleep_stage_labels'],
  optionalCapabilities: ['phase_estimation', 'phase_precision'],
  hasSleepStage: true,
  hasN3: true,
};
