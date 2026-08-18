"""Inspect local source files and build lightweight canonical session metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from dreamcore.datasets.indexing import INDEXERS, catalog_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/dataset_library_v1.yaml"))
    parser.add_argument("--dataset", choices=("all", *INDEXERS), default="all")
    return parser.parse_args()


def load_download_audit(raw_root: Path) -> dict[str, dict]:
    path = raw_root / "download_audit.json"
    if not path.is_file():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(row["local_file"]): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("local_file"), str)
    }


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent
    raw_root = project_root / config["raw_root"]
    package_root = project_root / config["session_package_root"]
    role_rules = tuple(config["signal_role_rules"])
    audit = load_download_audit(raw_root)
    selected = tuple(INDEXERS) if args.dataset == "all" else (args.dataset,)
    records = []
    for key in selected:
        indexer = INDEXERS[key](
            config["datasets"][key],
            project_root=project_root,
            raw_root=raw_root,
            package_root=package_root,
            role_rules=role_rules,
            viewer_config=config["viewer"],
            download_audit=audit,
        )
        indexed = indexer.index()
        records.extend(indexed)
        print(f"{key}: indexed {len(indexed)} recording(s)")
    catalog_path = project_root / config["catalog_output"]
    catalog_path.write_text(
        json.dumps(
            catalog_payload(tuple(records), project_root=project_root),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"catalog={catalog_path}")


if __name__ == "__main__":
    main()
