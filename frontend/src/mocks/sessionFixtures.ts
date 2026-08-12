import fixtureAJson from '../../../tests/fixtures/session_packages/fixture-neuro/fixture-a/manifest.json';
import fixtureBJson from '../../../tests/fixtures/session_packages/fixture-neuro/fixture-b/manifest.json';
import fixtureCJson from '../../../tests/fixtures/session_packages/fixture-physiology/fixture-c/manifest.json';

import { capabilityNames } from '../types';
import type {
  CapabilityName,
  CapabilitySet,
  CapabilityStatus,
  ProvenanceClass,
  SessionManifest,
} from '../types';

const capabilityStatuses = new Set<CapabilityStatus>([
  'AVAILABLE',
  'UNAVAILABLE',
  'PLANNED',
  'UNKNOWN',
]);
const provenanceClasses = new Set<ProvenanceClass>([
  'raw',
  'imported',
  'derived',
  'simulated',
  'unknown',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseFixtureManifest(value: unknown): SessionManifest {
  if (!isRecord(value) || value.schema_version !== 'dreamcore.session.v1') {
    throw new Error('Unsupported fixture Session Package schema');
  }
  if (
    !isRecord(value.dataset) ||
    typeof value.dataset.id !== 'string' ||
    typeof value.dataset.display_name !== 'string' ||
    !isRecord(value.session) ||
    typeof value.session.session_id !== 'string' ||
    typeof value.session.subject_id !== 'string' ||
    !isRecord(value.recording) ||
    typeof value.recording.duration_seconds !== 'number' ||
    value.recording.duration_seconds <= 0 ||
    !Array.isArray(value.signals) ||
    !isRecord(value.annotations) ||
    !isRecord(value.derived) ||
    !isRecord(value.capabilities) ||
    !isRecord(value.provenance) ||
    !provenanceClasses.has(value.provenance.classification as ProvenanceClass)
  ) {
    throw new Error('Invalid canonical fixture Session Package');
  }

  const normalizedCapabilities = { ...value.capabilities };
  for (const name of capabilityNames) {
    const descriptor = value.capabilities[name];
    if (descriptor === undefined) {
      normalizedCapabilities[name] = {
        status: 'UNKNOWN',
        source: 'unknown',
        reason: 'Capability not declared by this older fixture',
      };
      continue;
    }
    if (
      !isRecord(descriptor) ||
      !capabilityStatuses.has(descriptor.status as CapabilityStatus) ||
      !provenanceClasses.has(descriptor.source as ProvenanceClass)
    ) {
      throw new Error(`Invalid capability descriptor: ${name}`);
    }
  }

  return {
    ...value,
    capabilities: normalizedCapabilities,
  } as unknown as SessionManifest;
}

export const fixtureSessionManifests = [
  parseFixtureManifest(fixtureAJson),
  parseFixtureManifest(fixtureBJson),
  parseFixtureManifest(fixtureCJson),
] as const;

const demoCapabilities = Object.fromEntries(
  capabilityNames.map((name) => [
    name,
    {
      status:
        name === 'hardware_telemetry' || name === 'navigation_alignment'
          ? 'UNAVAILABLE'
          : 'AVAILABLE',
      source: name.startsWith('phase_') ? 'derived' : 'simulated',
      reason:
        name === 'hardware_telemetry' || name === 'navigation_alignment'
          ? 'Demo simulation has no hardware telemetry'
          : 'Deterministic frontend demonstration',
    },
  ]),
) as CapabilitySet;

export const demoSessionManifest: SessionManifest = {
  schema_version: 'dreamcore.session.v1',
  dataset: {
    id: 'demo-simulation',
    display_name: 'Demo Simulation',
    version: 'frontend-v1',
  },
  session: {
    session_id: 'V01-S02',
    subject_id: 'DC-P012',
    visit_id: 'V01',
  },
  recording: {
    duration_seconds: 26280,
  },
  signals: [],
  annotations: {
    sleep_stages: { available: true, source: 'simulated' },
  },
  derived: {},
  capabilities: demoCapabilities,
  provenance: {
    classification: 'simulated',
    source_dataset_uri: null,
    imported_by: 'frontend-demo-adapter',
    notes: 'DEMO SIMULATION — NOT REAL SUBJECT DATA',
  },
};

export function capability(manifest: SessionManifest, name: CapabilityName) {
  return manifest.capabilities[name];
}
