# DreamCore Research Console

A standalone React + TypeScript frontend that coexists with the DreamCore Python
research repository. This phase is a deterministic visual prototype only: it
does not connect to EEG equipment, stimulation hardware, or a Python service.

## Start locally

```bash
npm install
npm run dev
```

Vite serves the app at `http://127.0.0.1:4173`.

## Routes

- `/live` — researcher live-console mockup
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

See `docs/frontend_architecture.md`, `docs/frontend_data_contract.md`, and
`docs/frontend_design_system.md` for implementation boundaries.
