# DreamCore AI

Research framework for EOG/eye-movement sonification and retained sleep EEG methods.

> ⚠ Pre-alpha research code. No real-time hardware control. No clinical use.

## What this is

DreamCore V1 currently prioritizes a real-data sonification flow: public
Sleep-EDF EOG → interpretable eye-movement activity/candidates → deterministic
musical controls → synchronized browser audio. Alpha remains available as a
secondary diagnostic and comparison source; the earlier N3/SO/Hilbert research
code is also retained.

It provides:

- Configurable EOG discovery, filtering, activity features, and candidate events
- Deterministic Eye Movement / Alpha / baseline sonification comparison
- Browser Web Audio playback synchronized to the authoritative replay cursor
- Fixed and individualized Alpha spectral diagnostics with explicit IAF availability
- History-aware Alpha trend and non-clinical Awake/Drowsy research scores
- Simulated, smoothed abstract demand/events with explicit provenance
- Versioned read-only local Session HTTP API and bounded EEG windows
- Real SC4001 EEG/EOG/annotation/derived/control viewer with synchronized replay
- Simulated-intervention overlays with explicit no-ultrasound-delivered provenance
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
- An ultrasound dose model, stimulation controller, or stimulation-response dataset

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
│   ├── alpha/             — Alpha PSD, IAF, trend, state, simulated demand
│   ├── eye_movement/      — EOG discovery, filtering, activity, candidates
│   ├── sonification/      — deterministic physiological-to-music controls
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
- [x] Sleep-EDF reading, annotation alignment, and signal quality checks
- [x] Sleep-stage normalization and continuous N3 EEG extraction
- [x] Configuration-driven N3 preprocessing and raw/processed visual review
- [x] Auditable slow-oscillation candidate detection baseline
- [x] SC4001 pre-sleep Alpha V1 analysis and real Session Package
- [x] Read-only real Session transport and SC4001 Alpha frontend viewer
- [x] SC4001 full-night EOG activity/candidates and browser sonification V1
- [ ] Multi-subject EOG detector and sonification sensitivity validation

See `docs/progress.md` for detailed status.

## Quick verify

```bash
pytest -v
```

## Next steps

1. Review candidate-event precision against manually inspected EOG intervals
2. Validate robustness across additional Sleep-EDF subjects and EOG montages
3. Compare sonification mappings without treating musical controls as physiology
4. Keep all intervention concepts simulated until separate evidence exists

See `docs/roadmap.md` for full plan.
