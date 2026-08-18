# DreamCore V1 Current Best Methods

**Authoritative as of 2026-08-18.** This record distinguishes benchmark model
evaluation from the final product fit. It does not authorize an Early Predictor.

## Current methods

- **Alpha — current best:** classical spectral / PSD.
- **Eye Movement — current product use:** activity, density, and trend. The
  event-level detector remains exploratory.
- **K-Complex candidate:** K-Complex V0, a retrospective complete-waveform
  candidate detector.
- **K-Complex default verifier:** B1 Morphology,
  `k-complex-morphology-b1-v1`.
- **CBraMod:** successfully integrated and benchmarked as a frozen research
  comparison. It is not the production default, is off by default, and the
  current evidence does not justify fine-tuning.
- **Wake Music:** the configurable 60-second product pipeline, with the
  provider master retained separately.

## Frozen K-complex benchmark evaluation

The recording-grouped, leave-one-DREAMS-excerpt-out benchmark used only
high-confidence positives and high-confidence negatives. Ambiguous and
single-expert examples were excluded from fitting; missing Expert 2 was never
interpreted as a negative vote. At the unchanged probability threshold of 0.5,
B1 Morphology achieved grouped OOF precision 0.575, recall 0.821, F1 0.676,
AUROC 0.904, and AUPRC 0.832 on the frozen DREAMS benchmark.

| Benchmark arm | Precision | Recall | F1 | AUROC | AUPRC |
|---|---:|---:|---:|---:|---:|
| B0 K-Complex V0 | 0.259 | 1.000 | 0.412 | 0.500 | 0.259 |
| B1 Morphology | 0.575 | 0.821 | 0.676 | 0.904 | 0.832 |
| B2 Frozen CBraMod | 0.531 | 0.607 | 0.567 | 0.760 | 0.478 |
| B3 Fusion | 0.513 | 0.714 | 0.597 | 0.806 | 0.516 |

These are grouped OOF benchmark metrics, not performance claims for the final
all-data-fitted artifact.

## Final B1 product fit

After preserving the grouped OOF benchmark, a final verifier using the same
frozen B1 feature order, standardization, class-balanced logistic-regression
family and hyperparameters, label eligibility, random seed, and 0.5 threshold
was fit on all 108 eligible frozen DREAMS examples (28 positive, 80 negative).
The auditable artifact is `configs/models/k_complex_morphology_b1.json` and
references benchmark contract SHA-256
`d2d16ea5a98d865e31c6d7bdda1ed26733c890174dc340aebdb8d95761e8d152`.

The final product artifact has not itself been evaluated on an independent test
set. HMC SN001 is an untuned inference sanity check only, not K-complex ground
truth.
