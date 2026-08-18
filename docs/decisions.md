# Design Decisions

Record of architectural choices and rationale. Update as decisions are made or revised.

## DD-001: src layout

**Decision**: Use `src/` layout (`src/dreamcore/`) rather than flat package.

**Rationale**:
- Prevents accidental imports of the package from the repo root during development.
- Forces `pip install -e .` which catches packaging issues early.
- Standard in modern Python scientific projects.

**Date**: 2026-08-06

---

## DD-002: Config-driven parameters

**Decision**: All numerical parameters, channel names, filter ranges, and thresholds
must be read from YAML config, never hardcoded.

**Rationale**:
- Hardware parameters are unknown. Hardcoding 100 Hz or "Cz" now creates a
  mess when real specs arrive.
- Enables rapid A/B testing of parameter values without code changes.
- Every experiment run is fully reproducible from its config file.

**Date**: 2026-08-06

---

## DD-003: Python 3.11 floor

**Decision**: Minimum Python version 3.11.

**Rationale**:
- MNE 1.5+ targets 3.9+; 3.11 provides worthwhile performance improvements.
- 3.11 is stable and widely available on research HPC systems.
- Avoids 3.12+ compatibility risks with native deps (MNE, SciPy).

**Date**: 2026-08-06

---

## DD-004: MNE as EEG backbone

**Decision**: Use MNE-Python for EEG I/O and basic processing, not raw NumPy.

**Rationale**:
- MNE handles EDF, FIF, BrainVision, and other formats transparently.
- Provides montage, filtering, and visualization out of the box.
- Widely used in EEG research — easy to hire/collaborate.

**Date**: 2026-08-06

---

## DD-005: No real-time or hardware control in Phase 1

**Decision**: Phase 1 is purely algorithmic. Offline simulation only, mock trigger output.

**Rationale**:
- Hardware specs are unknown.
- Real-time constraints would distort algorithm design prematurely.
- Easier to iterate on algorithms with offline replay than embedded code.

**Date**: 2026-08-06

---

## DD-006: Three phase estimation methods minimum

**Decision**: Implement fixed-threshold, Hilbert, and state-space methods; compare rigorously.

**Rationale**:
- No single method is universally best across SNR conditions.
- Comparison provides evidence for which method to use when hardware is known.
- State-space methods are promising but need validation against simpler baselines.

**Date**: 2026-08-06

---

## DD-007: Sleep-EDF SC as the first real-data reader validation

**Decision**: Validate the EDF reader on one Sleep-EDF Expanded sleep-cassette
recording pair (subject 0, recording 1), fetched through MNE's supported
PhysioNet dataset interface. Keep the original hypnogram descriptions unchanged
in the validation summary.

**Rationale**:
- One PSG/Hypnogram pair is the smallest useful real-data integration check.
- MNE's fetcher selects the matching files and verifies their published hashes.
- Raw R&K stage descriptions make this validation independent of the later
  label-normalization policy.
- Dataset files and generated summaries remain outside Git tracking.

**Date**: 2026-08-06

---

## DD-008: Normalize R&K stages before interval extraction

**Decision**: Normalize Sleep-EDF R&K labels through dataset configuration,
mapping both stage 3 and stage 4 to the project label N3. Clip annotations to
the half-open PSG range before normalization and merge adjacent equal labels
only when their gap is within a configured tolerance. Preserve every raw label
that contributed to a merged interval.

Unknown raw labels follow a configured policy: map to `UNKNOWN` by default or
raise an explicit error. N3 extraction requires explicitly configured or
CLI-selected EEG channels and produces metadata only by default.

**Rationale**:
- R&K stage 3 and stage 4 together correspond to the project's N3 analysis set.
- Clipping prevents trailing or otherwise out-of-range hypnogram annotations
  from producing samples beyond the PSG.
- Preserved raw-label provenance keeps the normalization auditable.
- Explicit EEG channel selection prevents auxiliary signals from entering
  slow-oscillation analysis accidentally.
- Metadata-only output is reproducible without creating large derived datasets.

