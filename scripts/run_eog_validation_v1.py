"""Freeze or run DreamCore Cross-Dataset EOG Validation V1."""

from __future__ import annotations

import argparse
from pathlib import Path

from dreamcore.eog_validation.pipeline import (
    build_validation_contract,
    run_full_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/eog_validation_v1.yaml"))
    parser.add_argument("--contract-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.contract_only:
        _, digest, path = build_validation_contract(args.config)
        print(f"contract={path.resolve()}")
        print(f"sha256={digest}")
        return
    summary = run_full_validation(args.config)
    print(f"contract_sha256={summary['contract_sha256']}")
    print(f"recordings={summary['recording_count']}")
    print(f"channels={summary['channel_count']}")
    print(f"candidates={summary['candidate_count']}")
    print(f"manual_review_status={summary['manual_review_status']}")


if __name__ == "__main__":
    main()
