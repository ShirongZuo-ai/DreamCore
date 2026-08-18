# Frontend Data Contract

## Contract status

Phase A2 exposes a local read-only `/api/v1` HTTP service for canonical offline
sessions. Phase A3 adds a browser-owned offline replay clock over the same
bounded GET endpoints. There is still no WebSocket, live EEG, device telemetry,
or hardware command channel. Deterministic fixture transport remains available.

## Actual offline signal window

```json
{
  "session_id": "sc4001-alpha-v1",
  "signal_id": "eeg-1",
  "channel": "EEG Fpz-Cz",
  "provenance": "raw",
  "start_s": 30590.0,
  "end_s": 30710.0,
  "duration_s": 120.0,
  "sampling_rate_hz": 100.0,
  "unit": "uV",
  "n_samples": 12000,
  "timestamps": [30590.0],
  "samples": [0.0]
}
```

The shortened arrays above illustrate fields only. In every actual response,
`n_samples == len(timestamps) == len(samples)` and
`end_s - start_s == n_samples / sampling_rate_hz`. `uV` is explicit and must
not be inferred by the frontend. Requests are bounded by configured maximum
duration and can be clipped only at the recording end.

## Offline replay time contract

- `sessionTimeSeconds` is the sole authoritative replay time.
- The visible signal range is `[visibleStartSeconds, visibleEndSeconds)` and is
  shared by EEG, annotations, derived metrics, and simulated events.
- Imported sleep stage at time `t` satisfies
  `start_seconds <= t < start_seconds + duration_seconds`.
- Alpha V1 feature timestamps use **analysis-window end** semantics. A record is
  visible only when `window_end_s <= sessionTimeSeconds`.
- Eye Movement V1 features and sonification controls use the same
  recording-relative seconds and **analysis-window end** semantics.
- Raw EOG and derived filtered EOG are separate signal records; the derived
  track never replaces or mutates the raw track.
- Eye Movement Candidate events are visible only when
  `event.timestamp <= sessionTimeSeconds` and are not REM/dream labels.
- Between two feature timestamps, trend charts extend the most recently
  available derived value to `sessionTimeSeconds` as an explicitly labelled
  stepwise last-value hold. This endpoint is a display continuation, not a new
  Alpha estimate; the value changes only when the next source record is reached.
- Simulated events are visible only when
  `event.timestamp <= sessionTimeSeconds`.
- UI display downsampling and masking do not change HTTP samples, timestamps,
  units, or the underlying recorded EEG.

Each precomputed Alpha descriptor also carries `metadata.analysis`. It declares
the recording-relative time reference and seconds unit, evaluation range,
analysis-window length and step, attempted/accepted/rejected window counts,
rejection-reason counts, exact channel names, total feature-row count, and the
first/last `window_end_s`. This metadata explains bounded windows outside
derived coverage without generating substitute values or fetching the full
feature table.

The replay clock is local visualization state. It is not returned by the API,
not persisted in the Session Package, and not evidence of real-time acquisition.

## Eye Movement V1 derived records

`eye_movement_activity_v1` returns bounded rows with `session_id`,
`source_channel`, `window_start_s`, `window_end_s`, optional absolute ISO window
times, RMS, peak-to-peak, mean absolute derivative, robust deviation,
activity/amplitude scores, event rate, quality/reasons, and feature version.
Unavailable/invalid numerical fields are `null`, never zero-filled.

`eye_movement_events_v1` returns bounded Eye Movement Candidate rows with event
ID, timestamp, event window/duration, signed amplitude, signal polarity,
confidence, robust score, source channel, version, and `derived` provenance.

Every descriptor contains explicit coverage start/end, window/step, row count,
source channel, recording-relative seconds, and window-end semantics. The raw
signal may start at 0 while the first 4 s feature ends at 4 s; this is expected
and displayed explicitly.

## Sonification control records

`sonification_control_v1` is a separate namespace with `eye_movement` or
`alpha` source, source feature, window bounds, availability, tempo, density,
intensity, brightness, optional trigger/event/note/velocity, mapping/control
versions, and seed. Provenance is `sonification_control`, not raw/annotation.
The configured baseline is a UI/audio comparison and is never used to replace
missing physiology.

Derived audit exports remain CSV, while the adapter uses an indexed SQLite
artifact for bounded time queries. This storage choice is internal to the
DatasetAdapter and does not change `/api/v1/.../derived` responses.

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

Python reads configurable EEG channels from EDF, records sampling rate,
preserves channel order, and exposes bounded offline windows through the local
read-only HTTP service. No live packetizer or streaming transport exists.

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
- **Offline replay clock (planned):** the same decoded domain objects produced from a
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
- **Phase A2:** implemented Python-backed catalog and normalized real-dataset
  window transport.
- **Offline replay simulation:** a configuration-driven frontend clock advances
  a cursor over those bounded windows. Operator-created intervention markers
  exist only in browser memory and always retain `simulated` provenance plus a
  no-ultrasound-delivered notice.
- **Future:** live WebSocket packets may map into the same canonical types.

Fields marked `simulated` may appear in fixtures or real-public-data packages,
but always describe abstract simulated control—not observed stimulation or an
EEG effect. Authentication, clock synchronization, binary packet encoding,
device telemetry, and hardware identifiers remain unknown or planned.

## Automatic K-Complex V0 + Morphology B1 product contract

The automatic-analysis status adds `k_complex` with the same `NOT_AVAILABLE |
ANALYZING | READY | ERROR` states as other product features. Its identity is
recording plus source fingerprint, detector version, and configuration hash.

The local K-Complex detail response exposes `candidate_count`, `verified_count`,
and `rejected_count`. Every V0 proposal remains in `events` and carries
`verification_method=morphology_b1`, `verification_probability`,
`verification_status`, `original_morphology_score`, and `trough_s`. The default
product view includes verified candidates; rejected-by-verifier proposals remain
available through an explicit inspection control. Rejection is not a ground
truth non-K-complex label.

The response also contains N2 bouts, primary/focus channel metadata, immutable
detector and verifier identities, review progress, and separate manual trough
candidates. Event time fields are recording-relative seconds. `positive_peak_s`
is nullable and `causal_lead_time` is always null for V0. Verification never
changes onset, trough, positive peak, end, or morphology. The browser retrieves
waveform samples only through the existing bounded multi-signal endpoint, using
the configured event focus window. CBraMod stays behind an advanced comparison
toggle and is off by default.

Review mutations accept only Looks right, Wrong, or Uncertain plus bounded
optional notes. Manual marking accepts a recording-relative cursor only inside
configured N2. Both persist locally as annotation overlays and never rewrite
automatic event artifacts.