**Date**: 2026-08-06

---

## DD-009: Preserve native sampling and compare preprocessing profiles explicitly

**Decision**: Preprocess extracted N3 EEG through named YAML profiles. Keep
separate profiles for unmodified visualization, broadband sleep EEG, and
slow-oscillation observation. The Sleep-EDF slow-oscillation observation
profile applies per-channel demeaning and a 0.5–4 Hz FIR bandpass, keeps the
native sample rate, does not add a notch filter or re-reference the already
bipolar channels, and discards 5 seconds from each filtered segment boundary.

Resampling occurs only when `target_sampling_rate_hz` is non-null. Every run
records original/output rates, processing order, selected channels, parameters,
sample counts, and retained time range. Visual review uses a configured
representative segment and configured long/short windows rather than selecting
the longest interval automatically.

**Rationale**:
- Named profiles keep raw comparison, general sleep preprocessing, and the
  narrow slow-oscillation view scientifically distinct.
- Preserving 100 Hz avoids an unnecessary transformation in the first visual
  baseline; future resampling remains explicit and testable.
- Sleep-EDF EEG channels are bipolar derivations, so an additional reference is
  not assumed without a separate experimental rationale.
- Filtering before boundary removal, then dropping configured edges, reduces
  the chance that filter transients enter the review windows.
- Fixed windows and complete metadata make visual inspection reproducible.

These settings are research defaults for this dataset, not final product or
hardware parameters.

**Date**: 2026-08-06

---

## DD-010: Treat zero-crossing detections as auditable candidates, not SO truth

**Decision**: Define one candidate cycle as three consecutive detection-band
crossings: downward, upward, then the next downward crossing. The first
downward crossing is the event start, the upward crossing separates the
negative and positive half-waves, and the next downward crossing is the event
end. The minimum sample in the negative half-wave is the trough; the maximum
sample in the following positive half-wave is the positive peak.

Every structurally complete cycle is retained. Duration, amplitude, NaN,
boundary, extreme-amplitude, and configured invalid-mask checks append explicit
rejection reasons instead of deleting the event. A candidate may have multiple
reasons. For filtering only, isolated non-finite samples are linearly
interpolated; any candidate overlapping those original samples is still
rejected as `nan_or_nonfinite`.

Provide two named research profiles:

- `broad_slow_wave`: 0.5–4 Hz, broad duration bounds, no amplitude threshold.
- `strict_slow_oscillation`: 0.5–1.25 Hz, longer-cycle bounds, and a per-channel
  adaptive peak-to-peak threshold at a configured quantile.

Adaptive thresholds are calculated separately per subject recording and EEG
channel from candidates that first pass non-amplitude checks. Fixed thresholds
remain supported but are not the default and 75 µV is not encoded as a final
standard. Accepted cross-channel overlap means positive temporal intersection
above the configured minimum; report both overlapping pairs and unique events.

`down_slope` is the signed zero-to-trough amplitude change divided by elapsed
time. `up_slope` is the trough-to-positive-peak amplitude change divided by
elapsed time. Both use µV/s.

**Rationale**:
- The three-crossing definition supplies a complete negative-positive cycle
  with reproducible boundaries and interpretable features.
- Retaining rejected candidates makes parameter effects and artifact decisions
  inspectable after the run.
- Per-channel adaptive amplitude handling accommodates the strong amplitude
  difference between the two Sleep-EDF bipolar derivations without claiming a
  universal physiological cutoff.
- Separate broad and strict profiles expose sensitivity to the research
  definition instead of presenting one setting as ground truth.

These outputs are offline algorithm candidates only. They are not manually
confirmed physiological slow oscillations and are not suitable for triggering.

**Date**: 2026-08-06

---

## DD-011: Use a fixed-offset offline Hilbert phase as geometry baseline

**Decision**: Estimate continuous phase independently for each configured EEG
channel after a configured zero-phase FIR bandpass. Convert SciPy's analytic
signal phase to the project convention with one fixed offset of `-pi`:

