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
  'eog',
  'eye_movement_activity',
  'eye_movement_events',
  'sonification_controls',
  'alpha_power',
  'relative_alpha_power',
  'individual_alpha_frequency',
  'alpha_trend',
  'drowsiness_score',
  'stimulation_demand',
  'ready_to_remove',
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
  catalogTransport: 'fixture' | 'http';
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
  'demo-simulation' | 'test-fixture' | 'real-public-dataset' | 'live-device';

export type LoadedSession = {
  dataSource: DataSourceType;
  manifest: SessionManifest;
  fixture: boolean;
  realPublicData: boolean;
};

export type SignalWindowResponse = {
  session_id: string;
  signal_id: string;
  channel: string;
  provenance: ProvenanceClass;
  start_s: number;
  end_s: number;
  duration_s: number;
  sampling_rate_hz: number;
  unit: string;
  n_samples: number;
  timestamps: number[];
  samples: number[];
};

export type SleepStageAnnotation = {
  annotation_type: string;
  start_seconds: number;
  duration_seconds: number;
  label: string;
  raw_label?: string;
  provenance: ProvenanceClass;
};

export type AnnotationWindowResponse = {
  session_id: string;
  start_s: number;
  end_s: number;
  descriptors: Record<string, ContentDescriptor>;
  annotations: SleepStageAnnotation[];
};

export type AlphaFeatureRecord = {
  channel: string;
  window_start_s: number;
  window_end_s: number;
  stage: string;
  absolute_alpha_power: number | null;
  relative_alpha_power: number | null;
  individual_alpha_frequency_hz: number | null;
  iaf_confidence: number | null;
  iaf_available: boolean;
  iaf_reason: string | null;
  window_iaf_hz: number | null;
  window_iaf_confidence: number | null;
  alpha_trend: 'rising' | 'stable' | 'falling' | 'unavailable';
  alpha_trend_slope: number | null;
  alpha_change_from_baseline: number | null;
  drowsiness_score: number | null;
  state_confidence: number | null;
  stimulation_demand: number | null;
  demand_available: boolean;
  ready_to_remove: boolean;
  feature_provenance: 'derived';
  demand_provenance: string;
};

export type EyeMovementFeatureRecord = {
  session_id: string;
  source_channel: string;
  window_start_s: number;
  window_end_s: number;
  recording_start_time: string | null;
  absolute_window_start: string | null;
  absolute_window_end: string | null;
  eog_rms_uv: number | null;
  peak_to_peak_uv: number | null;
  mean_absolute_derivative_uv_per_s: number | null;
  robust_deviation_z: number | null;
  activity_score: number | null;
  amplitude_score: number | null;
  event_rate_per_min: number | null;
  event_candidate: boolean;
  signal_quality: 'valid' | 'invalid';
  signal_quality_reasons: string | null;
  feature_version: string;
  feature_provenance: 'derived';
};

export type EyeMovementEventRecord = {
  event_id: string;
  session_id: string;
  timestamp: number;
  window_start_s: number;
  window_end_s: number;
  duration_s: number;
  amplitude_uv: number;
  polarity: 'positive' | 'negative';
  confidence: number;
  robust_deviation_z: number;
  source_channel: string;
  feature_version: string;
  provenance: 'derived';
  event_type: 'eye_movement_candidate';
};

export type SonificationSource = 'eye_movement' | 'alpha' | 'baseline';

export type SonificationControlFrameRecord = {
  session_id: string;
  source: Exclude<SonificationSource, 'baseline'>;
  source_feature: string;
  window_start_s: number;
  window_end_s: number;
  available: boolean;
  tempo_bpm: number | null;
  density: number | null;
  intensity: number | null;
  brightness_hz: number | null;
  trigger: boolean;
  event_id: string | null;
  note_midi: number | null;
  note_velocity: number | null;
  mapping_version: string;
  control_version: string;
  seed: number;
  provenance: 'sonification_control';
};

export type DerivedWindowResponse = {
  session_id: string;
  metric: string;
  start_s: number;
  end_s: number;
  descriptor: ContentDescriptor;
  records: unknown[];
};

export type SimulatedControlEvent = {
  timestamp: number;
  demand_before: number;
  demand_after: number;
  state: string;
  alpha_power: number;
  relative_alpha_power: number;
  alpha_trend: string;
  confidence: number;
  event_type: string;
  provenance: 'simulated';
  provenance_notice: string;
};

export type EventWindowResponse = {
  session_id: string;
  start_s: number;
  end_s: number;
  descriptor: ContentDescriptor | null;
  events: SimulatedControlEvent[];
};

export type SessionLoadState =
  | { status: 'idle'; session: null; error: null }
  | { status: 'loading'; session: LoadedSession | null; error: null }
  | { status: 'ready'; session: LoadedSession; error: null }
  | { status: 'error'; session: LoadedSession | null; error: string };
