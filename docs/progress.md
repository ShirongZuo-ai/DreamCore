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
- [ ] Module implementations — all pending, see roadmap

## Next

- Milestone 1: Choose public dataset and implement data reader.
  First task for Codex: implement `src/dreamcore/data/reader.py`
  to load Sleep-EDF files via MNE.