- downward zero crossing: `-pi/2`;
- negative trough: `0`;
- upward zero crossing: `pi/2`;
- positive peak: `pi` (equivalent to wrapped `-pi`).

The offset is fixed for the entire profile and is never fitted per event. Keep
the original sample timeline and attach a boolean validity mask. Mark configured
segment boundaries, original non-finite samples, configured invalid intervals,
samples below the configured envelope threshold, and samples outside the
configured instantaneous-frequency range as invalid rather than deleting them.
For the first Sleep-EDF baseline, use a 0.5–1.25 Hz phase band, a 5 s invalid
boundary at each end, a per-channel 10th-percentile envelope floor, and a
0.2–2.0 Hz instantaneous-frequency validity range.

Accepted detector landmarks are used only to test consistency with the current
zero-crossing geometry. Cross-channel comparison samples phase at the midpoint
of overlapping accepted candidate intervals and reports circular direction and
dispersion. Neither comparison is physiological ground truth or evidence of
neural synchrony or causality.

**Rationale**:

- A fixed convention makes phase values reproducible across events and channels.
- Separate invalid-reason masks preserve the time axis and expose why a phase
  sample was excluded.
- Detector landmarks offer a useful implementation and geometry check without
  being mislabeled as manually validated brain phase.
- Circular statistics correctly handle the `-pi`/`pi` boundary.

Both the FIR filtering and Hilbert transform are offline and non-causal and may
use future samples. This baseline cannot establish real-time phase prediction
performance. The next implementation stage must introduce causal filtering and
simulated real-time replay before any online claim is considered.

**Date**: 2026-08-07

---

## DD-012: Put dataset-specific knowledge behind a canonical session boundary

**Decision**: Use the versioned `dreamcore.session.v1` package between dataset
adapters and all catalog/replay/UI consumers. Represent every capability with
`AVAILABLE`, `UNAVAILABLE`, `PLANNED`, or `UNKNOWN` plus optional provenance and
reason metadata. Missing content is displayed explicitly and is never replaced
with simulated medical values. Seeded random selection operates on a supplied
candidate collection; valid random selection applies a generic session filter
first.

**Rationale**:

- A second dataset should add an adapter or normalized package, not Live Console
  branches.
- Typed capabilities distinguish absent data from future work and unresolved
  specifications.
- Metadata-only catalogs and windowed reads scale without embedding signals in
  manifests.
- Shared fixtures keep the Python and TypeScript contracts aligned while no
  transport API exists.

Phase 2A uses synthetic TEST FIXTURES only. It does not implement a real dataset
reader, playback clock, WebSocket, device transport, or stimulation control.

**Date**: 2026-08-07

---

## DD-013: Make pre-sleep Alpha the V1 priority and keep control demand simulated

**Decision**: DreamCore V1 prioritizes a pre-sleep Alpha research pipeline over
an overnight N3 stimulation workflow. Use fixed 8–13 Hz and individualized-band
profiles from config, Welch PSD, conservative peak-based IAF availability,
multi-window trend history, and a non-clinical Alpha-only Awake/Drowsy heuristic.
Imported W/N1/N2 annotations are evaluation labels, not heuristic inputs.

The controller output is a bounded abstract `stimulation_demand`. Quality and
confidence gating, minimum observation time, exponential smoothing, rate limits,
hysteresis, and sustained ready evidence are configured. Demand, ready state,
and every stimulation event are `simulated` and carry `SIMULATED CONTROL DEMAND
— NOT ULTRASOUND DOSE`. They never alter source EEG and never map to ultrasound
pressure, intensity, duty cycle, PRF, dose, hardware commands, or efficacy.

Extend `dreamcore.session.v1` with Alpha capability names without changing the
schema version because its generic capability/derived/provenance descriptors
already express raw, imported, derived, and simulated content. Real manifests
contain references, not full EEG arrays; signal reads remain windowed.

**Rationale**:

- A traditional spectral baseline is inspectable before complex models.
- Explicit IAF unavailability prevents nominal frequencies from masquerading as
  subject-specific measurements.
