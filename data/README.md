# Data directory

Large datasets are gitignored. Only small metadata files belong here.

## Adding a dataset

1. Download raw data outside the repo (e.g., `~/datasets/sleep-edf/`)
2. Add a metadata file here with subject IDs, splits, and channel info
3. Reference the external path in your experiment config

## Expected structure (external)

```
~/datasets/
├── sleep-edf/
│   ├── sleep-cassette/
│   │   ├── SC4001E0-PSG.edf
│   │   ├── SC4001EC-Hypnogram.edf
│   │   └── ...
│   └── sleep-telemetry/
│       ├── ST7001J0-PSG.edf
│       ├── ST7001JA-Hypnogram.edf
│       └── ...
```

## Minimal Sleep-EDF SC validation pair

Milestone 1 uses subject 0, recording 1 from the Sleep-EDF Expanded
sleep-cassette cohort as a minimal real-data check:

- `SC4001E0-PSG.edf`
- `SC4001EC-Hypnogram.edf`

MNE's supported PhysioNet fetcher downloads exactly this pair and verifies the
published file hashes:

```python
from mne.datasets.sleep_physionet import age

age.fetch_data(
    subjects=[0],
    recording=[1],
    path="data/datasets/sleep-edf",
    base_url="https://physionet.org/files/sleep-edfx/1.0.0/sleep-cassette/",
)
```

`data/datasets/` is ignored by Git and is suitable for this local validation
pair. For longer-lived or multi-subject datasets, pass an external dataset
directory instead.

Run the inspection with all file paths supplied explicitly and the sampling
rate validation supplied by the dataset config:

```bash
python scripts/inspect_sleep_edf.py \
  --config experiments/sleep_edf_sc.yaml \
  --psg data/datasets/sleep-edf/physionet-sleep-data/SC4001E0-PSG.edf \
  --hypnogram data/datasets/sleep-edf/physionet-sleep-data/SC4001EC-Hypnogram.edf
```

The generated `results/sleep_edf_summary.json` is ignored by Git. Unit tests
use mocks and synthetic `RawArray` objects; they never download this dataset.

## N3 metadata extraction

The same dataset config contains the raw-label mapping, merge tolerance,
minimum N3 duration, and explicit EEG channel selection. Run:

```bash
python scripts/extract_n3_segments.py \
  --config experiments/sleep_edf_sc.yaml \
  --psg data/datasets/sleep-edf/physionet-sleep-data/SC4001E0-PSG.edf \
  --hypnogram data/datasets/sleep-edf/physionet-sleep-data/SC4001EC-Hypnogram.edf
```

This writes ignored metadata files only:

- `results/n3_segments.csv`
- `results/n3_segments.json`

No signal array is saved by default. If a later local analysis saves cropped
signals, keep them under an ignored data or results directory and retain the
source filename plus half-open time range in accompanying metadata.

## N3 EEG preprocessing and visual review

`configs/default.yaml` defines three research-only preprocessing profiles:

- `raw_eeg` leaves signal values unchanged for comparison.
- `broadband_sleep_eeg` applies the configured general sleep EEG band.
- `slow_oscillation_observation` provides a narrow visual view for the next
  research step.

The Sleep-EDF dataset config selects two explicit bipolar EEG channels, keeps
the native sample rate, and fixes a representative 600 s N3 segment plus two
display windows. Run:

```bash
python scripts/visualize_n3_eeg.py \
  --config experiments/sleep_edf_sc.yaml \
  --psg data/datasets/sleep-edf/physionet-sleep-data/SC4001E0-PSG.edf \
  --hypnogram data/datasets/sleep-edf/physionet-sleep-data/SC4001EC-Hypnogram.edf
```

The command writes these ignored artifacts:

- `results/n3_eeg_long.png`
- `results/n3_eeg_short.png`
- `results/n3_eeg_preprocessing_summary.json`

The JSON records source files, subject/recording identifiers, segment and window
ranges, selected channels, original/output sampling rates, every preprocessing
parameter, raw/processed statistics, and figure paths. No EDF or derived signal
array is written.
