# Project Scope

## What DreamCore AI builds

### Phase 1 — Algorithm research on public data (current)

| # | Capability | Status |
|---|-----------|--------|
| 1 | EEG data reading and quality checks | pending |
| 2 | Sleep stage label reading (N2, N3 focus) | pending |
| 3 | Slow oscillation detection | pending |
| 4 | Current and future phase estimation | pending |
| 5 | Method comparison: fixed-threshold vs. Hilbert vs. state-space | pending |
| 6 | Phase prediction uncertainty and precision gating | pending |
| 7 | Offline real-time replay simulation | pending |
| 8 | Mock trigger/skip output (no real device) | pending |

### Phase 2+ — TBD after hardware spec is frozen

Not planned yet. Depends on hardware parameters, electrode layout,
and product requirements.

## Explicitly OUT of scope (do not build)

- Real-time stimulation / ultrasound control
- Human subject studies or IRB protocols
- Dose optimization or reinforcement learning
- Medical diagnosis or clinical decision-making
- Production GUI or user-facing application
- Hardware firmware or embedded code
- EEG channel-specific or sampling-rate-specific assumptions
- Any code that assumes a specific product spec

## Constraints

- All numerical parameters from config, never hardcoded
- Works on public datasets only during Phase 1
- No patient data in repository
- Python 3.11, MNE ecosystem
- Runs on a single machine (no distributed training)
