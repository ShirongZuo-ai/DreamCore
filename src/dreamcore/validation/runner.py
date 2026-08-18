"""Contract-first runner for Signal Validation V1."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dreamcore.config import load_config
from dreamcore.validation.alpha import run_alpha_synthetic
from dreamcore.validation.crosstalk import run_synthetic_crosstalk
from dreamcore.validation.dreams import validate_archive
from dreamcore.validation.eye_movement import run_dreams_rem
from dreamcore.validation.k_complex import run_dreams_k_complex


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )


def _production_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    automatic = config["automatic_analysis"]
    eye_keys = (
        "filtering",
        "windowing",
        "quality",
        "normalization",
        "local_baseline",
        "event_detection",
    )
    alpha_config = {"product": automatic["alpha"], "alpha": config["alpha"]}
    eye_config = {key: config["eye_movement"][key] for key in eye_keys}
    kc_config = {"product": automatic["k_complex"], "detector": config["k_complex_v0"]}
    return {
        "alpha": {
            "algorithm_version": automatic["alpha"]["algorithm_version"],
            "config_hash": _hash(alpha_config),
        },
        "eye_movement": {
            "algorithm_version": automatic["eye_movement"]["algorithm_version"],
            "config_hash": _hash(eye_config),
        },
        "k_complex": {
            "algorithm_version": automatic["k_complex"]["algorithm_version"],
            "config_hash": _hash(kc_config),
            "detector_config_hash": _hash(config["k_complex_v0"]),
        },
    }


def build_contract(project_root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    validation = config["signal_validation_v1"]
    dreams = validation["dreams"]
    source_manifest_path = project_root / str(validation["source_manifest"])
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    archives = {}
    for key in ("k_complex", "rem"):
        item = dreams[key]
        archives[key] = validate_archive(
            project_root / str(item["archive_path"]),
            size_bytes=int(item["published_size_bytes"]),
            published_checksum=str(item["published_checksum"]),
        )
        archives[key]["path"] = str(item["archive_path"])
    implementation_paths = tuple(
        sorted((project_root / "src/dreamcore/validation").glob("*.py"))
    ) + (project_root / "scripts/run_signal_validation_v1.py",)
    contract = {
        "schema_version": validation["schema_version"],
        "validation_version": validation["validation_version"],
        "revision_note": validation["revision_note"],
        "validation_implementation": {
            str(path.relative_to(project_root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in implementation_paths
        },
        "production_algorithms": _production_contract(config),
        "benchmark": {
            "dataset_title": dreams["dataset_title"],
            "record_id": dreams["record_id"],
            "doi": dreams["doi"],
            "license_id": dreams["license_id"],
            "source_manifest_sha256": hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
            "archives": archives,
            "annotation_semantics": {
                "k_complex": "expert event onset and duration interval; no expert trough landmark",
                "rem": "expert rapid-eye-movement onset and duration interval",
                "hypnogram": "R&K stage code every 5 seconds",
            },
            "known_source_quality_findings": {
                "k_complex_expert_2_scope": "excerpts 1-5 only",
                "rem_nonpositive_duration_rows": 1,
            },
        },
        "matching": validation["matching"],
        "synthetic": {
            "alpha": validation["alpha_synthetic"],
            "cross_talk": validation["synthetic_crosstalk"],
        },
        "metric_definitions": {
            "precision": "matched / detector events",
            "recall": "matched / evaluable expert events",
            "f1": "harmonic mean of precision and recall",
            "eye_candidate_agreement": (
                "matched DreamCore candidates / all DreamCore candidates; "
                "not generic eye-movement precision"
            ),
            "frequency_error_hz": "estimated reliable peak minus injected peak",
            "alpha_power_relative_error": (
                "(median estimated absolute alpha power - theoretical injected "
                "sinusoid power A^2/2) / theoretical injected sinusoid power, "
                "reported for amplitude-ordering cases"
            ),
            "operational_kc_trough": (
                "raw CZ-A1 minimum inside expert interval; not expert trough ground truth"
            ),
        },
        "source_manifest": source_manifest,
    }
    contract["contract_sha256"] = _hash(contract)
    return contract


def write_contract(project_root: Path, config: Mapping[str, Any]) -> tuple[Path, str]:
    validation = config["signal_validation_v1"]
    output = project_root / str(validation["output_root"])
    output.mkdir(parents=True, exist_ok=True)
    contract = build_contract(project_root, config)
    path = output / str(validation["contract_filename"])
    _write_json(path, contract)
    digest = str(contract["contract_sha256"])
    (output / str(validation["contract_hash_filename"])).write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return path, digest


def verify_contract(project_root: Path, config: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    validation = config["signal_validation_v1"]
    path = project_root / str(validation["output_root"]) / str(validation["contract_filename"])
    if not path.is_file():
        raise FileNotFoundError("Signal Validation contract missing; run --contract-only first")
    stored = json.loads(path.read_text(encoding="utf-8"))
    current = build_contract(project_root, config)
    if stored != current:
        raise ValueError("Signal Validation contract no longer matches code/config/source inputs")
    expected = str(stored.pop("contract_sha256"))
    if _hash(stored) != expected:
        raise ValueError("Signal Validation contract hash is invalid")
    stored["contract_sha256"] = expected
    return stored, expected


def run_all(project_root: Path, config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    validation = config["signal_validation_v1"]
    output = project_root / str(validation["output_root"])
    contract, contract_hash = verify_contract(project_root, config)
    timings = {}
    started = time.perf_counter()

    section_start = time.perf_counter()
    alpha_rows, alpha_summary = run_alpha_synthetic(config)
    timings["alpha_synthetic_s"] = time.perf_counter() - section_start
    _write_csv(output / "alpha_synthetic_cases.csv", alpha_rows)
    _write_csv(
        output / "alpha_synthetic_summary.csv",
        [{"metric": key, "value": value} for key, value in alpha_summary.items()],
    )

    section_start = time.perf_counter()
    rem_matches, rem_recordings, rem_summary = run_dreams_rem(project_root, config)
    timings["dreams_rem_s"] = time.perf_counter() - section_start
    _write_csv(output / "dreams_rem_event_matching.csv", rem_matches)
    _write_csv(output / "dreams_rem_recordings.csv", rem_recordings)
    _write_json(output / "dreams_rem_summary.json", rem_summary)

    section_start = time.perf_counter()
    expert_1, expert_2, interexpert, kc_summary = run_dreams_k_complex(project_root, config)
    timings["dreams_k_complex_s"] = time.perf_counter() - section_start
    _write_csv(output / "dreams_kc_expert1_matching.csv", expert_1)
    _write_csv(output / "dreams_kc_expert2_matching.csv", expert_2)
    _write_csv(output / "dreams_kc_interexpert.csv", interexpert)
    _write_json(output / "dreams_kc_summary.json", kc_summary)

    section_start = time.perf_counter()
    crosstalk_rows, crosstalk_summary = run_synthetic_crosstalk(config)
    timings["synthetic_crosstalk_s"] = time.perf_counter() - section_start
    _write_csv(output / "synthetic_crosstalk.csv", crosstalk_rows)

    timings["total_s"] = time.perf_counter() - started
    summary = {
        "schema_version": "dreamcore.signal_validation.summary.v1",
        "validation_version": validation["validation_version"],
        "contract_sha256": contract_hash,
        "contract": {
            "production_algorithms": contract["production_algorithms"],
            "benchmark": contract["benchmark"],
            "matching": contract["matching"],
        },
        "alpha": alpha_summary,
        "eye_movement": rem_summary,
        "k_complex": kc_summary,
        "cross_talk": crosstalk_summary,
        "performance": timings,
        "thresholds_tuned_after_contract": False,
    }
    _write_json(output / str(validation["summary_filename"]), summary)
    return summary
