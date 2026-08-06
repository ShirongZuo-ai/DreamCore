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
