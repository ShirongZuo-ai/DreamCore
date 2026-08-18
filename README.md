# DreamCore AI

Research framework for physiology-conditioned AI Wake Music, EOG sonification,
and retained sleep EEG methods.

> ⚠ Pre-alpha research code. No real-time hardware control. No clinical use.

## What this is

DreamCore V1 now prioritizes a post-waking generative flow: public Sleep-EDF EOG
→ existing derived eye-movement features → versioned Wake Music Profile →
DreamCore-designed musical directions → MiniMax instrumental generation →
locally stored master MP3 → configurable 60-second Wake Version → Viewer
playback. The full generated master remains available without modification.
The earlier synchronized Web Audio
oscillator path remains available as **Research Sonification**. Alpha remains a
secondary diagnostic source; the N3/SO/Hilbert research code is retained.

AI Wake Music is an exploratory generative feature. The mapping from physiology
to musical properties is designed by DreamCore. The generated music is not a
clinical intervention or validated therapy.

It provides:

- A multi-dataset library with Dataset → Subject → Recording navigation for
  bounded local Sleep-EDF Expanded, HMC v1.1, and ISRUC-Sleep Cohort III data
- Native-rate, per-channel EDF/REC inspection, canonical channel roles, raw
  labels, normalized stages, provenance, and explicit not-computed states
- Configurable EOG discovery, filtering, activity features, and candidate events
- Versioned Wake Music profiles, bounded style/variation prompts, safety caps,
  local generation cache, and backend-only MiniMax integration
- Annotation-confirmed pre-Wake source-window selection plus manual research windows
- Viewer style selection, generation status, mapping explanation, local MP3 player,
  config-driven new variations, default 60-second Wake Version, and optional
  Full Track playback
- Deterministic Eye Movement / Alpha / baseline sonification comparison
- Browser Web Audio playback synchronized to the authoritative replay cursor
- Fixed and individualized Alpha spectral diagnostics with explicit IAF availability
- History-aware Alpha trend and non-clinical Awake/Drowsy research scores
- Simulated, smoothed abstract demand/events with explicit provenance
- Versioned read-only local Session HTTP API and bounded EEG windows
- Real SC4001 EEG/EOG/annotation/derived/control viewer with synchronized replay
- Simulated-intervention overlays with explicit no-ultrasound-delivered provenance
- Public sleep EEG data loading and quality checking
- Retrospective K-Complex V0 candidates with the frozen, dependency-light B1
  Morphology verifier as product default and optional CBraMod comparison
- Sleep stage classification with focus on N2/N3
- Slow oscillation detection
- Instantaneous and future phase estimation
- Phase prediction uncertainty quantification and precision gating
- Offline simulation of real-time closed-loop replay
- Mock trigger/skip output (no real stimulation hardware)

## What this is NOT

- A medical device or clinical decision support system
- A real-time stimulation controller
- A production or clinical product with hardware integration
- A trained, production-ready model
- An ultrasound dose model, stimulation controller, or stimulation-response dataset

## Environment setup

```bash
# Python 3.11 required
python3 --version  # should be 3.11.x

# Create venv and install
python3 -m venv .venv
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
│   ├── wake_music/        — profile, mapping, prompt, provider, cache/storage
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
- [x] AI-generated instrumental Wake Music V1 with local storage and Viewer playback
- [x] Multi-Dataset Library V1 adapters, catalog, bounded reads, API, and Viewer navigation
- [x] Frozen Cross-Dataset EOG Validation V1 full-night artifacts, agreement/stage/scorer summaries, and manual-QC Viewer workflow
- [x] Signal Validation V1 contract, official DREAMS adapters, synthetic validation, and internal dashboard
- [x] Frozen B1 Morphology K-complex verifier productization with separate grouped OOF evidence and final-fit provenance
- [ ] Multi-subject EOG detector and sonification sensitivity validation

See `docs/progress.md` for detailed status.

Signal Validation reproduction and metric semantics are documented in
`docs/signal_validation_v1.md`.

## Quick verify

```bash
.venv/bin/python3 -m pytest
cd frontend && npm run test:run
```

## Next steps

1. Review the SC4001 Wake Music A–D comparison without treating musical choices as physiology
2. Review candidate-event precision against manually inspected EOG intervals
3. Run the unchanged Eye Movement pipeline on the catalog's representative
   Sleep-EDF, HMC dual-EOG, and ISRUC recordings
4. Keep all intervention concepts simulated until separate evidence exists

See `docs/roadmap.md` for full plan.