- History and controller dynamics prevent one noisy window from causing a large
  simulated demand change.
- Provenance separation prevents simulated control concepts from being confused
  with public EEG observations or real stimulation responses.
- Retaining the N3/SO/Hilbert modules preserves prior research without making it
  the current V1 direction.

**Date**: 2026-08-07

---

## DD-014: Keep real-session HTTP transport read-only and adapter-backed

**Decision**: Expose canonical Session Packages through a versioned local
`/api/v1` GET-only WSGI service. Catalog, manifest, signal-window, annotation,
derived-metric, and simulated-event requests delegate through
`DatasetRegistry` and the owning `DatasetAdapter`. Signal reads require a
configured maximum duration, include explicit units and timestamps, and clip
only at the recording boundary. There is no full-record or mutation endpoint.

The frontend implements `HttpSessionCatalogService` and `HttpReplaySource`
behind its existing service contracts. Fixture transport remains available.
Manual navigation owns one synchronized range shared by observed EEG, imported
stages, derived Alpha/state features, and simulated control output. uPlot may
downsample only the visual copy; the HTTP response remains unchanged.

**Rationale**:

- Keeping storage access in adapters prevents an SC4001-specific API or UI.
- Explicit `raw`/`imported`/`derived`/`simulated` provenance prevents simulated
  demand from being interpreted as an observed ultrasound effect.
- Bounded windows avoid returning the 22-hour PSG or storing it in React state.
- Standard-library WSGI supplies the required local transport without adding a
  network-installed web dependency to the research environment.

This phase adds no WebSocket, replay clock, live EEG, stimulation command,
ultrasound parameter, or hardware integration.

**Date**: 2026-08-07

---

## DD-015: Replay public EEG in real-time cadence without implying intervention response

**Decision**: Add a configuration-driven, client-side offline replay clock over
the existing bounded `ReplaySource` windows. The clock supports play/pause,
reset, speed selection, cursor synchronization, and bounded-window rollover. It
does not add a full-record endpoint, WebSocket, live EEG, or server-side clock.

An operator may place an in-memory `simulated_intervention_marker` at the
current replay cursor. Every marker has `simulated` provenance and the notice
`SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED`. The marker appears across
the observed EEG, imported hypnogram, derived Alpha/state, and simulated-demand
views but never changes any source or derived value. It is not persisted and
does not send a command.

**Rationale**:

- Real-time cadence lets the existing public record exercise synchronized UI
  behavior without presenting prerecorded data as a live acquisition.
- A single cross-panel cursor and marker make temporal comparison auditable.
- Browser-memory-only events preserve the read-only API and prevent a visual
  annotation from being mistaken for an actual Sleep-EDF intervention.
- The explicit negative hardware statement is required because no DreamCore
  ultrasound stimulus-response data exists.

This decision authorizes only offline replay and abstract simulated annotation.
It does not authorize ultrasound dose, FUS delivery wording, device control,
EEG modification, efficacy claims, or causal pre/post interpretation.

**Date**: 2026-08-07

---

## DD-016: Use one authoritative offline replay clock and window-end feature semantics

**Decision**: Phase A3 replaces the component-local replay cursor in DD-015
with an independent `idle | playing | paused | ended | error` state machine.
`sessionTimeSeconds` is the only authoritative time. EEG reveal, current
imported stage, derived Alpha/state visibility, simulated demand, and simulated
event visibility all consume that value; panels do not own timers.

An Alpha feature timestamp means the **analysis-window end**. The frontend does
not expose a feature until `window_end_s <= sessionTimeSeconds`. A simulated
event likewise remains hidden until its timestamp is reached. The imported
hypnogram remains an independent reference and is never regenerated from the
drowsiness heuristic.

Signal transport remains bounded and read-only. A small configured LRU cache
stores at most three window packages outside React state. The next window is
prefetched once near the current boundary; seek/window changes abort obsolete
requests, and a generation guard prevents stale responses from replacing the
new window. uPlot updates data without recreating its chart for every clock
tick.

**Rationale**:

