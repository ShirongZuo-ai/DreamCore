# Frontend Architecture

## Purpose and boundary

`frontend/` is an independent Vite application that coexists with the Python
research package. It now supports a local read-only HTTP view of canonical
public-data sessions. It neither imports Python modules nor changes algorithm
outputs, and it has no EEG device, stimulation device, or medical decision.

The application has three audiences plus a dataset-neutral research library:

| Route | Audience | Purpose |
|---|---|---|
| `/live` | Experiment operator | Inspect Demo/fixture content or a manually selected real offline window |
| `/review` | Research analyst | Review a simulated, descriptive session summary |
| `/subject` | Participant | See only fitting, recording, comfort, and assistance status |
| `/datasets` | Research operator | Search, filter, select, and load fixture or real public sessions |
| `/datasets/:datasetId/sessions/:sessionId` | Research operator | Inspect a shareable canonical session description |

The root redirects to `/live`; unknown routes render a small Not Found view.

## Layers

```text
pages
  ↓ compose
components (layout / dashboard / eeg / safety / common)
  ↓ consume
hooks + services + mocks
  ↓ share
types + design tokens
```

- `src/app/` owns route composition.
- `src/pages/` owns page-level information hierarchy and local-only interaction.
- `src/components/` contains single-purpose presentational boundaries.
- `src/types/` contains transport-friendly domain types.
- `src/mocks/` is the single source for deterministic Demo values.
- `src/services/` defines interfaces plus fixture and read-only HTTP adapters.
- `src/styles/` defines tokens and shared low-level styles.
- `tests/` contains Vitest/Testing Library behavior tests.
- `e2e/` contains browser layout, accessibility-visible behavior, and screenshot checks.

## Dataset and session boundary

Phase 2A adds the following application boundary:

```text
shared dreamcore.session.v1 fixture
  → SessionCatalogService / ReplaySource
  → SessionWorkspaceProvider
  → Dataset Library and capability-aware Live Console
```

`SessionWorkspaceProvider` owns source selection, selected session, and the
`idle | loading | ready | error` load state. It persists during in-app route
navigation but not across a browser refresh. Pages consume only canonical
`DatasetSummary`, `SessionSummary`, `SessionManifest`, `CapabilitySet`, and
`LoadedSession` types. They do not parse dataset-specific metadata.

The fixture transport still imports deterministic JSON validated by Python.
Phase A2 adds `HttpSessionCatalogService` and `HttpReplaySource`; Workspace
chooses the transport from catalog metadata and binds the loaded source. Pages
never fetch directly. Adding a dataset still requires an adapter or normalized
package, not conditionals in the Live Console.

## Signal and sonification rendering boundary

For Demo Simulation, the waveform remains deterministic SVG. Real offline
sessions request only the configured window through `ReplaySource` and render
two signals on a shared uPlot axis. React owns only current bounded arrays. The
configured point limit can downsample the plotted copy, while units, sample
count, timestamps, and transported values remain intact.

The real workspace uses one bounded range for EEG, raw/filtered EOG, imported
stages, eye-movement features/events, sonification controls, Alpha diagnostics,
and simulated demand/events. `src/replay/` owns an independent five-state
clock; `sessionTimeSeconds` is the only authoritative time and panels own no
timers. Manual navigation remains available. Crossing a range consumes a
prefetched window or requests the next bounded window through `ReplaySource`;
it does not create a streaming or full-record transport.

The sonification boundary mirrors EEGsynth's modular concept without importing
its runtime dependencies:

```text
ReplaySource → EyeMovementFeatureTrack → control frames
                                           ↓ same cursor
                                   useSonificationAudio
                                           ↓ user gesture
                                      Web Audio API
```

The audio hook owns only browser audio nodes and last-trigger bookkeeping. It
does not own time, recompute physiology, or mutate transported arrays. Tempo
sets beat cadence, density deterministically gates beats, intensity/velocity
sets the envelope, brightness sets the low-pass cutoff, and candidate events
can trigger notes. Source selection changes only the musical-control track.

The window coordinator keeps a configured, bounded LRU outside React state,
prefetches only once near the next boundary, passes AbortSignal to HTTP reads,
and ignores responses from obsolete generations after seek. React holds only
the active bounded window. EEG samples after the current cursor are visually
masked, features become visible at their analysis-window end, and simulated
events appear only when replay reaches their timestamps.

The replay cursor is positioned from uPlot's own x-scale plus its measured plot
bounding box, so it shares the exact coordinate system used by the waveform.
Derived Alpha/state and simulated-demand charts use a labelled stepwise
last-value hold between source feature timestamps. This makes replay progress
visible without interpolating, recomputing, or fabricating derived physiology.

An operator can add an in-memory simulated-intervention marker at the current
cursor. The marker is synchronized across EEG, hypnogram, Alpha/state, and
demand charts and displays `SIMULATED INTERVENTION — NO ULTRASOUND DELIVERED`.
It is not persisted, does not call an API, does not send a hardware command, and
does not modify observed EEG or derived features.

A future streaming implementation should follow this flow:

```text
WebSocket packet → decoder/validator → typed ring buffer
                                      ↓ bounded refresh cadence
                              uPlot display adapter
                                      ↓ sparse state only
                                   React UI
```

Samples must not be copied into React state one at a time. Connection status,
selected display window, alerts, and summary values can use React state;
high-rate arrays belong in an external ring buffer. uPlot now renders bounded
real-session EEG and Alpha/state windows. ECharts remains available for future
sleep architecture and post-session statistics.

## State and safety

No general state library is used. Offline replay state is isolated in a
reducer/hook and owns session time, state, and speed. Other page-local state is
limited to:

- the local Emergency Stop demonstration;
- the local Request Assistance acknowledgement.

Both interactions explicitly say that no external command or message was sent.
Any future command-capable service is out of scope until hardware, safety, and
authorization specifications are approved.

## Responsive and accessibility approach

The layout targets 1440×900, 1280×800, and 390×844. Content uses bounded
containers and `min-width: 0` in grid columns; the operator sidebar moves below
EEG on narrower screens, and primary navigation becomes a bottom bar on mobile.
Page-level horizontal scrolling is prohibited. Focus-visible outlines, semantic
sections, accessible control names, and `prefers-reduced-motion` are included.

## Verification

Use the scripts in `frontend/package.json`. Browser screenshots are generated
under `frontend/artifacts/screenshots/`, outside the Python `results/` tree.
