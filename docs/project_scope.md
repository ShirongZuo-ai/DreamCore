# Project Scope

## What DreamCore AI builds

### DreamCore V1 — AI Wake Music and research sonification

The primary product-facing research feature delivers instrumental music after
waking. DreamCore summarizes existing derived EOG activity, candidate rate,
trend, and amplitude over an explicit source window; maps those values to a
versioned Wake Music Profile; and uses bounded style/variation prompts to
condition a backend generative provider. Raw EEG/EOG never goes to the provider.

The existing replay-aligned Web Audio oscillator remains available as
**Research Sonification**. Its controls and the new generative profile are
exploratory musical mappings, not physiological interpretations, therapeutic
outputs, REM labels, dream detection, or emotion inference.

AI Wake Music is an exploratory generative feature. The mapping from physiology
to musical properties is designed by DreamCore. The generated music is not a
clinical intervention or validated therapy. The Viewer is local research
infrastructure presented through a product-first ToC experience; it is not a
clinical product.

Alpha, Theta, Delta, Beta, and imported sleep stage are secondary research
context. Existing Alpha APIs, data, tests, and posterior-vs-frontal comparison
remain available. The first EOG baseline uses SC4001E0 and its discovered
`EOG horizontal` EDF label; the analysis code does not hardcode that label.
Recorded EEG/EOG remains unchanged.

### Multi-Dataset Library V1

DreamCore catalogs a bounded local research subset of Sleep-EDF Expanded 1.0.0,
HMC Sleep Staging 1.1, and ISRUC-Sleep Cohort III through the existing Session
Package and unified Viewer. Dataset-specific adapters inspect source headers,
preserve native sampling rates, original channel labels, stage labels, scorer
identity, and official provenance, then expose bounded reads through one
canonical interface. Large samples stay in source files. Missing derived
features remain `not_computed` or `unsupported` internally, never numeric zero.
When a compatible source exists, the product Viewer automatically computes and
caches Alpha, Eye Movement, retrospective K-Complex V0, and the local Wake
Music Profile. The primary UI
shows only Not available, Analyzing, Ready, or Error; provenance remains in
advanced research metadata.

### Cross-Dataset EOG Validation V1

DreamCore applies the frozen Eye Movement V1 detector to SC4002, HMC SN001/SN002,
and ISRUC Cohort III subjects 1/2. This is a small descriptive validation of
detector behavior across source montages, native sampling rates, stage context,
and ISRUC scorer disagreement. Human review is stored as a separate local
annotation layer and never changes detector output. Candidates are not REM,
dream, saccade, direction, or clinical ground truth.

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
- No public raw physiological files in Git or redistribution through GitHub
- Python 3.11, MNE ecosystem
- Runs on a single machine (no distributed training)

K-Complex V0 is a retrospective, morphology-based N2 candidate detector. The
default product verifier is the frozen B1 Morphology linear model; CBraMod is an
off-by-default research comparison. Both may inspect complete candidate
waveforms and must not be presented as causal trough prediction, prospective
detection, diagnosis, or clinical ground truth.
