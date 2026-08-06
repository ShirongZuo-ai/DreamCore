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
