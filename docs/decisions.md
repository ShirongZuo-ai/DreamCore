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
