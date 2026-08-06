# DreamCore AI

Research framework for sleep closed-loop regulation — algorithm exploration phase.

> ⚠ Pre-alpha research code. No real-time hardware control. No clinical use.

## What this is

DreamCore AI is the algorithm research component of the DreamCore sleep
closed-loop regulation project. It provides:

- Public sleep EEG data loading and quality checking
- Sleep stage classification with focus on N2/N3
- Slow oscillation detection
- Instantaneous and future phase estimation
- Phase prediction uncertainty quantification and precision gating
- Offline simulation of real-time closed-loop replay
- Mock trigger/skip output (no real stimulation hardware)

## What this is NOT

- A medical device or clinical decision support system
- A real-time stimulation controller
- An end-to-end product with hardware integration
- A trained, production-ready model

## Environment setup

```bash
# Python 3.11 required
python --version  # should be 3.11.x

# Create venv and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Directory map

```
dreamcore-ai/
├── AGENTS.md              — instructions for AI coding agents
├── README.md              — this file
├── pyproject.toml         — project metadata, dependencies, tool config
├── .gitignore             — data, secrets, artifacts
├── configs/
│   └── default.yaml       — research defaults (NOT hardware specs)
├── docs/
│   ├── project_scope.md   — what we build and what we don't
│   ├── unknowns.md        — unresolved product/hardware/data questions
│   ├── research_protocol.md — experimental conventions
│   ├── roadmap.md         — planned milestones
│   ├── decisions.md       — design decisions and rationale
│   ├── progress.md        — what's done, what's next
│   └── hardware_interface.md — placeholder for future hardware integration
├── src/dreamcore/         — package source
│   ├── data/              — data readers (EDF, annotation import)
│   ├── preprocessing/     — filtering, artifact removal, referencing
│   ├── sleep_staging/     — stage label handling, N2/N3 focus
│   ├── slow_oscillation/  — detection, amplitude/period features
│   ├── phase_prediction/  — Hilbert, threshold, state-space methods
│   ├── precision_gating/  — uncertainty estimation, trigger/skip gating
│   ├── simulation/        — offline replay of real-time loop
│   └── evaluation/        — metrics, visualization
├── scripts/               — one-off analysis and plotting scripts
├── experiments/           — per-experiment configs
├── tests/                 — pytest suite
├── results/               — generated outputs (gitignored)
└── data/                  — small metadata only; datasets are gitignored
```

## Current status

- [x] Project initialization
- [ ] Module implementations (all pending)

See `docs/progress.md` for detailed status.

## Quick verify

```bash
pytest -v
```

## Next steps

1. Choose a public sleep dataset (e.g., Sleep-EDF, MASS, DREAMS)
2. Implement `src/dreamcore/data/` reader
3. Implement sleep stage label mapping
4. Implement slow oscillation detection
5. Iterate on phase estimation methods

See `docs/roadmap.md` for full plan.