- One clock prevents independent panel drift.
- Window-end semantics avoid revealing a derived value before all samples used
  to compute it have occurred in replay time.
- Bounded caching and cancellation support long replay without accumulating an
  all-night signal or issuing a request every animation frame.
- Progressive display is a visualization of a fixed public record, not live
  acquisition or evidence that a simulated event affected later EEG.

This demonstrator adds no WebSocket, hardware ring buffer, EEG acquisition,
ultrasound parameter, stimulation command, or counterfactual signal.

**Date**: 2026-08-07

---

## DD-017: Declare precomputed derived coverage separately from raw-session coverage

**Decision**: A real Session Package with precomputed Alpha rows records compact
`metadata.analysis` coverage: recording-relative seconds, window-end timestamp
semantics, evaluation range, configured window/step, exact channels,
attempted/accepted/rejected window counts and reasons, total row count, and
first/last feature times. The frontend may use this metadata to explain why a
bounded raw-EEG window has no derived rows, but it must not synthesize a row or
change the replay clock.

**Rationale**:

- Raw EEG may cover a much longer recording than a configured research analysis.
- An empty bounded response before or after derived coverage is not an extraction
  failure and should not be presented as an unexplained unavailable value.
- Compact coverage metadata preserves the bounded transport and makes timestamp
  units and channel mapping auditable.

**Date**: 2026-08-12

---

## DD-018: Make EOG/eye movement primary and sonification modular

**Decision**: Supersede DD-013's product priority without deleting its
implementation. The primary V1 path is now:

```text
Sleep-EDF EOG
→ EyeMovementFeatureTrack
→ Eye Movement Candidate events/activity
→ SonificationMapper
→ SonificationControlFrame
→ browser AudioRenderer
```

Discover EOG from recording metadata and configured label rules; fail
explicitly if discovery is absent or ambiguous. Compute features independently
of imported sleep stage. Use 4 s windows stepped every 1 s, window-end feature
timestamps, configured 0.3–10 Hz zero-phase Butterworth filtering, robust local
activity deviation, and deterministic mapping defaults for the first SC4001
experiment. All values and thresholds remain configuration-owned.

Extend `dreamcore.session.v1` additively with EOG, eye-movement activity/event,
and sonification-control capabilities. Raw EOG, filtered EOG, derived windows,
events, controls, stages, and Alpha share one `sessionTimeSeconds`. Persist
full coverage and source fingerprints. Keep CSVs as audit exports and use a
recording-relative SQLite time index for bounded API reads; this changes no
feature values or public API shape.

Adopt EEGsynth's conceptual separation of signal processing, controls, and
sound output, but do not require Redis, FieldTrip, MIDI hardware, or an external
synthesizer for V1. Web Audio begins only after a user gesture. Eye Movement is
the default source; Alpha is optional comparison; baseline is explicitly
configured. Musical parameters have `sonification_control` provenance and are
not measured physiology.

**Rationale**:

- SC4001 posterior and frontal Alpha differed enough that Alpha should remain a
  diagnostic rather than the default product signal.
- A real EOG path supports an interpretable, testable physiological driver
  without claiming that an event equals REM or a dream.
- Module boundaries allow a later MIDI/OSC/EEGsynth adapter without duplicating
  the current Session/replay architecture.
- Explicit coverage and indexed window reads prevent the previous mismatch
  between a long raw timeline and a small or slow derived artifact.

**Date**: 2026-08-12

---

## DD-019: Separate post-waking AI music from replay sonification

**Decision**: Make AI Wake Music the primary product-facing research experience
while retaining the oscillator path as `Physiological Sonification · Research`.
The backend selects the final annotation-confirmed non-Wake→Wake transition and
uses the configured preceding interval, or an explicit manual research window.
Only existing derived EOG feature rows enter `dreamcore.wake_music.profile.v1`.

DreamCore maps activity→register, candidate rate→density, trend→brightness and
energy curve, and amplitude→bounded expression. A six-family style bank and
seeded arrangement variants produce a reproducible prompt configuration. Auto
style is an exploratory seeded choice, not a claim that physiology determines
genre. Energy and percussiveness are capped; vocals and aggressive styles are
disabled.

