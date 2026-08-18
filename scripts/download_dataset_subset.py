"""Download the bounded DreamCore Multi-Dataset Library V1 source batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/dataset_library_v1.yaml"))
    parser.add_argument("--dataset", choices=("all", "sleep_edfx", "hmc", "isruc"), default="all")
    parser.add_argument("--recordings", nargs="*")
    parser.add_argument("--subjects", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def sha256(path: Path, chunk_size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_recordings(dataset: dict[str, Any], args: argparse.Namespace):
    requested_recordings = set(args.recordings or ())
    requested_subjects = set(args.subjects or ())
    for recording_id, recording in dataset.get("recordings", {}).items():
        if requested_recordings and recording_id not in requested_recordings:
            continue
        if requested_subjects and str(recording["subject_id"]) not in requested_subjects:
            continue
        yield recording_id, recording


def physionet_plan(
    key: str,
    dataset: dict[str, Any],
    raw_root: Path,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    destination_root = raw_root / dataset["raw_subdirectory"]
    output = []
    for recording_id, recording in selected_recordings(dataset, args):
        for role in ("psg", "annotations", "annotation_audit"):
            source = recording.get(role)
            if not source:
                continue
            output.append(
                {
                    "dataset": key,
                    "recording_id": recording_id,
                    "role": role,
                    "url": dataset["base_url"] + source["name"],
                    "destination": destination_root / source["name"],
                    "estimated_size_mb": float(source["estimated_size_mb"]),
                    "sha256": source["sha256"],
                }
            )
    return output


def download_physionet(
    item: dict[str, Any], config: dict[str, Any], *, resume: bool
) -> dict[str, Any]:
    destination = Path(item["destination"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    chunk_size = int(config["chunk_size_bytes"])
    if destination.is_file() and sha256(destination, chunk_size) == item["sha256"]:
        return audit_row(item, destination, item["sha256"])
    attempts = int(config["retries"]) + 1
    for attempt in range(1, attempts + 1):
        command = [
            "curl",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--max-time",
            str(config["timeout_s"]),
            "--user-agent",
            str(config["user_agent"]),
        ]
        if resume:
            command.extend(("--continue-at", "-"))
        command.extend(("--output", str(destination), item["url"]))
        completed = subprocess.run(command, check=False)
        if completed.returncode == 0:
            break
        if destination.is_file() and sha256(destination, chunk_size) == item["sha256"]:
            return audit_row(item, destination, item["sha256"])
        if attempt == attempts:
            raise RuntimeError(
                f"download failed after {attempts} resumable attempts for "
                f"{item['recording_id']} {item['role']}"
            )
    actual_checksum = sha256(destination, chunk_size)
    if actual_checksum != item["sha256"]:
        raise RuntimeError(f"checksum mismatch for {destination.name}")
    return audit_row(item, destination, actual_checksum)


def audit_row(item: dict[str, Any], destination: Path, actual_checksum: str) -> dict[str, Any]:
    return {
        **{key: item[key] for key in ("dataset", "recording_id", "role", "url")},
        "local_file": str(destination.resolve()),
        "downloaded_at": datetime.now(UTC).isoformat(),
        "file_size_bytes": destination.stat().st_size,
        "sha256": actual_checksum,
        "checksum_source": "official PhysioNet SHA256SUMS.txt",
    }


def merge_audit_rows(raw_root: Path, new_rows: list[dict[str, Any]]) -> Path:
    raw_root.mkdir(parents=True, exist_ok=True)
    audit_path = raw_root / "download_audit.json"
    existing_rows: list[dict[str, Any]] = []
    if audit_path.is_file():
        loaded = json.loads(audit_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            existing_rows = [row for row in loaded if isinstance(row, dict)]
    merged = {
        (str(row.get("dataset")), str(row.get("local_file"))): row
        for row in (*existing_rows, *new_rows)
    }
    audit_path.write_text(
        json.dumps(list(merged.values()), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit_path


def print_plan(plan: list[dict[str, Any]], isruc: dict[str, Any] | None) -> None:
    total_mb = 0.0
    for item in plan:
        total_mb += item["estimated_size_mb"]
        print(
            f"{item['dataset']} {item['recording_id']} {item['role']} "
            f"{item['estimated_size_mb']:.3f} MB -> {item['destination']}"
        )
        print(f"  {item['url']}")
    if isruc:
        total_mb += float(isruc["estimated_total_mb"])
        print(
            f"isruc subjects={','.join(isruc['expected_subjects'])} original official "
            f"Cohort III package {isruc['estimated_total_mb']:.1f} MB -> "
            f"{isruc['destination']}"
        )
        print(f"  official source: {isruc['official_source']}")
    print(f"ESTIMATED_TOTAL_MB={total_mb:.3f}")


def isruc_subject_files(destination: Path, subject: str) -> tuple[Path, ...]:
    """Return one complete official Cohort III subject package, if present."""

    subject_directories = sorted(
        path for path in destination.rglob(subject) if path.is_dir() and path.name == subject
    )
    for directory in subject_directories:
        required = (
            directory / f"{subject}.rec",
            directory / f"{subject}_1.txt",
            directory / f"{subject}_2.txt",
        )
        if all(path.is_file() and path.stat().st_size > 0 for path in required):
            return tuple(path for path in directory.iterdir() if path.is_file())
    return ()


def audit_isruc(
    destination: Path, isruc: dict[str, Any], subjects: tuple[str, ...], chunk_size: int
) -> list[dict[str, Any]]:
    rows = []
    for subject in subjects:
        files = isruc_subject_files(destination, subject)
        if not files:
            raise RuntimeError(f"official ISRUC Cohort III subject {subject} is incomplete")
        rows.append(
            {
                "dataset": "isruc",
                "recording_id": subject,
                "role": "original_psg_and_dual_expert_annotations",
                "official_source": isruc["official_source"],
                "local_file": str(files[0].parent.resolve()),
                "downloaded_at": datetime.now(UTC).isoformat(),
                "files": [
                    {
                        "name": path.name,
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256(path, chunk_size),
                    }
                    for path in sorted(files)
                ],
                "file_count": len(files),
                "file_size_bytes": sum(path.stat().st_size for path in files),
                "checksum_source": "locally computed; official checksum manifest unavailable",
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent
    raw_root = project_root / config["raw_root"]
    selected = tuple(config["datasets"]) if args.dataset == "all" else (args.dataset,)
    plan = []
    for key in selected:
        if key in {"sleep_edfx", "hmc"}:
            plan.extend(physionet_plan(key, config["datasets"][key], raw_root, args))
    isruc = None
    if "isruc" in selected:
        raw = config["datasets"]["isruc"]
        requested_subjects = tuple(args.subjects or raw["expected_subjects"])
        unknown = set(requested_subjects) - set(raw["expected_subjects"])
        if unknown:
            raise ValueError(f"unknown ISRUC Cohort III subjects: {sorted(unknown)}")
        isruc = {
            **raw,
            "expected_subjects": requested_subjects,
            "destination": raw_root / raw["raw_subdirectory"],
        }
    print_plan(plan, isruc)
    if args.dry_run:
        return

    audit_rows = []
    with ThreadPoolExecutor(max_workers=int(config["download"]["max_parallel_files"])) as executor:
        futures = {
            executor.submit(download_physionet, item, config["download"], resume=args.resume): item
            for item in plan
        }
        for future in as_completed(futures):
            row = future.result()
            audit_rows.append(row)
            merge_audit_rows(raw_root, [row])
            print(
                f"verified {row['dataset']} {row['recording_id']} {row['role']} "
                f"{row['file_size_bytes']} bytes"
            )
    if isruc:
        destination = Path(isruc["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        requested_subjects = tuple(isruc["expected_subjects"])
        missing = tuple(
            subject
            for subject in requested_subjects
            if not isruc_subject_files(destination, subject)
        )
        if missing:
            command = ["megadl", "--choose-files", "--path", str(destination)]
            if not args.resume:
                command.append("--disable-resume")
            command.append(isruc["public_folder_url"])
            selection = " ".join(
                str(isruc["public_folder_selection_ids"][subject]) for subject in missing
            )
            completed = subprocess.run(command, input=selection + "\n", text=True, check=False)
            if completed.returncode != 0:
                raise RuntimeError("official ISRUC Cohort III public-folder download failed")
        audit_rows.extend(
            audit_isruc(
                destination,
                isruc,
                requested_subjects,
                int(config["download"]["chunk_size_bytes"]),
            )
        )
    audit_path = merge_audit_rows(raw_root, audit_rows)
    print(f"AUDIT={audit_path}")


if __name__ == "__main__":
    main()
