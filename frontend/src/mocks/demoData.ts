import type {
  ControllerDecision,
  EEGChannel,
  EEGSampleWindow,
  PhysiologySnapshot,
  SafetyStatus,
  SubjectSession,
  TimelineEvent,
} from '../types';

type DemoWaveConfig = {
  label: string;
  phase: number;
  amplitude: number;
  quality: EEGChannel['quality'];
};

export const demoPresentationConfig = {
  windowSeconds: 10,
  samplingRateHz: 32,
  waveform: [
    { label: 'Fp1', phase: 0.1, amplitude: 0.82, quality: 'good' },
    { label: 'Fp2', phase: 0.52, amplitude: 0.76, quality: 'good' },
    { label: 'F3', phase: 0.95, amplitude: 0.88, quality: 'fair' },
    { label: 'F4', phase: 1.32, amplitude: 0.73, quality: 'good' },
    { label: 'F7', phase: 1.78, amplitude: 0.67, quality: 'fair' },
    { label: 'F8', phase: 2.16, amplitude: 0.79, quality: 'good' },
  ] satisfies DemoWaveConfig[],
} as const;

function createDeterministicSignal(config: DemoWaveConfig): number[] {
  const sampleCount =
    demoPresentationConfig.windowSeconds *
    demoPresentationConfig.samplingRateHz;

  return Array.from({ length: sampleCount }, (_, index) => {
    const t = index / demoPresentationConfig.samplingRateHz;
    const slow = Math.sin(t * Math.PI * 1.45 + config.phase) * 28;
    const alpha = Math.sin(t * Math.PI * 5.2 + config.phase * 0.6) * 5;
    const drift = Math.sin(t * Math.PI * 0.34 + config.phase * 1.4) * 8;
    return Number(((slow + alpha + drift) * config.amplitude).toFixed(3));
  });
}

const demoChannels: EEGChannel[] = demoPresentationConfig.waveform.map(
  (config) => ({
    id: config.label.toLowerCase(),
    label: config.label,
    unit: 'µV',
    quality: config.quality,
    samples: createDeterministicSignal(config),
  }),
);

export const demoSession: SubjectSession = {
  subjectId: 'DC-P012',
  sessionId: 'V01-S02',
  protocolCode: 'Protocol B',
  recordingTime: '01:42:36',
  deviceStatus: 'offline',
  dataLatencyMs: null,
  storageStatus: 'ready',
  batteryPercent: null,
  isDemo: true,
};

export const demoEEGWindow: EEGSampleWindow = {
  source: 'demo',
  startTimestampUs: 0,
  durationSeconds: demoPresentationConfig.windowSeconds,
  samplingRateHz: demoPresentationConfig.samplingRateHz,
  channelOrder: demoChannels.map((channel) => channel.id),
  channels: demoChannels,
};

export const demoDecision: ControllerDecision = {
  sleepStage: 'N3',
  stageConfidence: 0.91,
  state: 'OBSERVING',
  phase: {
    phaseRadians: null,
    precisionDegrees: null,
    predictedUpstateTimestampUs: null,
    validity: 'waiting',
  },
  decision: 'NO_TRIGGER',
  reason: {
    code: 'insufficient_history',
    label: 'Collecting sufficient signal history',
  },
  source: 'demo',
};

export const demoPhysiology: PhysiologySnapshot = {
  source: 'simulated',
  heartRateBpm: 62,
  spo2Percent: 98,
  movement: 'low',
  snoring: 'none-detected',
};

export const demoSafety: SafetyStatus = {
  source: 'demo',
  signalIntegrity: 'demo',
  electrodeContact: 'not-connected',
  deviceTemperatureC: null,
  dataConnection: 'offline',
  navigationAlignment: 'unavailable',
  automaticStimulation: 'disabled',
};

export const demoTimelineEvents: TimelineEvent[] = [
  {
    id: 'marker-1',
    kind: 'manual-marker',
    timestampUs: 1_800_000_000,
    label: 'Demo marker',
    source: 'demo',
  },
  {
    id: 'artifact-1',
    kind: 'artifact',
    timestampUs: 4_200_000_000,
    durationUs: 180_000_000,
    label: 'Simulated artifact interval',
    source: 'demo',
  },
  {
    id: 'skip-1',
    kind: 'skipped-candidate',
    timestampUs: 5_700_000_000,
    label: 'Demo skip',
    source: 'demo',
  },
];

export const demoReviewMetrics = [
  { label: 'Recording Duration', value: '07:18:42', helper: 'Demo session' },
  { label: 'Sleep Onset Latency', value: '18 min', helper: 'Simulated' },
  { label: 'SWS Percentage', value: '21.4%', helper: 'Descriptive only' },
  { label: 'Data Validity', value: '93.8%', helper: 'Simulated estimate' },
] as const;

export const demoSleepStages = [
  { stage: 'W', width: 8 },
  { stage: 'N1', width: 6 },
  { stage: 'N2', width: 19 },
  { stage: 'N3', width: 16 },
  { stage: 'N2', width: 13 },
  { stage: 'REM', width: 11 },
  { stage: 'N2', width: 17 },
  { stage: 'W', width: 10 },
] as const;
