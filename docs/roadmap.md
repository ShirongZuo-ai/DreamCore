# Roadmap

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

**Goal**: Estimate instantaneous and predict future phase.

- [ ] Implement `src/dreamcore/phase_prediction/hilbert.py`
- [ ] Implement `src/dreamcore/phase_prediction/threshold.py`
- [ ] Implement `src/dreamcore/phase_prediction/state_space.py`
- [ ] Method comparison notebook/script

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