MiniMax calls originate only in the Python backend, use a single configurable
base URL, request non-streaming URL output with `is_instrumental=true`, omit
lyrics, and immediately download the temporary URL. Each generation stores the
profile, exact prompt, safe metadata, and local MP3 under ignored results. The
cache key includes session/window/versions/style/seed/provider/model/prompt hash.
The read-only `/api/v1` Session contract is unchanged; mutations are isolated
under `/api/wake-music`.

**Rationale**:

- A categorical profile preserves an explainable DreamCore-owned mapping and
  prevents a provider from interpreting raw physiology.
- Seeded bounded variation supports comparisons and auditability without
  promising deterministic provider audio.
- Immediate local download avoids dependence on expiring provider URLs.
- Separate APIs preserve canonical Session semantics and keep credentials out
  of the browser.

**Date**: 2026-08-13

---

## DD-020: Preserve generated masters and derive product playback locally

**Decision**: Keep each provider-generated `wake_music.mp3` byte-preserved as
the full master. Create `wake_music_60s.mp3` locally using configured FFmpeg
postprocessing: take the first configured 60 seconds, apply no fade-in, and
apply a gentle configured three-second fade-out beginning at 57 seconds. Store
separate `master_audio` and `wake_version` metadata. Default the Viewer and
`/audio` route to the Wake Version while retaining the master under
`/audio/master`.

Missing derivatives are created or reused during local storage lookup or by an
explicit helper command. This operation does not invoke MiniMax and does not
alter physiology, mapping, prompt, style, variation, seed, or generation-cache
identity.

**Rationale**:

- A bounded product playback duration is easier to review and use as a wake cue.
- Keeping the provider master byte-identical preserves reproducibility and
  permits full-track research inspection.
- A local derivative avoids consuming generation quota and keeps playback
  policy separate from physiological and musical-generation parameters.

**Date**: 2026-08-13

---

## DD-021: Index source files; do not construct a duplicate signal database

**Decision**: Extend `dreamcore.session.v1`, `DatasetRegistry`, and the existing
bounded Session API for Sleep-EDF Expanded, HMC v1.1, and ISRUC Cohort III.
Adapters inspect native EDF/REC metadata and keep source signals in place.
Lightweight manifests/catalog entries store dataset, subject, recording,
channel, annotation, capability, and provenance metadata only.

Preserve `original_channel_name`, per-channel sampling frequency and unit beside
a conservative `canonical_role`. Normalize stages to W/N1/N2/N3/REM/UNKNOWN/
MOVEMENT while retaining every raw stage label. ISRUC scorer 1 is the configured
primary Viewer source; scorer 2 remains a separately queryable annotation.
Source availability and derived availability are distinct states.

**Rationale**: This prevents multi-gigabyte duplication, avoids global montage
and sampling-rate assumptions, preserves disagreements, and lets the unified
Viewer load only requested time windows.

**Date**: 2026-08-13

---

## DD-022: Freeze Eye Movement V1 before cross-dataset descriptive validation

**Decision**: Hash a machine-readable contract before applying the unchanged
Eye Movement V1 detector to SC4002, HMC SN001/SN002, and ISRUC Cohort III
subjects 1/2. Analyze every native EOG channel independently over the full
recording. Use deterministic one-to-one temporal matching for dual EOG,
exposure-normalized stage summaries, and separate ISRUC scorer assignments.

Add a seeded candidate sample and a stage-stratified non-candidate control
sample to the unified Viewer. Human labels persist locally as a separate
versioned annotation layer; they never overwrite a detector candidate. Until
humans complete review, precision and sampled miss metrics remain unavailable.

**Rationale**: Freezing parameters prevents post-result tuning, dual-channel
matching exposes montage-dependent behavior without declaring a correct
channel, and stage/scorer denominators avoid misleading raw-count comparisons.
The control sample can reveal possible misses descriptively but cannot provide
formal recall without exhaustive ground truth.

