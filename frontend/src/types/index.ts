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
