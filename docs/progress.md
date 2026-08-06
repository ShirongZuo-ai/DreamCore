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

## Next

- Implement configurable EEG preprocessing without changing the native reader
  sampling-rate validation.
- Visually inspect filtered N3 EEG before implementing slow-oscillation detection.
