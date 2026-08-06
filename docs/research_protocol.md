# Research Protocol

Experimental conventions for DreamCore AI Phase 1.

## Principles

1. **Config-driven**: every parameter reads from `configs/default.yaml` (or override).
2. **Reproducible**: fixed random seeds, logged configs, versioned dependencies.
3. **Modular**: each analysis step is a separate module; compose via config/scripts.
4. **No hardware assumptions**: code must work with any montage and sampling rate.

## Experiment workflow

1. Write config variant in `experiments/<name>.yaml`
2. Run pipeline script from `scripts/`
3. Output goes to `results/<experiment_name>/`
4. Log the git commit hash and full config alongside results

## Dataset conventions

- Store raw data outside the repo (e.g., `~/datasets/sleep-edf/`)
- Use `data/` only for small metadata files (channel lists, subject splits)
- Never commit `.edf`, `.fif`, `.npy`, or `.csv` raw data

## Sleep stage labels

- Use `config.sleep_staging.stage_labels` for mapping, never hardcoded strings
- Primary focus: N2 (spindle-bearing, SO present) and N3 (slow-wave dominant)

## Slow oscillation conventions

- Bandpass filter: configurable `filter_low_hz` to `filter_high_hz`
- Zero-crossing detection, then half-wave amplitude and duration checks
- No assumption about SO shape or symmetry

## Phase estimation

- Implement **at least** three methods:
  1. Fixed-threshold crossing
  2. Hilbert transform (analytic signal)
  3. State-space oscillator model
- Compare with same evaluation harness

## Precision gating

- Gate on: prediction uncertainty, SNR, cycle consistency
- Output: binary trigger/skip decision per analysis window
- Log decisions for post-hoc analysis

## Offline simulation

- Sliding window over continuous data
- At each step: preprocess → detect SO → estimate phase → gate → mock trigger
- Record timestamp, phase, confidence, gating decision
- No actual stimulation signal generated

## Evaluation

- Cross-validation where applicable
- Per-subject and aggregate metrics
- Always report mean ± std across folds/subjects
