# Frontend Architecture

## Purpose and boundary

`frontend/` is an independent Vite application that coexists with the Python
research package. It is currently a static monitoring prototype. It neither
imports Python modules nor changes algorithm outputs, and it has no EEG device,
stimulation device, medical decision, or network integration.

The application has three audiences and routes:

| Route | Audience | Purpose |
|---|---|---|
| `/live` | Experiment operator | Observe a deterministic mock session and inspect safety state |
| `/review` | Research analyst | Review a simulated, descriptive session summary |
| `/subject` | Participant | See only fitting, recording, comfort, and assistance status |

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
- `src/services/` defines interfaces and network-free Demo adapters.
- `src/styles/` defines tokens and shared low-level styles.
- `tests/` contains Vitest/Testing Library behavior tests.
- `e2e/` contains browser layout, accessibility-visible behavior, and screenshot checks.

## EEG rendering boundary

The current waveform is a deterministic SVG renderer. `EEGWaveformPanel`
accepts one `EEGSampleWindow`; it does not synthesize data, open a connection,
or own acquisition state. This makes it replaceable with a uPlot renderer.

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
high-rate arrays belong in an external ring buffer. uPlot is installed for this
future display adapter, while ECharts is installed for sleep architecture and
post-session statistics. Neither library is wired to dynamic data in this phase.

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
