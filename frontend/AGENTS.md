# AGENTS.md — DreamCore Research Console

These rules apply to all work under `frontend/`.

1. Before modifying the frontend, read the root `AGENTS.md` plus
   `docs/project_scope.md`, `docs/unknowns.md`, `docs/decisions.md`, and
   `docs/research_protocol.md`.
2. All values currently rendered by this app are deterministic Demo data. Never
   represent them as measurements from a person or device.
3. Do not implement real stimulation control, device commands, diagnosis, or
   efficacy claims. Do not expose experimental blinding such as Active/Sham.
4. Run `npm run format:check`, `npm run lint`, `npm run typecheck`,
   `npm run test:run`, and `npm run build` after changes. Run E2E checks for
   layout or workflow changes.
5. Keep components single-purpose. Keep EEG drawing independent from React
   state updates.
6. A future real-time EEG implementation must write samples to a ring buffer;
   it must not trigger a React render for every sample.
7. Keep API types hardware-neutral. Sampling rate, channel order, thresholds,
   and durations must arrive through config or data contracts, never through
   product assumptions.
8. Update the relevant frontend documentation whenever contracts, architecture,
   or design tokens change.
9. Never commit or push automatically.
