# DreamCore Research Console

A standalone React + TypeScript frontend that coexists with the DreamCore Python
research repository. It retains shared TEST FIXTURES and can load real public
SC4001 Session Packages through the local read-only `/api/v1` service. It does
not connect to EEG equipment or stimulation hardware.

## Start locally

Start the API from the repository root, then Vite:

```bash
python scripts/serve_session_api.py --config configs/default.yaml
cd frontend
npm install
npm run dev
```

Vite serves the app at `http://127.0.0.1:4173`.

## Routes

- `/live` — researcher live-console mockup
- `/datasets` — canonical fixture and real public dataset/session library
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