**Date**: 2026-08-14

---

## DD-023: Product-first automatic local analysis with identity-based reuse

**Decision**: Opening a recording starts non-blocking local Alpha and Eye
Movement jobs when compatible source channels exist, followed by a local Wake
Music Profile when its inputs become ready. Jobs are keyed by recording source
fingerprint, algorithm version, and configuration hash, deduplicated in-process,
and persisted under ignored results. Full-night Cross-Dataset EOG Validation
artifacts are referenced when their frozen detector contract, channels,
sampling rates, and coverage are equivalent; large results are not copied.

The primary Viewer exposes only Not available, Analyzing, Ready, and Error.
Detailed hashes and provenance remain internal. MiniMax generation remains an
explicit user action, and K-Complex remains an unimplemented future feature.

**Rationale**: Product users should receive useful insights without managing
artifact lifecycles. Stable cache identity preserves scientific auditability,
while per-feature background jobs keep initial rendering responsive and prevent
duplicate analysis.

**Date**: 2026-08-14

---

## DD-024: Add retrospective K-Complex V0 to automatic local analysis

**Decision**: Supersede DD-023's K-Complex placeholder with a transparent,
configuration-hashed `k_complex_v0` detector. Select one primary EEG channel
independently from Alpha using frontal→central→other compatible EEG role
priority, gate normal counts to normalized N2, merge continuous N2 bouts, and
assign within-bout ordinals. Detect complete-waveform negative-positive
morphology after zero-phase 0.3–4 Hz filtering using local median/MAD depth and
prominence, configurable duration bounds, artifact limits, and refractory
suppression. A positive peak stays absent unless it passes its configured
threshold.

Run K-Complex through the existing automatic-analysis executor and persistent
identity cache. Expose event focus through the existing bounded multi-signal
reader. Persist Looks right/Wrong/Uncertain reviews and manual N2 trough
candidates in a separate local SQLite overlay; neither changes detector output.

**Rationale**: Retrospective morphology and lightweight human review establish
an inspectable cross-dataset baseline before any causal early-trough work. The
separate channel policy avoids inheriting Alpha's posterior preference, robust
local thresholds accommodate heterogeneous native montages/scales, and explicit
N2 bout ordinals make the first and second candidates directly reviewable.

This V0 may inspect samples after the trough. It is not an early predictor,
clinical detector, or ground truth and exposes no causal lead time.

**Date**: 2026-08-14

---

## DD-025: Productize frozen B1 morphology and keep CBraMod research-only

**Decision**: Keep K-Complex V0 as the retrospective candidate detector and use
the already-benchmarked B1 Morphology verifier as the default product filter.
B1 retains exactly four ordered V0 features (`score`, `duration_s`, signed
`negative_trough_amplitude`, and zero-or-observed `positive_peak_delay_s`), a
standard scaler, class-balanced L2 logistic regression with the frozen
hyperparameters and seed, and an inclusive 0.5 probability threshold. The
verifier changes acceptance only and never changes V0 onset, trough, positive
peak, end, duration, score, or morphology measurements.

Preserve the recording-grouped DREAMS OOF benchmark as evaluation evidence.
Fit the product artifact separately on all 108 label-eligible frozen examples;
do not assign the OOF metrics to that final fit. Store coefficients, scaler,
threshold, label policy, provenance, benchmark contract hash, and a canonical
checksum in a small JSON artifact. Include its checksum in product cache
identity.

Keep frozen CBraMod available for explicitly enabled research comparison, off
by default. Normal K-complex inference must not load its checkpoint or require
PyTorch, CUDA, embeddings, or cache files. Expose verified/rejected-by-verifier
semantics while retaining rejected V0 proposals for inspection; neither status
is ground truth.

**Rationale**: B1 was the strongest arm of the frozen comparison and is small,
auditable, deterministic, and operational without a foundation-model runtime.
Separating OOF evaluation from the final all-eligible-data fit prevents an
unsupported performance claim for the product artifact.

**Date**: 2026-08-18
