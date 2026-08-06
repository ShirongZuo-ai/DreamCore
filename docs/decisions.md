# Design Decisions

Record of architectural choices and rationale. Update as decisions are made or revised.

## DD-001: src layout

**Decision**: Use `src/` layout (`src/dreamcore/`) rather than flat package.

**Rationale**:
- Prevents accidental imports of the package from the repo root during development.
- Forces `pip install -e .` which catches packaging issues early.
- Standard in modern Python scientific projects.

**Date**: 2026-08-06

---

## DD-002: Config-driven parameters

**Decision**: All numerical parameters, channel names, filter ranges, and thresholds
must be read from YAML config, never hardcoded.

**Rationale**:
- Hardware parameters are unknown. Hardcoding 100 Hz or "Cz" now creates a
  mess when real specs arrive.
- Enables rapid A/B testing of parameter values without code changes.
- Every experiment run is fully reproducible from its config file.

**Date**: 2026-08-06

---

## DD-003: Python 3.11 floor

**Decision**: Minimum Python version 3.11.

**Rationale**:
- MNE 1.5+ targets 3.9+; 3.11 provides worthwhile performance improvements.
- 3.11 is stable and widely available on research HPC systems.
- Avoids 3.12+ compatibility risks with native deps (MNE, SciPy).

**Date**: 2026-08-06

---

## DD-004: MNE as EEG backbone

**Decision**: Use MNE-Python for EEG I/O and basic processing, not raw NumPy.

**Rationale**:
- MNE handles EDF, FIF, BrainVision, and other formats transparently.
- Provides montage, filtering, and visualization out of the box.
- Widely used in EEG research — easy to hire/collaborate.

**Date**: 2026-08-06

---

## DD-005: No real-time or hardware control in Phase 1

**Decision**: Phase 1 is purely algorithmic. Offline simulation only, mock trigger output.

**Rationale**:
- Hardware specs are unknown.
- Real-time constraints would distort algorithm design prematurely.
- Easier to iterate on algorithms with offline replay than embedded code.

**Date**: 2026-08-06

---

## DD-006: Three phase estimation methods minimum

**Decision**: Implement fixed-threshold, Hilbert, and state-space methods; compare rigorously.

**Rationale**:
- No single method is universally best across SNR conditions.
- Comparison provides evidence for which method to use when hardware is known.
- State-space methods are promising but need validation against simpler baselines.

**Date**: 2026-08-06

---

## DD-007: Sleep-EDF SC as the first real-data reader validation

**Decision**: Validate the EDF reader on one Sleep-EDF Expanded sleep-cassette
recording pair (subject 0, recording 1), fetched through MNE's supported
PhysioNet dataset interface. Keep the original hypnogram descriptions unchanged
in the validation summary.

**Rationale**:
- One PSG/Hypnogram pair is the smallest useful real-data integration check.
- MNE's fetcher selects the matching files and verifies their published hashes.
- Raw R&K stage descriptions make this validation independent of the later
  label-normalization policy.
- Dataset files and generated summaries remain outside Git tracking.

**Date**: 2026-08-06

---

## DD-008: Normalize R&K stages before interval extraction

**Decision**: Normalize Sleep-EDF R&K labels through dataset configuration,
mapping both stage 3 and stage 4 to the project label N3. Clip annotations to
the half-open PSG range before normalization and merge adjacent equal labels
only when their gap is within a configured tolerance. Preserve every raw label
that contributed to a merged interval.

Unknown raw labels follow a configured policy: map to `UNKNOWN` by default or
raise an explicit error. N3 extraction requires explicitly configured or
CLI-selected EEG channels and produces metadata only by default.

**Rationale**:
- R&K stage 3 and stage 4 together correspond to the project's N3 analysis set.
- Clipping prevents trailing or otherwise out-of-range hypnogram annotations
  from producing samples beyond the PSG.
