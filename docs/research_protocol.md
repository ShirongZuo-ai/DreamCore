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
