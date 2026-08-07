# Project Scope

## What DreamCore AI builds

### DreamCore V1 — pre-sleep Alpha research prototype (current priority)

DreamCore V1 studies a pre-sleep workflow: observe awake EEG Alpha, track its
history, estimate an explicitly non-clinical Awake→Drowsy research state, and
produce a simulated abstract `stimulation_demand` that can fall toward a
`ready_to_remove` state. Demand and events are research simulations only.
They are not ultrasound dose, device commands, observed stimulation, or
evidence of a stimulation response.

The first Alpha baseline uses public Sleep-EDF EEG and imported W/N1/N2 labels
for offline evaluation. Real EEG remains unchanged. Alpha features are derived;
demand, ready state, and stimulation events are simulated.

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
- Ultrasound intensity, pressure, duty cycle, PRF, dose, or efficacy estimation
- Treating simulated demand/events as observed stimulation or EEG response

The existing N3, slow-oscillation, and offline Hilbert code remains a retained
research track. The V1 priority change does not delete or reinterpret it.

## Constraints

- All numerical parameters from config, never hardcoded
- Works on public datasets only during Phase 1
- No patient data in repository
- Python 3.11, MNE ecosystem
- Runs on a single machine (no distributed training)
