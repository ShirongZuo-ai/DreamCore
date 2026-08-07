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

## EEG rendering boundary

For Demo Simulation, the waveform remains deterministic SVG. Real offline
sessions request only the configured window through `ReplaySource` and render
two signals on a shared uPlot axis. React owns only current bounded arrays. The
configured point limit can downsample the plotted copy, while units, sample
count, timestamps, and transported values remain intact.

The real Alpha workspace uses one manual range for EEG, imported stages,
derived Alpha/state records, and simulated demand/events. It has
previous/next/duration/jump controls but no timer or play/pause behavior.

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

No general state library is used. Current state is page-local and limited to:

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