- Preserved raw-label provenance keeps the normalization auditable.
- Explicit EEG channel selection prevents auxiliary signals from entering
  slow-oscillation analysis accidentally.
- Metadata-only output is reproducible without creating large derived datasets.

**Date**: 2026-08-06

---

## DD-009: Preserve native sampling and compare preprocessing profiles explicitly

**Decision**: Preprocess extracted N3 EEG through named YAML profiles. Keep
separate profiles for unmodified visualization, broadband sleep EEG, and
slow-oscillation observation. The Sleep-EDF slow-oscillation observation
profile applies per-channel demeaning and a 0.5–4 Hz FIR bandpass, keeps the
native sample rate, does not add a notch filter or re-reference the already
bipolar channels, and discards 5 seconds from each filtered segment boundary.

Resampling occurs only when `target_sampling_rate_hz` is non-null. Every run
records original/output rates, processing order, selected channels, parameters,
sample counts, and retained time range. Visual review uses a configured
representative segment and configured long/short windows rather than selecting
the longest interval automatically.

**Rationale**:
- Named profiles keep raw comparison, general sleep preprocessing, and the
  narrow slow-oscillation view scientifically distinct.
- Preserving 100 Hz avoids an unnecessary transformation in the first visual
  baseline; future resampling remains explicit and testable.
- Sleep-EDF EEG channels are bipolar derivations, so an additional reference is
  not assumed without a separate experimental rationale.
- Filtering before boundary removal, then dropping configured edges, reduces
  the chance that filter transients enter the review windows.
- Fixed windows and complete metadata make visual inspection reproducible.

These settings are research defaults for this dataset, not final product or
hardware parameters.

**Date**: 2026-08-06

---

## DD-010: Treat zero-crossing detections as auditable candidates, not SO truth

**Decision**: Define one candidate cycle as three consecutive detection-band
crossings: downward, upward, then the next downward crossing. The first
downward crossing is the event start, the upward crossing separates the
negative and positive half-waves, and the next downward crossing is the event
end. The minimum sample in the negative half-wave is the trough; the maximum
sample in the following positive half-wave is the positive peak.

Every structurally complete cycle is retained. Duration, amplitude, NaN,
boundary, extreme-amplitude, and configured invalid-mask checks append explicit
rejection reasons instead of deleting the event. A candidate may have multiple
reasons. For filtering only, isolated non-finite samples are linearly
interpolated; any candidate overlapping those original samples is still
rejected as `nan_or_nonfinite`.

Provide two named research profiles:

- `broad_slow_wave`: 0.5–4 Hz, broad duration bounds, no amplitude threshold.
- `strict_slow_oscillation`: 0.5–1.25 Hz, longer-cycle bounds, and a per-channel
  adaptive peak-to-peak threshold at a configured quantile.

Adaptive thresholds are calculated separately per subject recording and EEG
channel from candidates that first pass non-amplitude checks. Fixed thresholds
remain supported but are not the default and 75 µV is not encoded as a final
standard. Accepted cross-channel overlap means positive temporal intersection
above the configured minimum; report both overlapping pairs and unique events.

`down_slope` is the signed zero-to-trough amplitude change divided by elapsed
time. `up_slope` is the trough-to-positive-peak amplitude change divided by
elapsed time. Both use µV/s.

**Rationale**:
- The three-crossing definition supplies a complete negative-positive cycle
  with reproducible boundaries and interpretable features.
- Retaining rejected candidates makes parameter effects and artifact decisions
  inspectable after the run.
- Per-channel adaptive amplitude handling accommodates the strong amplitude
  difference between the two Sleep-EDF bipolar derivations without claiming a
  universal physiological cutoff.
- Separate broad and strict profiles expose sensitivity to the research
  definition instead of presenting one setting as ground truth.

These outputs are offline algorithm candidates only. They are not manually
confirmed physiological slow oscillations and are not suitable for triggering.

**Date**: 2026-08-06
