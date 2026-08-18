# DreamCore Research Console

A standalone React + TypeScript frontend that coexists with the DreamCore Python
research repository. It retains shared TEST FIXTURES and can load real public
SC4001 Session Packages through the local read-only `/api/v1` service. It does
not connect to EEG equipment or stimulation hardware.

The real-public-data workspace includes a primary AI Wake Music panel backed by
the Python-only MiniMax integration. It selects an annotation-confirmed Wake
window or a manual research window, shows the exact exploratory mapping, and
plays a locally derived 60-second Wake Version by default, with an explicit Full
Track option for the unchanged generated master. The browser never receives the
API key or a temporary provider URL.

The workspace also includes a five-state, configuration-driven
offline replay clock, bounded window cache/prefetch, synchronized EEG/EOG,
sleep-stage, eye-movement, Research Sonification, and Alpha diagnostic tracks.
Research Sonification Web Audio is enabled only by the user and is driven by the same replay cursor.
Every simulated intervention marker states `SIMULATED INTERVENTION — NO
ULTRASOUND DELIVERED`; no recorded signal is changed and no command is sent.

K-complex product counts use the frozen B1 Morphology verifier after the
retrospective K-Complex V0 candidate detector. The compact surface reports
verified candidates; rejected-by-verifier V0 proposals remain inspectable.
CBraMod is an off-by-default advanced research comparison, not a browser or
default-inference dependency.

## Start locally

Start the API from the repository root, then Vite:

```bash
.venv/bin/python3 scripts/serve_session_api.py --config configs/default.yaml
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
