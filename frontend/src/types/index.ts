export type DeviceStatus = 'online' | 'offline' | 'connecting' | 'error';

export type SignalQuality = 'good' | 'fair' | 'poor' | 'not-connected';

export type SleepStage = 'W' | 'N1' | 'N2' | 'N3' | 'REM' | 'UNKNOWN';

export type ControllerState =
  'IDLE' | 'OBSERVING' | 'ELIGIBLE' | 'STOPPED' | 'ERROR';

export type DecisionReason = {
  code: string;
  label: string;
  detail?: string;
};

export type EEGChannel = {
  id: string;
  label: string;
  unit: 'µV';
  quality: SignalQuality;
  samples: number[];
};

export type EEGSampleWindow = {
  source: 'demo' | 'live' | 'replay';
  startTimestampUs: number;
  durationSeconds: number;
  samplingRateHz: number;
  channelOrder: string[];
  channels: EEGChannel[];
};

export type SubjectSession = {
  subjectId: string;
  sessionId: string;
  protocolCode: string;
  recordingTime: string;
  deviceStatus: DeviceStatus;
  dataLatencyMs: number | null;
  storageStatus: 'ready' | 'warning' | 'unavailable';
  batteryPercent: number | null;
  isDemo: boolean;
};

export type PhysiologySnapshot = {
  source: 'simulated';
  heartRateBpm: number;
  spo2Percent: number;
  movement: 'low' | 'moderate' | 'high';
  snoring: 'none-detected' | 'detected' | 'unavailable';
};

export type SafetyStatus = {
  source: 'demo';
  signalIntegrity: 'demo' | 'good' | 'warning' | 'critical';
  electrodeContact: 'not-connected' | 'good' | 'partial' | 'poor';
  deviceTemperatureC: number | null;
  dataConnection: DeviceStatus;
  navigationAlignment: 'unavailable' | 'aligned' | 'misaligned';
  automaticStimulation: 'disabled' | 'enabled';
};

export type TimelineEvent = {
  id: string;
  kind:
    | 'hypnogram'
    | 'stimulation'
    | 'skipped-candidate'
    | 'artifact'
    | 'arousal'
    | 'manual-marker';
  timestampUs: number;
  durationUs?: number;
  label: string;
  source: 'demo' | 'live' | 'replay';
};

export type PhaseEstimate = {
  phaseRadians: number | null;
  precisionDegrees: number | null;
  predictedUpstateTimestampUs: number | null;
  validity: 'waiting' | 'valid' | 'invalid';
};

export type ControllerDecision = {
  state: ControllerState;
  decision: 'TRIGGER' | 'SKIP' | 'STOP' | 'NO_TRIGGER';
  reason: DecisionReason;
  phase: PhaseEstimate;
  sleepStage: SleepStage;
  stageConfidence: number;
  source: 'demo' | 'live' | 'replay';
};

export const capabilityNames = [
  'eeg',
  'sleep_stage_labels',
  'sleep_stage_predictions',
  'slow_oscillation_detection',
  'phase_estimation',
  'phase_precision',
  'decision_simulation',
  'heart_rate',
  'ppg',
  'spo2',
  'movement',
  'snoring',
  'arousals',
  'artifacts',
  'stimulation_events',
  'hardware_telemetry',
  'navigation_alignment',
] as const;

export type CapabilityName = (typeof capabilityNames)[number];
export type CapabilityStatus =
  'AVAILABLE' | 'UNAVAILABLE' | 'PLANNED' | 'UNKNOWN';
export type ProvenanceClass =
  'raw' | 'imported' | 'derived' | 'simulated' | 'unknown';

export type CapabilityDescriptor = {
  status: CapabilityStatus;
  source: ProvenanceClass;
  reason?: string;
  derived_by?: string;
  version?: string;
};

export type CapabilitySet = Record<CapabilityName, CapabilityDescriptor>;

export type DatasetIdentity = {
  id: string;
  display_name: string;
  version?: string;
};

export type CanonicalSignalMetadata = {
  id: string;
  modality: string;
  channel_name: string;
  unit: string;
  sampling_rate_hz: number;
  source: ProvenanceClass;
  available: boolean;
  metadata?: Record<string, unknown>;
};

export type ContentDescriptor = {
  available: boolean;
  source: ProvenanceClass;
  reason?: string;
  derived_by?: string;
  version?: string;
  metadata?: Record<string, unknown>;
};

export type SessionManifest = {
  schema_version: 'dreamcore.session.v1';
  dataset: DatasetIdentity;
  session: {
    session_id: string;
    subject_id: string;
    visit_id?: string;
    night_id?: string;
  };
  recording: {
    start_time?: string;
    duration_seconds: number;
    timezone?: string;
  };
  signals: CanonicalSignalMetadata[];
  annotations: Record<string, ContentDescriptor>;
  derived: Record<string, ContentDescriptor>;
  capabilities: CapabilitySet;
  provenance: {
    classification: ProvenanceClass;
    source_dataset_uri: string | null;
    imported_by?: string;
    notes?: string;
  };
};

export type DatasetSummary = DatasetIdentity & {
  sessionCount: number;
  availableCapabilities: number;
};

export type SessionSummary = {
  dataset: DatasetIdentity;
  sessionId: string;
  subjectId: string;
  visitId?: string;
  nightId?: string;
  durationSeconds: number;
  capabilities: CapabilitySet;
  hasSleepStage: boolean;
  hasN3: boolean;
  provenance: ProvenanceClass;
};

export type SessionFilter = {
  datasetId?: string;
  requiredCapabilities: CapabilityName[];
  optionalCapabilities: CapabilityName[];
  minimumDurationSeconds?: number;
  hasSleepStage?: boolean;
  hasN3?: boolean;
  subjectId?: string;
};

export type DataSourceType =
  'demo-simulation' | 'offline-replay' | 'live-device';

export type LoadedSession = {
  dataSource: DataSourceType;
  manifest: SessionManifest;
  fixture: boolean;
};

export type SessionLoadState =
  | { status: 'idle'; session: null; error: null }
  | { status: 'loading'; session: LoadedSession | null; error: null }
  | { status: 'ready'; session: LoadedSession; error: null }
  | { status: 'error'; session: LoadedSession | null; error: string };
