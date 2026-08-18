"""Run the default morphology B1 verifier on the untuned HMC SN001 product path."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

from dreamcore.analysis.manager import FEATURE_K_COMPLEX, AutomaticAnalysisManager
from dreamcore.api.http import build_registry


def summarize_hmc_product_rows(rows: list[dict]) -> dict:
    probabilities = np.asarray([row["verification_probability"] for row in rows], dtype=float)
    accepted = [row for row in rows if row["verification_status"] == "accepted"]
    rejected = [row for row in rows if row["verification_status"] == "rejected"]
    ordinal_status = defaultdict(lambda: {"candidate_count": 0, "accepted_count": 0})
    accepted_first_second = defaultdict(dict)
    for row in rows:
        ordinal = int(row["ordinal_in_n2_bout"])
        if ordinal not in {1, 2}:
            continue
        key = f"ordinal_{ordinal}"
        ordinal_status[key]["candidate_count"] += 1
        if row["verification_status"] == "accepted":
            ordinal_status[key]["accepted_count"] += 1
            accepted_first_second[str(row["n2_bout_id"])][str(ordinal)] = float(
                row["negative_trough_s"]
            )
    quantiles = np.quantile(probabilities, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "ground_truth_status": "unlabeled product sanity inference only",
        "candidate_count": len(rows),
        "verified_count": len(accepted),
        "rejected_count": len(rejected),
        "probability_distribution": {
            "minimum": float(np.min(probabilities)),
            "p05": float(quantiles[0]),
            "p25": float(quantiles[1]),
            "median": float(quantiles[2]),
            "mean": float(np.mean(probabilities)),
            "p75": float(quantiles[3]),
            "p95": float(quantiles[4]),
            "maximum": float(np.max(probabilities)),
        },
        "first_second_candidate_behavior": dict(ordinal_status),
        "accepted_first_second_by_n2_bout": dict(accepted_first_second),
        "interpretation": "No HMC labels were used and no B1 parameter was tuned on HMC.",
    }


def main() -> None:
    project = Path.cwd()
    full = yaml.safe_load((project / "configs/default.yaml").read_text(encoding="utf-8"))
    verifier_config = full["automatic_analysis"][FEATURE_K_COMPLEX]["verifier"]
    session_id = str(verifier_config["sanity_session_id"])
    registry = build_registry(project / full["session_transport"]["session_package_root"])
    manager = AutomaticAnalysisManager(project, registry, full)
    try:
        manifest = registry.get_session_by_id(session_id)
        sources = manager._source_signals(manifest, FEATURE_K_COMPLEX)
        identity = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
        result = manager._run_k_complex(manifest, sources, identity)
    finally:
        manager.shutdown()
    rows = json.loads(Path(result["artifacts"]["events"]).read_text(encoding="utf-8"))["events"]
    expected = int(verifier_config["sanity_expected_v0_candidate_count"])
    if len(rows) != expected:
        raise RuntimeError(
            f"HMC {session_id} V0 candidate count changed: {len(rows)} != {expected}"
        )
    output = project / str(verifier_config["sanity_output_root"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / "hmc_sn001_inference.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": "dreamcore.k_complex.morphology_b1.sanity.v1",
        "session_id": session_id,
        "candidate_detector": result["analysis"]["candidate_detector"],
        "verifier_version": result["analysis"]["verifier_version"],
        "verification_threshold": result["analysis"]["verification_threshold"],
        **summarize_hmc_product_rows(rows),
    }
    (output / "hmc_sn001_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
