# AGENTS.md — DreamCore AI

Instructions for AI coding agents (Codex, Claude Code, etc.) working on this repo.

## Before touching code

1. Read `docs/project_scope.md` — what this project is and is NOT.
2. Read `docs/unknowns.md` — what we don't know yet; don't assume.
3. Read `docs/decisions.md` — past decisions and their rationale.
4. Read `docs/research_protocol.md` — experimental conventions.

## When modifying code

- All parameters MUST come from `configs/default.yaml` or a config object.
  No hardcoded sampling rates, channel names, thresholds, or durations.
- Run `pytest` after every change. Fix failures before pushing.
- Run `ruff check src/ tests/` and `ruff format --check src/ tests/`.

## DO NOT

- Implement ultrasound/transcranial stimulation control.
- Hardcode 100 Hz, a specific EEG channel, or electrode positions.
- Download or commit large datasets (EDF, NPY, FIF, etc.).
- Assume sleeping vs. wake state unless the sleep staging module provides it.
- Store sensitive or patient data in the repo.
- Train models or implement RL / dose optimization / medical decisions.
- Assume a specific product spec. This is algorithm research.

## Repository layout

```
src/dreamcore/   — package code
configs/         — YAML configs (default.yaml is placeholder)
docs/            — project docs (scope, unknowns, decisions, protocol, etc.)
tests/           — pytest tests
scripts/         — one-off analysis scripts
experiments/     — per-experiment configs and logs
results/         — generated figures and tables (gitignored except .gitkeep)
data/            — small metadata; large datasets are gitignored
```
