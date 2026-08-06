# Roadmap

## Milestone 0 — Project initialization ✅

- [x] Repository structure
- [x] Configuration framework
- [x] Documentation skeleton
- [x] Minimal import test

## Milestone 1 — Data pipeline

**Goal**: Read public sleep EEG and validate quality.

- [ ] Choose public dataset (Sleep-EDF candidate)
- [ ] Implement `src/dreamcore/data/reader.py` — EDF loader with MNE
- [ ] Implement `src/dreamcore/data/quality.py` — channel stats, NaN check, flatline detection
- [ ] Implement `src/dreamcore/preprocessing/filter.py` — bandpass, notch
- [ ] Test on 1-2 subjects, verify outputs visually

## Milestone 2 — Sleep staging

**Goal**: Load and use sleep stage labels, focus on N2/N3.

- [ ] Implement `src/dreamcore/sleep_staging/labels.py` — label mapping from config
- [ ] Implement N2/N3 epoch extraction
- [ ] Stage distribution summary per subject

## Milestone 3 — Slow oscillation detection

**Goal**: Reliably detect individual slow oscillations.

- [ ] Implement `src/dreamcore/slow_oscillation/detect.py`
- [ ] Zero-crossing + amplitude/duration thresholding
- [ ] Visual validation: overlay detection on raw/filtered signal
- [ ] Report SO density, amplitude, duration per subject

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
