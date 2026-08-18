"""Create and run the frozen Signal Validation V1 contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dreamcore.config import load_config
from dreamcore.validation.runner import run_all, write_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config_path = (project_root / args.config).resolve()
    if args.contract_only:
        path, digest = write_contract(project_root, load_config(config_path))
        print(json.dumps({"contract": str(path), "sha256": digest}, indent=2))
        return
    print(json.dumps(run_all(project_root, config_path), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
