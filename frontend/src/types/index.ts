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

export type WakeMusicStyle =
  | 'auto'
  | 'soft_piano_ambient'
  | 'bright_morning'
  | 'classical_chamber'
  | 'neoclassical'
  | 'gentle_acoustic'
  | 'calm_ambient';

export type WakeMusicGeneration = {
  generation_id: string;
  cache_key: string;
  session_id: string;
  profile: {
    profile_version: string;
    session_id: string;
    source_window: {
      start_s: number;
      end_s: number;
      selection: string;
      transition_time_s: number | null;
      preceding_stage: string | null;
      wake_stage: string | null;
    };
    physiology: {
      activity_level: number;
      event_rate_level: number;
      event_rate_per_min: number;
      activity_trend: number;
      amplitude_level: number;
      feature_row_count: number;
      source_channel: string;
      source_feature: string;
    };
    music: {
      register: 'low' | 'mid' | 'high';
      density: 'sparse' | 'moderate' | 'moderately_active';
      brightness: 'warm' | 'gradually_brighter' | 'noticeably_brighter';
      expressive_strength: 'delicate' | 'natural' | 'slightly_more_present';
      energy: string;
      energy_curve: string;
      style_family: Exclude<WakeMusicStyle, 'auto'>;
      style_label: string;
      tempo_character: string;
    };
    constraints: {
      max_energy: string;
      max_percussiveness: string;
      allow_aggressive_styles: false;
      allow_vocals: false;
    };
    mapping_version: string;
    generation_seed: number;
    variation_id: string;
    style_selection: 'auto_exploratory' | 'user_override';
    mapping_context: string;
  };
  prompt_configuration: {
    prompt: string;
    prompt_hash: string;
    style_family: string;
    style_label: string;
    variation_id: string;
    variation_description: string;
    generation_seed: number;
  };
  provider: string;
  model: string;
  generated_at: string;
  master_audio: {
    path: string;
    audio_url: string;
    duration_s: number;
    file_size_bytes: number;
    sample_rate_hz: number;
    channels: number;
    bitrate: number | null;
  };
  wake_version: {
    strategy: 'first_excerpt_v1';
    start_s: number;
    duration_s: number;
    encoded_duration_s: number;
    fade_out_s: number;
    fade_out_start_s: number;
    path: string;
    audio_url: string;
    file_size_bytes: number;
    sample_rate_hz: number;
    channels: number;
    bitrate: number | null;
  };
  audio_url: string;
  trace_id: string | null;
  cached: boolean;
  external_generation_stochastic: true;
};

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
  official_source?: string;
  license_source?: string;
  metadata?: Record<string, unknown>;
};

export type CanonicalSignalMetadata = {
  id: string;
  modality: string;
  channel_name: string;
  original_channel_name?: string;
  canonical_role?:
    | 'EEG_FRONTAL'
    | 'EEG_CENTRAL'
    | 'EEG_OCCIPITAL'
    | 'EEG_OTHER'
    | 'EOG_LEFT'
    | 'EOG_RIGHT'
    | 'EOG_HORIZONTAL'
    | 'EMG'
    | 'ECG'
    | 'RESPIRATORY'
    | 'OTHER';
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
    metadata?: Record<string, unknown>;
  };
};

export type DatasetSummary = DatasetIdentity & {
  sessionCount: number;
  availableCapabilities: number;
  subjectCount: number;
  localRecordingCount: number;
  localStatus: 'available_locally' | 'metadata_only' | 'missing' | 'error';
  signalModalities: string[];
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

export type SignalWindowsResponse = {
  session_id: string;
  start_s: number;
  duration_s: number;
  windows: SignalWindowResponse[];
};

export type SleepStageAnnotation = {
  annotation_type: string;
  start_seconds: number;
  duration_seconds: number;
  label: string;
  raw_label?: string;
  normalized_label?: string;
  scoring_standard?: string;
  scorer?: string;
  annotation_source?: string;
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
