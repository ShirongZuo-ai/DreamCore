# Frontend Data Contract

## Contract status

This document describes what the frontend will eventually need; it is not a
claim that the Python repository currently exposes an API. Today there is no
HTTP endpoint, WebSocket server, live EEG stream, device telemetry, or hardware
command channel. The frontend uses deterministic objects from `src/mocks/`.

Status terminology:

- **Currently available offline**: information exists in Python files or
  generated research outputs, but is not served to the frontend.
- **Planned**: a field shape proposed for an offline replay or future API.
- **Unknown**: cannot be fixed before hardware/product specifications exist.

## Session metadata

```ts
type SubjectSession = {
  subjectId: string;
  sessionId: string;
  protocolCode: string;
  recordingTime: string;
  deviceStatus: 'online' | 'offline' | 'connecting' | 'error';
  dataLatencyMs: number | null;
  storageStatus: 'ready' | 'warning' | 'unavailable';
  batteryPercent: number | null;
  isDemo: boolean;
};
```

Dataset subject/recording identifiers and elapsed ranges are currently
available offline. Live device status, latency, storage, and battery are
unknown. Frontend display IDs are Demo placeholders and are not patient data.

## EEG packet

Proposed replay/WebSocket packet, versioned before implementation:

```json
{
  "schema_version": "planned-v1",
  "source": "replay",
  "sequence": 1842,
  "start_timestamp_us": 1723000000000000,
  "sampling_rate_hz": 256,
  "channel_order": ["hardware-defined-channel-id"],
  "sample_count_per_channel": 64,
  "samples_uv": [[0.0, 1.2, -0.7]],
  "signal_quality": [
    {
      "channel_id": "hardware-defined-channel-id",
      "status": "good",
      "reason_codes": []
    }
  ]
}
```

- Timestamps are integer microseconds since Unix epoch for transport. Relative
  replay time may be carried separately as integer microseconds from session
  start. The backend must declare which clock produced a timestamp.
- `sampling_rate_hz` is required in every stream initialization and whenever it
  changes. The frontend must never assume a particular rate.
- `channel_order` is explicit and corresponds one-to-one with rows in
  `samples_uv`; it is not inferred from electrode conventions.
- Sample units are explicit microvolts in this proposed contract. Conversion
  provenance is a backend responsibility.
- Packet duration and batch size are planned configuration, not fixed here.
- Channel names, count, positions, reference scheme, ADC properties, and final
  sample rate remain unknown pending hardware specification.

Python currently reads configurable EEG channels from EDF, records sampling
rate, preserves channel order, and produces offline arrays. No packetizer or
live transport currently exists.

## Signal quality

Planned per-channel fields:

```ts
type SignalQualityPacket = {
  channelId: string;
  status: 'good' | 'fair' | 'poor' | 'not-connected';
  reasonCodes: string[];
  measuredAtUs: number;
  metrics?: Record<string, number | null>;
};
```

Offline Python quality checks currently include NaN ratio and configurable
flatline detection. Contact impedance, electrode attachment, packet loss, and
device diagnostics are unknown and must not be inferred from those checks.

## Sleep stage

```ts
type SleepStagePacket = {
  timestampUs: number;
  stage: 'W' | 'N1' | 'N2' | 'N3' | 'REM' | 'UNKNOWN';
  confidence: number | null;
  source: 'annotation' | 'model' | 'demo';
  modelVersion: string | null;
};
```

Config-driven annotation normalization and N3 interval extraction are currently
available offline. Online staging, stage confidence, and a staging model are
not implemented. The displayed `N3 / 91%` is purely simulated.

## Phase estimate

```ts
type PhaseEstimatePacket = {
  timestampUs: number;
  channelId: string;
  phaseRadians: number | null;
  phaseConventionId: string;
  precisionDegrees: number | null;
  predictedUpstateTimestampUs: number | null;
  validity: 'waiting' | 'valid' | 'invalid';
  reasonCodes: string[];
  causal: boolean;
  algorithmVersion: string;
};
```

