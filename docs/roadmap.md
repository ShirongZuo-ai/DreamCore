# Roadmap

## DreamCore V1 Phase C — AI Wake Music

**Goal**: turn an explicit waking-related EOG feature window into a locally
stored, pleasant instrumental piece through a reproducible exploratory mapping.

- [x] Versioned Wake Music Profile and configurable categorical mapping
- [x] Annotation-confirmed Wake window plus manual research-window selection
- [x] Six bounded styles, seeded Auto choice, and within-style variants
- [x] Explicit energy, percussiveness, aggression, and vocal constraints
- [x] Backend-only MiniMax client, safe errors, immediate download, and cache
- [x] Separate local generation API preserving read-only Session endpoints
- [x] Primary Viewer panel, mapping explanation, native player, and new variation
- [x] Mocked mapping/provider/storage/cache/security/UI test coverage
- [ ] Review SC4001 A–D prompts and audio characteristics with human raters
- [ ] Evaluate mapping and source-window sensitivity across additional sessions

This feature is exploratory generative conditioning, not medical personalization
or validated therapy. MiniMax does not provide deterministic exact note-level
control, and repeated external generation remains stochastic.

## DreamCore V1 Phase B — Eye Movement Sonification

**Goal**: prove that a real public Sleep-EDF EOG signal can reproducibly drive
audible, replay-synchronized musical controls without implying REM or therapy.

- [x] Metadata-driven EOG discovery with no silent EEG substitution
- [x] Full-night filtering, 4 s/1 s activity windows, quality, and coverage
- [x] Robust Eye Movement Candidate events and event-rate feature
- [x] Deterministic Eye Movement / Alpha / baseline mapping
- [x] Additive `dreamcore.session.v1` artifacts and indexed bounded API reads
- [x] Shared EEG/EOG/stage/features/events/control cursor and replay clock
- [x] Browser Web Audio play/mute/reset with safe configured gain
- [x] Eye Movement primary UI and Alpha secondary diagnostics
- [ ] Manual candidate audit and cross-subject sensitivity study
- [ ] Optional MIDI/OSC/EEGsynth output adapter after interface requirements

## Retained Phase A — Pre-sleep Alpha diagnostic research

**Goal**: derive auditable Alpha features from awake/pre-sleep EEG and simulate
a hardware-neutral demand that decreases with sustained drowsiness evidence.

- [x] Welch fixed-band Alpha power and relative power
- [x] Conservative session/channel IAF plus individualized-band profile
- [x] Sliding baseline/short/trend history
- [x] Non-clinical Awake/Drowsy heuristic
- [x] Smoothed, rate-limited, hysteretic simulated demand and event schema
- [x] SC4001 W→N1→N2 two-channel evaluation and QA
- [x] Real-metadata `dreamcore.session.v1` package with windowed EDF references
- [x] Real signal transport for a read-only frontend viewer
- [x] Add an offline replay clock behind `ReplaySource` without changing the
  observed/derived/simulated provenance contract
- [x] Add one authoritative replay time, a five-state clock, window-end feature
  semantics, bounded prefetch/cache, request cancellation, and stale guards
- [x] Synchronize progressive EEG, current imported stage, derived Alpha/state,
  simulated demand/events, seek, and W→N1 navigation
- [x] Add operator-created, in-memory simulated-intervention markers with an
  explicit no-ultrasound-delivered notice and no EEG mutation
- [ ] Validate Alpha/IAF behavior on a dataset with posterior coverage and a
  controlled eyes-open/eyes-closed pre-sleep protocol

All demand/events in Phase A are simulated. No ultrasound parameter or control
is implemented. The milestones below are retained research tracks, not deleted.

## Milestone 0 — Project initialization ✅

- [x] Repository structure
- [x] Configuration framework
- [x] Documentation skeleton
- [x] Minimal import test

## Milestone 1 — Data pipeline

**Goal**: Read public sleep EEG and validate quality.

