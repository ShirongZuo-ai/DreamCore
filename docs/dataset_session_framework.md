# Dataset and Session Framework

## Purpose

Phase 2A defines the dataset-neutral boundary used by DreamCore:

```text
Raw Dataset
    → Dataset Adapter
    → DreamCore Session Package
    → Dataset Registry / Session Catalog
    → ReplaySource
    → Frontend
```

The frontend consumes DreamCore session types only. It must not interpret EDF,
Sleep-EDF, MASS, SHHS, a hardware vendor format, or any other source layout.
Adding a second dataset must not require changes to the core UI. Integration
belongs in a new adapter or in a conversion step that emits standard packages.

Phase 2A contains deterministic, synthetic TEST FIXTURES only. It does not add
real subject records, an EDF reader, a Python HTTP API, streaming, playback, or
device control.

## Schema ownership and versioning

DreamCore owns the canonical package schema. The current exact identifier is
`dreamcore.session.v1`. A manifest describes metadata and references; it never
contains complete signal arrays. An unknown schema version fails validation
rather than being guessed or silently upgraded.

The shared contract fixtures live in `tests/fixtures/session_packages/`. Python
parses these files through the filesystem repository and the frontend imports
the same JSON files for contract tests, avoiding independently maintained
copies. Future normalized packages may live under `data/session_packages/`,
with one `manifest.json` per session.

The v1 top-level objects are:

- `schema_version`
- `fixture_notice` for fixture packages
- `dataset`: stable id, display name, and optional source version
- `session`: session, subject, optional visit, and optional night identifiers
- `recording`: optional start time/timezone and required duration in seconds
- `signals`: window-readable signal metadata and availability
- `annotations`: descriptors for stages, arousals, artifacts, and markers
- `derived`: descriptors for detections, estimates, predictions, and decisions
- `capabilities`: one descriptor for every canonical capability
- `provenance`: package and field lineage (`raw`, `imported`, `derived`,
  `simulated`, or `unknown`)
- optional metadata such as `has_n3`, kept generic and explicitly sourced

Optional source fields may be absent. Required identity, duration, provenance,
and capability fields are validated. A missing capability is never inferred
from a convenient UI default.

## Capability semantics

Each canonical capability is a typed descriptor, not a loose boolean:

| Status | Meaning | UI treatment |
|---|---|---|
| `AVAILABLE` | Content exists for this session | Show sourced content or a source-aware placeholder |
| `UNAVAILABLE` | Source is known not to contain it | Show `Unavailable` and the reason |
| `PLANNED` | A declared future computation/integration | Show `Planned`; no substitute value |
| `UNKNOWN` | Presence or specification is not known | Show `Unknown`; do not assume healthy or absent |

Descriptors can include `source`, `reason`, `derived_by`, and `version`. The
canonical capability names cover EEG, stage labels/predictions, slow
oscillations, phase/precision, decisions, physiology, events, telemetry, and
navigation. Their definitions are shared by Python and TypeScript.

Missing-data language preserves meaning:

- `Unavailable — Not present in source dataset`
- `Not computed — No estimator output for this session`
- `Planned — Declared future work`
- `Unknown — Source or hardware specification is unresolved`

The UI must never manufacture a value to fill a missing panel. In particular,
offline packages without hardware telemetry are presented as offline records,
not as healthy connected hardware.

## DatasetAdapter

`dreamcore.datasets.DatasetAdapter` is a domain-only abstract base with:

- `dataset_metadata()`
- `list_sessions()`
- `get_session_metadata(session_id)`
- `get_capabilities(session_id)`
- `load_signal_window(session_id, signal_id, start_seconds, duration_seconds)`
- `load_annotations(session_id, annotation_type)`
- `load_derived_results(session_id, result_type)`

Adapters know their source format but know nothing about React. The Phase 2A
`FixtureDatasetAdapter` validates the contract and returns deterministic tiny
windows/events for tests. It reads no large files.

## Repository, registry, and filters

`SessionPackageRepository` discovers `manifest.json` files and validates them
without loading signal samples. `DatasetRegistry` registers multiple adapters,
lists datasets/sessions, resolves session metadata and capabilities, searches
catalog metadata, and applies `SessionFilter`.

Filters remain dataset-neutral: dataset, required/optional capabilities,
minimum duration, stage-label presence, N3 presence, and optional subject id.
Optional capabilities inform candidate ranking/description but are not required
for validity.

Random-selection semantics are explicit:

- **Random Session** chooses from the current candidate collection.
- **Random Valid Session** first applies the current filter, then chooses.
- A caller supplies the seed; selection uses an isolated deterministic random
  generator and does not mutate process-global random state.
- Equal registry state, candidate order, and seed produce the same selection.
- An empty candidate set raises/returns a specific reason; it never falls back
  to an invalid session and never starts replay automatically.

## ReplaySource and transport boundaries

`ReplaySource` exposes session metadata, duration, signal metadata, windowed
signal reads, annotations, and derived events. Catalog summaries never include
full sample arrays. `FixtureReplaySource` proves the boundary without a clock,
timer, WebSocket, or dynamic EEG rendering.

Transport evolution is intentionally staged:

1. **Phase 2A:** the frontend reads the shared deterministic fixture contract;
   Python provides the canonical domain, repository, registry, and fixture
   adapter. There is no claim of a connected Python API.
2. **Phase 2B:** add a real dataset adapter or normalizer and a small
   Python-backed catalog/window transport while retaining the same domain
   shapes.
3. **Future offline replay:** add a replay clock and window scheduling behind
   `ReplaySource`.
4. **Future live transport:** map versioned HTTP metadata and WebSocket packets
   into the same frontend types. Device-specific transports stay behind their
   adapters and require separate hardware and safety specifications.

At the anticipated scale of thousands of sessions, server-side pagination and
search can replace the in-memory fixture catalog without changing page
components. Signal access remains windowed in every transport.

## Provenance and research safeguards

Fixture A exercises EEG, labels, slow-oscillation, and phase availability;
Fixture B exercises EEG/labels with phase missing; Fixture C exercises missing
EEG and partially available physiology. They exist only to test capability-aware
behavior and are labeled `TEST FIXTURE — NOT REAL SUBJECT DATA` throughout.

Capabilities report data presence, not quality, diagnosis, benefit, or fitness
for stimulation. No package field exposes Active/Sham assignments, and no
Phase 2A component controls stimulation or medical hardware.
