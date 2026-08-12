# Project Scope

## What DreamCore AI builds

### DreamCore V1 — eye-movement sonification prototype (current priority)

DreamCore V1 studies a replay-aligned workflow: observe a real public EOG
channel, derive interpretable activity and Eye Movement Candidate events, map
them deterministically to musical controls, and render audible browser sound.
The mappings are exploratory sonification hypotheses, not physiological
interpretations, therapeutic outputs, REM labels, or dream detection.

Alpha, Theta, Delta, Beta, and imported sleep stage are secondary research
context. Existing Alpha APIs, data, tests, and posterior-vs-frontal comparison
remain available. The first EOG baseline uses SC4001E0 and its discovered
`EOG horizontal` EDF label; the analysis code does not hardcode that label.
Recorded EEG/EOG remains unchanged.

### Phase 1 — Algorithm research on public data (current)

| # | Capability | Status |
|---|-----------|--------|
| 1 | EEG data reading and quality checks | pending |
| 2 | Sleep stage label reading (N2, N3 focus) | pending |
| 3 | Slow oscillation detection | pending |
| 4 | Current and future phase estimation | pending |
| 5 | Method comparison: fixed-threshold vs. Hilbert vs. state-space | pending |
| 6 | Phase prediction uncertainty and precision gating | pending |
| 7 | Offline real-time replay simulation | implemented for bounded Session windows |
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
- Labeling an operator-created replay marker as delivered ultrasound
- Equating an eye-movement candidate with REM, a dream, or dream content
- Inferring left/right eye direction from a single unsupported differential channel
- Describing sonification as a validated therapy, diagnosis, or sleep outcome

The existing N3, slow-oscillation, and offline Hilbert code remains a retained
research track. The V1 priority change does not delete or reinterpret it.

## Constraints

- All numerical parameters from config, never hardcoded
- Works on public datasets only during Phase 1
- No patient data in repository
- Python 3.11, MNE ecosystem
- Runs on a single machine (no distributed training)
