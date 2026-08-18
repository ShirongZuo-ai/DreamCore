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

## Pre-sleep Alpha V1

Alpha V1 is retained as a secondary diagnostic/comparison track, not the
current primary product signal.

- Use configuration-selected fixed and individualized Alpha profiles.
- Use traditional, inspectable PSD estimation (Welch for the baseline).
- Report session/channel IAF as unavailable when the configured peak evidence
  is insufficient; never fill an IAF from a nominal center frequency.
- Estimate Alpha trend from configured short, trend, and baseline histories;
  never classify state from one window alone.
- W/N1/N2 annotations may evaluate the heuristic offline but are not inputs to
  the Alpha-only Awake/Drowsy score.
- Preserve observed EEG samples. Filtering and derived features must not be
  written back into the source or altered to simulate a response.
- Mark Alpha features and state scores `derived`. Mark every demand, ready state,
  and stimulation event `simulated` with the notice `SIMULATED CONTROL DEMAND —
  NOT ULTRASOUND DOSE`.
- Mark every operator-created offline replay intervention `simulated` with the
  notice `SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED`. Such markers are
  annotations only: they must not mutate EEG/features or call hardware.
- No Alpha result may be described as evidence that ultrasound changed EEG or
  improved sleep.

## Eye Movement / EOG V1

- Discover EOG from recording metadata with configured type/label rules. If no
  unique channel is found, report unavailable; never substitute an EEG channel.
- Preserve the raw EOG. Filtering produces a separate derived signal and never
  writes back into the observed waveform.
- Use configured stage-agnostic sliding windows and window-end timestamps.
- Report RMS/activity, peak-to-peak amplitude, mean absolute derivative, robust
  local-baseline deviation, candidate rate, quality, and complete coverage.
- Call threshold excursions `Eye Movement Candidate`; never call one `REM
  Event`, `Dream Detected`, or `Dream Intensity`.
- Treat polarity as recorded differential-signal polarity. Infer no anatomical
  direction unless an electrode configuration separately supports it.
- Keep imported sleep stage as contextual annotation, not an event-detector gate.
- Persist feature/mapping versions, source channel, source fingerprint,
  processing parameters, recording-relative and absolute window times, seed,
  and coverage.
- Cross-dataset validation freezes the full detector configuration before
  analysis and hashes a machine-readable contract. HMC E1/E2 and ISRUC LOC/ROC
  are analyzed independently; no synthetic horizontal channel is constructed.
- Dual-channel agreement uses deterministic closest-unmatched pairing with a
  primary ±0.5 s tolerance and ±0.25/±1.0 s sensitivity checks.
- Stage comparisons report both counts and stage-exposure-normalized rates.
  ISRUC scorer assignments remain separate. Candidate QC and sampled
  non-candidate QC are distinct, seeded manual-review samples; sampled controls
  do not establish formal recall.

## Sonification V1

- Separate raw signal, feature track, mapping, control frames, and audio renderer.
- Default to Eye Movement; Alpha is an optional comparison and baseline is
  explicitly configured, not fabricated missing physiology.
- Map candidate events to notes, candidate rate to tempo, activity to density
  and brightness, and amplitude to intensity. These are musical mappings only.
- For identical session, time range, configuration, and seed, controls must be
  reproducible.
- Start Web Audio only on a user gesture, keep gain bounded by config, and use
  the existing replay cursor as the sole time source.

## Slow oscillation conventions

- Bandpass filter: configurable `filter_low_hz` to `filter_high_hz`
- Zero-crossing detection, then half-wave amplitude and duration checks
- No assumption about SO shape or symmetry

## Retrospective K-Complex V0

- Select EEG independently from Alpha, prioritizing indexed frontal, then
  central, then other compatible EEG roles while retaining original labels.
- Gate product counts to the configured normalized target stage (N2 by
  default), merge contiguous target-stage epochs into bouts, and preserve raw
  label/scorer provenance.
- Use the configured zero-phase low-frequency filter, local median/MAD
  amplitude and prominence gates, morphology duration bounds, artifact limits,
  and refractory suppression. Thresholds remain identical across datasets.
- A following positive peak is recorded only when it passes its configured
  evidence threshold; otherwise it remains null.
- Human reviews and manual trough candidates are local annotation overlays and
  never mutate automatic detector output.
- V0 uses the complete waveform retrospectively. Report no causal lead time and
  make no before-trough detection claim.
- Product verification uses the frozen B1 Morphology specification after V0.
  Preserve the exact feature order, scaler/logistic family and hyperparameters,
  label eligibility, seed, and inclusive 0.5 threshold. Verification may change
  only accepted/rejected status; every V0 landmark and morphology measurement
  remains unchanged.
- Treat grouped OOF metrics as benchmark evaluation only. The separate final
  all-eligible-data B1 fit is for product inference and has no independent-test
  F1 claim.
- CBraMod is an off-by-default research comparison. The default K-complex path
  must not require its checkpoint, cache, PyTorch, or CUDA.

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
## Multi-dataset provenance and missing-data convention

- Inspect actual source headers before assigning a channel role. Always retain
  the source label, native rate, unit, file, dataset version, and official URI.
- Treat a canonical role as a cross-dataset aid, not a montage replacement. Use
  `OTHER` when evidence is insufficient.
- Preserve raw stage labels and scorer identity. Stage 3 and Stage 4 may both
  normalize to N3; this does not erase the raw distinction.
- For ISRUC Cohort III, retain both expert files. The configured primary scorer
  drives Viewer display; the alternate remains auditable.
- Distinguish `source_available`, `not_computed`, `unsupported`, `missing`, and
  `error`. Never encode absent derived data as zero.
- Read full-night signals only in bounded windows needed by an analysis or
  display. Do not export a duplicate all-sample database.