- [x] Choose public validation dataset (Sleep-EDF Expanded SC)
- [x] Implement `src/dreamcore/data/reader.py` — EDF loader with MNE
- [x] Implement configurable channel stats, NaN checks, and flatline detection
- [x] Implement `src/dreamcore/preprocessing/eeg.py` — configurable reference,
  detrend, bandpass, notch, explicit resampling, and boundary trimming
- [x] Validate reader, annotations, quality, and alignment on one real subject
- [x] Visually compare raw and preprocessed N3 EEG at long and short scales
- [ ] Expand validation and visual review to a second subject
- [x] Add bounded Sleep-EDF, HMC v1.1, and ISRUC Cohort III library ingestion
  with native channel discovery and unified Viewer navigation
- [x] Compare the unchanged Eye Movement V1 detector on representative
  Sleep-EDF, HMC dual-EOG, and ISRUC montages without threshold tuning
- [ ] Complete blinded manual QC of the frozen 150-candidate and 150-control
  Cross-Dataset EOG Validation V1 sample

## Milestone 2 — Sleep staging

**Goal**: Load and use sleep stage labels, focus on N2/N3.

- [x] Implement `src/dreamcore/sleep_staging/labels.py` — label mapping from config
- [x] Implement continuous N3 EEG interval extraction
- [ ] Implement N2 interval extraction
- [ ] Stage distribution summary per subject

## Milestone 3 — Slow oscillation detection

**Goal**: Reliably detect individual slow oscillations.

- [x] Implement `src/dreamcore/slow_oscillation/detector.py`
- [x] Zero-crossing + configurable amplitude/duration candidate filtering
- [x] Visual validation: overlay candidates on raw/detection-band signal
- [x] Report candidate density, amplitude, duration, frequency, and rejection
  reasons for the first subject/segment
- [ ] Review candidates and profile sensitivity across more segments/subjects

**Status**: the first real N3 segment now has a reproducible candidate detector,
complete accepted/rejected audit trail, channel-overlap summary, and reviewed QA
figure. Candidate status is not physiological ground truth.

## Milestone 4 — Phase estimation

**Goal**: Establish phase-estimation baselines, then evaluate causal replay
before considering future-phase prediction.

- [x] Implement offline `src/dreamcore/phase_prediction/hilbert.py`
- [x] Validate the fixed phase convention against accepted detector landmarks
  and export circular-error/cross-channel QA
- [ ] Implement causal filtering and simulated real-time replay with explicit
  algorithmic delay measurement
- [ ] Implement `src/dreamcore/phase_prediction/threshold.py`
- [ ] Implement `src/dreamcore/phase_prediction/state_space.py`
- [ ] Method comparison notebook/script

**Status**: the offline Hilbert baseline is reproducible on two real EEG
channels, preserves invalid samples on the original timeline, and has reviewed
landmark and QA outputs. Its zero-phase FIR and Hilbert transform use future
samples, so it is not evidence of causal or real-time phase performance.

## Milestone 5 — Precision gating

**Goal**: Decide when to trigger vs. skip based on confidence.

- [ ] Implement `src/dreamcore/precision_gating/gate.py`
- [ ] Uncertainty estimation per prediction
- [ ] Trigger/skip decision logic
- [ ] Evaluation: precision/recall of trigger decisions

## Milestone 6 — Offline simulation

**Goal**: Simulate real-time operation from continuous data.

- [ ] Implement `src/dreamcore/simulation/replay.py`
- [ ] Sliding window + mock trigger log
- [ ] End-to-end pipeline script
- [ ] Latency analysis

## Milestone 7 — Evaluation & comparison

**Goal**: Comprehensive method comparison.

- [ ] All phase methods on same data split
- [ ] Per-subject and aggregate metrics
- [ ] Final report in `results/`

## Beyond Phase 1 (TBD)

- Real hardware integration (depends on hardware spec)
- Online adaptation
- Multi-night variability analysis
