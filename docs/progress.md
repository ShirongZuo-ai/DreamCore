# Progress Log

## 2026-08-06 — Project initialization

- [x] Repository structure created (`src/` layout, 8 submodules)
- [x] `pyproject.toml` with MNE/NumPy/SciPy/Pandas/Matplotlib/PyYAML/pytest deps
- [x] `.gitignore` covering data, secrets, and artifacts
- [x] `configs/default.yaml` with placeholder research defaults
- [x] Documentation skeleton: AGENTS.md, README.md, docs/*
- [x] `AGENTS.md` with AI coding agent instructions
- [x] `unknowns.md` listing unresolved product/hardware/data questions
- [x] `decisions.md` recording 6 initial architectural decisions
- [x] `roadmap.md` with 7 milestones
- [x] `research_protocol.md` with experimental conventions
- [x] Package structure with `__init__.py` in all submodules
- [x] Minimal import test passes (`test_import.py`)
- [x] `ruff` format/lint check passed on generated code
- [x] Sleep-EDF reader and configurable signal quality checks

## 2026-08-06 — Milestone 1 Step 2 real Sleep-EDF validation

- [x] Fetched subject 0, recording 1 through MNE's Sleep PhysioNet interface
  with published SHA-1 verification:
  - `SC4001E0-PSG.edf` (48,338,048 bytes)
  - `SC4001EC-Hypnogram.edf` (4,620 bytes)
- [x] Loaded the real pair through the existing `load_edf()` implementation.
- [x] Confirmed 100 Hz, 79,500 seconds, 7,950,000 samples, and 7 channels:
  `EEG Fpz-Cz`, `EEG Pz-Oz`, `EOG horizontal`, `Resp oro-nasal`,
  `EMG submental`, `Temp rectal`, and `Event marker`.
- [x] Read 154 original hypnogram annotations and confirmed stages 2, 3, and 4.
- [x] Original stage totals: W 59,910 s; stage 1 1,740 s; stage 2 7,500 s;
  stage 3 3,030 s; stage 4 3,570 s; R 3,750 s; unscored `?` 6,900 s.
- [x] Verified time alignment: PSG `[0, 79500)` s is fully covered by the
  hypnogram. The hypnogram ends at 86,400 s because its final unscored `?`
  annotation begins exactly at the PSG endpoint and extends for 6,900 s.
- [x] Quality report passed: every channel has a NaN ratio of 0 and no identical
  run exceeds the configured 5 s flatline threshold.
- [x] Generated `results/sleep_edf_summary.json` (ignored by Git).
- [x] Added network-free synthetic tests for summary generation and alignment.

## 2026-08-06 — Milestone 1 Step 3 label normalization and N3 extraction

- [x] Added config-driven Sleep-EDF R&K label normalization for W, N1, N2, N3,
  REM, UNKNOWN, and MOVEMENT; stage 3 and stage 4 both map to N3.
- [x] Added configurable unknown-label behavior (`map_to_unknown` or `raise`).
- [x] Clip all annotations to the half-open PSG range before normalization.
- [x] Merge adjacent equal normalized labels using a configured gap tolerance
  while preserving their raw-label sources.
- [x] Require explicit EEG channel names and validate their MNE channel types.
- [x] Added reproducible CSV/JSON metadata output without saving signal arrays.
- [x] Real SC4001E0 result: 154 original annotations, 153 after clipping, and
  71 N3 annotations merged into 31 continuous N3 intervals.
- [x] Real N3 duration: 6,600 s total; longest interval 2,070 s
  (`[33330, 35400)` s); all 31 intervals passed the 30 s minimum.
- [x] Extracted `EEG Fpz-Cz` and `EEG Pz-Oz` at the MNE Raw rate of 100 Hz;
  every metadata row has a sample count consistent with its duration.
- [x] Generated `results/n3_segments.csv` and `results/n3_segments.json`, both
  ignored by Git. No derived signal files were saved.
- [x] Added network-free tests for mapping, unknown labels, clipping, merging,
  duration filtering, channel selection, sample counts, and metadata output.

## 2026-08-06 — Milestone 2 Step 1 N3 EEG preprocessing and visualization

- [x] Added `preprocessing/eeg.py` with configuration-driven channel selection,
  optional average/named-channel re-reference, optional notch filtering,
  bandpass filtering, demean/linear detrending, explicit optional resampling,
  and boundary trimming.
- [x] Added raw, broadband sleep EEG, and slow-oscillation observation profiles.
  They are research defaults rather than product specifications.
- [x] Resampling is disabled for the Sleep-EDF smoke run. When configured, both
  rates and changed sample counts are recorded and covered by tests.
- [x] Reused the reader, label normalization, interval merge, and N3 extraction
  pipeline in `scripts/visualize_n3_eeg.py`; no existing logic was duplicated.
- [x] Selected representative segment `SC4001E0-PSG_n3_0002`, a 600 s merged
  stage 3/stage 4 interval at `[31200, 31800)` s, rather than the 2,070 s longest
  interval. Both configured EEG channels were retained at native 100 Hz.
- [x] Applied demean plus 0.5–4 Hz FIR bandpass with no notch, no additional
  re-reference, and no resampling. A 5 s discard at each boundary retained
  `[31205, 31795)` s (590 s, 59,000 samples per channel).
- [x] Generated ignored long-window `[31260, 31380)` s and short-window
  `[31290, 31310)` s PNG comparisons plus
  `results/n3_eeg_preprocessing_summary.json`.
- [x] Retained-segment statistics in µV (raw → processed): `EEG Fpz-Cz` mean
  0.172 → 0.004, SD 29.952 → 28.716, peak-to-peak 255.250 → 252.905;
  `EEG Pz-Oz` mean -0.346 → 0.007, SD 18.575 → 17.399, peak-to-peak
  159.407 → 155.383.
- [x] Manual export review found stable baselines without obvious clipping or
  boundary artifacts. The 20 s view shows coherent low-frequency morphology in
  both channels, including a prominent synchronous deflection near 10–11 s;
  event-versus-artifact classification remains deliberately unresolved.
- [x] Added network-free unit/integration tests for configuration, channel
  errors, parameter validation, demeaning, resampling, sample/time accounting,
  boundary trimming, source immutability, and two-figure/JSON generation.

## 2026-08-06 — Milestone 2 Step 2 slow-oscillation candidate baseline

- [x] Added `slow_oscillation/detector.py` with linearly interpolated zero
  crossings and complete downward-upward-downward candidate cycles.
- [x] Extracted event boundaries, trough/positive-peak timing and amplitude,
  peak-to-peak amplitude, half-wave/full-cycle duration, estimated frequency,
  and signed down/up slopes for accepted and rejected candidates.
- [x] Added research-only `broad_slow_wave` and `strict_slow_oscillation`
  profiles. The strict profile is the primary real-data output; the broad
  profile also completed a real smoke run using temporary outputs.
- [x] Added no-threshold, fixed-threshold, and per-channel adaptive-quantile
  amplitude strategies. The strict profile used the configured 75th percentile
  rather than a fixed 75 µV assumption.
- [x] Added auditable rejection reasons for duration, NaN/non-finite input,
  retained-boundary proximity, configured peak-to-peak maximum, invalid time
  masks, and amplitude threshold.
- [x] Reused the reader, label normalization, N3 extraction, and preprocessing
  pipeline for `SC4001E0-PSG_n3_0002`; analyzed `[31205, 31795)` s (590 s) at
  100 Hz on `EEG Fpz-Cz` and `EEG Pz-Oz`.
- [x] Strict-profile real result: Fpz-Cz accepted 78 of 708 candidates
  (7.932/min; adaptive threshold 86.969 µV), while Pz-Oz accepted 79 of 676
  (8.034/min; adaptive threshold 52.831 µV).
- [x] Accepted-event median full-cycle duration / peak-to-peak amplitude /
  frequency: Fpz-Cz 1.008 s / 102.756 µV / 0.992 Hz; Pz-Oz 1.012 s /
  65.805 µV / 0.989 Hz.
- [x] Cross-channel accepted-event overlap: 39 overlapping pairs; 34/78 Fpz-Cz
  events (43.590%) and 37/79 Pz-Oz events (46.835%) overlap an event on the
  other channel; total pairwise overlap was 22.206 s.
- [x] Global rejection counts (non-exclusive): below adaptive threshold 1,154;
  full cycle too short 687; negative half-wave too short 376; full cycle too
  long 17; negative half-wave too long 8; near boundary 6. No real candidate
  hit NaN, extreme-amplitude, or invalid-mask rejection in this segment.
- [x] Wrote ignored `slow_oscillation_events.csv`,
  `slow_oscillation_summary.json`, and `slow_oscillation_qa.png`. The 20 s QA
  window contains 55 candidates (3 accepted, 52 rejected).
- [x] Manual QA confirmed raw/detection-band alignment, zero crossings at the
  filtered baseline, extrema inside their half-waves, and clear accepted versus
  rejected encoding. This is algorithm QA, not manual physiological labeling.
- [x] Added network-free synthetic and integration coverage for known-frequency
  crossings, extrema, durations, amplitude strategies, artifacts, empty input,
  channel independence, input immutability, summary/CSV output, overlap, and QA
  export.

## 2026-08-07 — Milestone 2 Step 3 offline Hilbert phase baseline

- [x] Added `phase_prediction/hilbert.py` with independent per-channel analytic
  signals, wrapped/unwrapped phase, amplitude envelopes, optional instantaneous
  frequency, and explicit validity/reason masks that preserve the time axis.
- [x] Defined the project phase convention with one fixed `-pi` offset from raw
  Hilbert phase: downward zero `-pi/2`, trough `0`, upward zero `pi/2`, and
  positive peak `pi`. No event-specific fitting or phase adjustment is used.
- [x] Added configurable invalidation for filter/Hilbert boundaries, original
  NaNs, explicit invalid ranges, low envelope, and out-of-range instantaneous
  frequency. Empty, constant, and too-short inputs fail explicitly.
- [x] Retained subject, recording, segment, channel, sampling rate,
  preprocessing profile, detector profile, and phase profile provenance.
- [x] Reused the existing N3 extraction, broadband preprocessing, and strict
  slow-oscillation detector on `SC4001E0-PSG_n3_0002`: `[31205, 31795)` s,
  590 s, 59,000 samples per channel at 100 Hz.
- [x] Real valid-phase ratios were 83.302% for `EEG Fpz-Cz` and 82.775% for
  `EEG Pz-Oz`. Of the 78/79 accepted detector candidates, 56/55 passed the
  configured event-level phase validity and forward-evolution checks.
- [x] Across valid landmarks, circular MAE / median absolute error was
  5.841° / 0.292° for Fpz-Cz and 5.764° / 0.640° for Pz-Oz. Zero-crossing
  errors were below 0.015° mean; extrema errors were larger (8.713–13.959°),
  as expected when a Hilbert phase of a non-sinusoidal waveform is compared
  with sample extrema.
- [x] Found 39 temporally overlapping accepted-event pairs; 33 had valid phase
  at the overlap midpoint. The Fpz-Cz-minus-Pz-Oz circular mean was -2.897 rad
  (-165.987°), with circular dispersion 0.283. This is descriptive algorithm
  output, not a neural synchrony or connectivity result.
- [x] Wrote ignored `hilbert_phase_landmarks.csv`,
  `hilbert_phase_summary.json`, and `hilbert_phase_qa.png`. Manual QA of the
  configured 20 s `[31290, 31310)` window confirmed aligned channels, expected
  landmark ordering, visible phase wraps, envelope thresholds, and explicit
  invalid regions. Only accepted candidates are overlaid.
- [x] Added network-free synthetic unit and end-to-end tests for the phase
  convention, wrapping, unwrapping, circular error, envelope/frequency,
  validity masks, error cases, channel independence, input immutability,
  provenance, landmarks, cross-channel comparison, and all three outputs.
- [x] Explicitly labeled the FIR/Hilbert path as an offline, zero-phase,
  non-causal baseline that may use future samples and cannot support a
  real-time prediction or trigger claim.

## Next

- Implement causal filtering and simulated real-time replay with explicit
  algorithmic delay accounting; do not infer online performance from the
  offline Hilbert result.
- Expand manual candidate review and sensitivity analysis across detector
  profiles, segments, and subjects before treating density as a stable metric.

## 2026-08-07 — Phase 2A generic dataset and session framework

- [x] Added the versioned `dreamcore.session.v1` manifest, typed capability
  semantics, filesystem package repository, generic adapter contract, registry,
  filters, deterministic random selection, and windowed replay-source boundary.
- [x] Added three tiny shared synthetic contract fixtures covering available,
  unavailable, planned, unknown, derived, and partial-physiology behavior.
- [x] Added the Dataset Library, shareable session details, source/session
  loader, in-app selection persistence, and capability-aware Live Console.
- [x] Kept all fixtures explicitly marked as not real subject data; no EDF
  reader, real replay, API, WebSocket, hardware telemetry, or control was added.
- [x] Phase A1/A2 superseded the planned Phase 2B item with the first approved
  real package plus adapter-backed catalog/window transport, without changing
  the core fixture contracts.

## 2026-08-07 — DreamCore V1 Phase A1 pre-sleep Alpha pipeline

- [x] Added configuration-driven Welch PSD, fixed/individualized Alpha bands,
  conservative IAF peak detection, Alpha envelope, quality gating, sliding
  baseline/short/trend histories, and rising/stable/falling/unavailable trends.
- [x] Added an explicitly non-clinical Alpha-only Awake/Drowsy heuristic. Stage
  annotations are retained only for offline comparison.
- [x] Added bounded simulated demand with confidence/quality gating, minimum
  valid observation, smoothing, rate limiting, hysteresis, sustained ready
  evidence, and simulated frontend-neutral events. EEG is never modified.
- [x] Evaluated SC4001 `[29730, 31140)` s using 30 s windows every 10 s:
  88 W, 10 N1, and 37 N2 stage-pure windows per channel.
- [x] Neither 900 s Wake baseline had a reliable session IAF under the configured
  3 dB prominence rule. In Wake, Fpz-Cz had 59/88 reliable window peaks (SD
  1.717 Hz) and Pz-Oz had 78/88 (SD 1.278 Hz); across W/N1/N2 the counts were
  89/135 and 106/135. Session IAF remains unavailable.
- [x] Median fixed-band relative Alpha W/N1/N2 was 0.0173/0.0498/0.0260 for
  Fpz-Cz and 0.1255/0.1000/0.0370 for Pz-Oz. Posterior Alpha declined across
  stages; the frontal bipolar derivation did not show the same monotonic pattern.
- [x] Wake Fpz-Cz relative Alpha was 86.2% below Pz-Oz by the configured
  descriptive ratio. This is not a validated future-wearable information-loss metric.
- [x] All 270 channel-windows passed the current basic signal-quality thresholds.
  IAF reliability, rather than basic amplitude/finite coverage, was the main
  unavailable feature.
- [x] The frontal-controlled simulated demand produced 135 events (all explicitly
  simulated), with 94 demand-available points and no `ready_to_remove` point.
  Its late N2 rise exposes the frontal heuristic limitation rather than a
  stimulation effect.
- [x] Generated ignored Alpha CSV/JSON/PNG outputs and a tracked metadata-only
  real Session Package. Registry discovery, 2 s EDF window reads, annotation
  reads, and derived-result references were verified.
- [x] Added synthetic tests covering Alpha detection, IAF absence, band profiles,
  power, trend states, quality gates, controller dynamics, provenance, source
  immutability, and session serialization. Existing N3/SO/Hilbert tests remain.

## 2026-08-07 — DreamCore V1 Phase A2 real Session transport and Alpha viewer

- [x] Added a versioned, local, GET-only `/api/v1` WSGI transport over the
  existing DatasetRegistry/DatasetAdapter boundary.
- [x] Added catalog, session, signal metadata, bounded signal window,
  annotation-window, derived-window, and simulated-event endpoints with
  structured errors and preserved capabilities/provenance.
- [x] Defined an explicit signal contract containing `uV`, sampling rate,
  sample count, timestamps, start/end, and samples; recording-boundary clipping
  is covered without a full-record endpoint.
- [x] Added `HttpSessionCatalogService` and `HttpReplaySource` while retaining
  deterministic fixture transports. Dataset Library now exposes Demo
  Simulation, Test Fixture, and Real Public Dataset sources.
- [x] Loaded SC4001 through the real Session Package without session-id
  branches and displayed two windowed EEG channels on one uPlot time axis.
- [x] Added synchronized manual navigation, imported W/N1/N2 stage overlays,
  Alpha/IAF/trend/state panels, and simulated demand/event panels.
- [x] Kept `Unavailable — No reliable alpha peak` for both SC4001 session IAFs
  and displayed `SIMULATED CONTROL DEMAND — NOT ULTRASOUND DOSE` separately
  from observed and derived content.
- [x] Added Python transport tests, frontend HTTP/viewer tests, real-data
  Playwright coverage, and ignored desktop/mobile QA screenshots.

## 2026-08-07 — Offline replay and simulated-intervention overlay

- [x] Added a Session Package configuration-driven client clock with
  play/pause, reset, speed selection, bounded-window rollover, and one shared
  cursor across observed, imported, derived, and simulated panels.
- [x] Added an operator action that records a browser-memory-only simulated
  intervention at the current cursor and shows synchronized orange markers.
- [x] Added the mandatory notice `SIMULATED INTERVENTION — NO ULTRASOUND
  DELIVERED`; no hardware endpoint, command, ultrasound parameter, persistence,
  or source EEG mutation was introduced.
- [x] Added a persistent two-channel legend to the Alpha panel and unit/E2E
  coverage for replay advancement, intervention provenance, alert text, and
  responsive layout.

## 2026-08-07 — DreamCore V1 Phase A3 synchronized offline replay

- [x] Replaced the viewer-local timer with an independent five-state replay
  clock and one authoritative `sessionTimeSeconds` shared by every panel.
- [x] Added play/pause/restart/seek, 0.5×/1×/2×/5×/10× speeds, manual window
  navigation, configured W→N1 jump, and an all-session seek slider.
- [x] Added progressive recorded-EEG reveal, current imported-stage tracking,
  window-end Alpha/state availability, and reached-time gating for simulated
  events and `ready_to_remove`.
- [x] Added a configured bounded LRU cache, next-window prefetch, AbortSignal
  cancellation, and stale-response protection without a frame-level API loop.
- [x] Added explicit Observed/Imported/Derived/Simulated flow language and the
  warning that simulated control events did not produce the recorded EEG.
- [x] Added clock, end-state, cache-eviction, prefetch, cancellation, stale
  response, viewer synchronization, provenance, and browser replay coverage.
- [x] Generated ignored QA screenshots for paused, playing, W→N1, Alpha plus
  simulated demand, and 390 px mobile states.
- [x] Corrected replay chart synchronization by positioning the white cursor in
  uPlot's measured plot coordinates and retaining the final revealed EEG sample
  in display downsampling. Added a labelled stepwise last-value hold so sparse
  Alpha/state/demand records visibly advance with replay without creating new
  metric values.

## 2026-08-12 — Eye Movement Sonification V1

- [x] Confirmed the actual SC4001 EDF labels and discovered `EOG horizontal`
  from metadata/configured patterns. MNE classifies this legacy EDF label as a
  generic EEG type, so type-only discovery would have missed it.
- [x] Processed all 7,950,000 EOG samples at the EDF-native 100 Hz rate. All
  samples were finite. Generated 79,497 stage-agnostic 4 s windows at a 1 s
  step; 79,497 were accepted and none rejected.
- [x] Added RMS, peak-to-peak, mean absolute derivative, robust local deviation,
  normalized activity/amplitude, candidate flag, and 30 s candidate rate.
- [x] Detected 617 robust `Eye Movement Candidate` events across the full
  recording. Coverage is 4.0–79,500.0 s. No event is labeled REM or dream.
- [x] Added exact relative/absolute window times, source channel, versions,
  processing parameters, source SHA-256, quality, coverage, and rejection
  diagnostics to the Session Package.
- [x] Added deterministic controls: event→note, rate→tempo,
  activity→density/brightness, amplitude→intensity, plus Alpha comparison and
  configured baseline. The mapping seed and bounds are persisted.
- [x] Added raw/filtered EOG, activity/event, four control, audio, and comparison
  UI to the existing Viewer. Every panel uses the existing replay clock/cursor.
- [x] Added user-gesture Web Audio play/mute/reset with configured master gain.
  Observed EEG/EOG is never modified.
- [x] Kept Alpha APIs/tests/panels and moved their UI under secondary Research /
  Diagnostics with a single-session interpretation note.
- [x] Retained CSV audit exports and added a SQLite time index. The measured
  120 s derived-feature API read decreased from whole-CSV parsing to about
  0.05 s on the local validation machine.
