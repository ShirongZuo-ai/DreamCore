# DreamCore Research Console

A standalone React + TypeScript frontend that coexists with the DreamCore Python
research repository. Phase 2A adds a deterministic, dataset-neutral catalog and
session-loading framework using shared TEST FIXTURES only. It does not connect
to EEG equipment, stimulation hardware, a real dataset, or a Python service.

## Start locally

```bash
npm install
npm run dev
```

Vite serves the app at `http://127.0.0.1:4173`.

## Routes

- `/live` — researcher live-console mockup
- `/datasets` — canonical TEST FIXTURE dataset and session library
- `/datasets/:datasetId/sessions/:sessionId` — shareable session details
- `/review` — post-session review mockup
- `/subject` — blinded, simplified participant view

## Quality commands

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test:run
npm run build
npm run test:e2e
```

See `../docs/frontend_architecture.md`, `../docs/frontend_data_contract.md`,
`../docs/frontend_design_system.md`, and `../docs/dataset_session_framework.md` for
implementation boundaries.