An offline, zero-phase Hilbert baseline with validity masks and a documented
phase convention is currently available. It is explicitly non-causal and must
not populate a live prediction field. Causal estimation, online uncertainty,
future up-state prediction, and latency accounting are planned research work.

## Decisions: trigger, skip, and stop

```ts
type DecisionPacket = {
  timestampUs: number;
  decisionId: string;
  controllerState: 'IDLE' | 'OBSERVING' | 'ELIGIBLE' | 'STOPPED' | 'ERROR';
  decision: 'TRIGGER' | 'SKIP' | 'STOP' | 'NO_TRIGGER';
  reasonCode: string;
  reasonDetail?: string;
  candidateTimestampUs: number | null;
  source: 'demo' | 'replay';
};
```

Precision gating and end-to-end replay decisions are planned but not currently
implemented. Only future mock trigger/skip logs are in project scope. `STOP` in
the current frontend is a local UI demonstration and never a hardware command.

## Safety status

```ts
type SafetyStatusPacket = {
  measuredAtUs: number;
  signalIntegrity: 'good' | 'warning' | 'critical' | 'unknown';
  electrodeContact: 'good' | 'partial' | 'poor' | 'not-connected' | 'unknown';
  deviceTemperatureC: number | null;
  dataConnection: 'online' | 'offline' | 'connecting' | 'error';
  navigationAlignment: 'aligned' | 'misaligned' | 'unavailable';
  automaticStimulation: 'disabled';
  interlockReasonCodes: string[];
};
```

All hardware-derived safety fields are unknown pending vendor selection and
approved safety interlocks. `automaticStimulation` remains disabled in this
phase. The frontend must default unknown fields to unavailable/offline rather
than a healthy state.

## Timeline events

`TimelineEvent` uses a typed event kind, integer microsecond timestamp, optional
duration, label, and explicit `demo | replay | live` source. Current timeline
events are placeholders. Python offline candidate/phase CSVs contain some event
timing that could be mapped later, after a stable export schema is agreed.

## Future transports

- **WebSocket (planned):** initialization message with schema/config/channel
  metadata, binary or compact batched samples, monotonic sequence numbers,
  heartbeat, explicit reconnect/gap semantics, and independently throttled
  summary/status messages.
- **Offline replay (planned):** the same decoded domain objects produced from a
  versioned file or HTTP source, paced by a replay clock. Replay must preserve
  original timestamps and disclose that it is not live.

Authentication, endpoint URLs, binary encoding, message batching, retention,
clock synchronization, reconnect policy, backpressure, and hardware identifiers
are unknown. They must be specified before either adapter is built.

## Canonical Session Package contract (Phase 2A)

The canonical manifest version is `dreamcore.session.v1`. Its owned schema and
capability policy are documented in `dataset_session_framework.md`. Python and
the frontend validate the same files under
`tests/fixtures/session_packages/**/manifest.json`; these are marked `TEST
FIXTURE — NOT REAL SUBJECT DATA` and are not evidence that a Python API or real
dataset import exists.

The frontend-facing package contains dataset/session identity, optional visit
and night identifiers, duration plus optional start-time/timezone, lightweight
signal metadata, annotation/derived-result presence, typed capabilities, and
provenance. Complete EEG/physiology arrays are prohibited in catalog summaries
and manifests. Future sample data is obtained only by a windowed read.

Every canonical capability has `AVAILABLE | UNAVAILABLE | PLANNED | UNKNOWN`
status and can carry `source`, `reason`, `derived_by`, and `version`. Absence is
not represented by a fabricated numeric value. UI consumers display the status
and reason and only render sourced values when the capability permits it.

Current transport ownership is deliberately separated:

- **Phase 2A:** deterministic frontend fixture transport plus Python canonical
  domain/repository/registry contracts.
- **Phase 2B:** planned Python-backed catalog and normalized real-dataset
  window transport.
- **Future:** versioned HTTP metadata and offline replay or live WebSocket
  packets mapped into the same canonical types.

Fields marked `simulated` are fixture/demo-only. Real signal locations,
pagination, authentication, clock synchronization, binary packet encoding,
device telemetry, and hardware identifiers remain unknown or planned.
