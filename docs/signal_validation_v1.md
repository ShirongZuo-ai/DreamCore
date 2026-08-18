# Signal Validation V1

Signal Validation is an explicit, internal benchmark. It never runs when the
Viewer opens and its outputs do not alter the production Alpha, Eye Movement,
or K-Complex caches. The normal Sleep Insights surface remains product-focused.

## Reproduce the benchmark

The official DREAMS archives must already exist at the paths recorded in
`data/dreams_signal_validation_v1.json`. Create and inspect the immutable
machine-readable contract before running the benchmark:

```bash
.venv/bin/python3 scripts/run_signal_validation_v1.py --contract-only
.venv/bin/python3 scripts/run_signal_validation_v1.py
```

The runner refuses to proceed if the stored contract differs from the current
validation implementation, production configuration, or benchmark source
metadata. Results are written to the ignored
`results/signal_validation_v1/` directory; no waveform arrays are exported.

## Metric semantics

- Alpha is evaluated with deterministic synthetic frequency, peak rejection,
  power recovery, and stability cases. These results validate implementation
  behavior, not biological accuracy.
- Eye Movement matching measures agreement of generic DreamCore candidates
  with DREAMS expert rapid-eye-movement intervals. Candidate agreement is not
  generic eye-movement precision.
- K-Complex results preserve Expert 1 and Expert 2 independently. DREAMS labels
  are onset/duration intervals and contain no expert trough landmark. The
  reported operational trough is the raw central-channel minimum within an
  expert interval, not expert trough ground truth.
- Missing human labels and unsupported measurements render as Pending or NA;
  they are never converted to zero.

## Dashboard

Start the existing local API and frontend, then open `/validation` or choose
**Signal Validation** in the top navigation. The dashboard only reads the
generated summary and does not launch a benchmark job. Source provenance,
algorithm/config identity, matching rules, and full metric definitions remain
available in `results/signal_validation_v1/validation_contract.json`.

## Source and redistribution

The DREAMS K-complex and REM databases come from Zenodo record 2650142
(`10.5281/zenodo.2650142`) under CC BY-NC-ND 3.0. Raw archives and extracted
physiology stay under ignored `data/datasets/raw/dreams/` paths and must not be
redistributed through the repository.
