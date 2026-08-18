"""Run untuned HMC and synthetic ocular-leakage checks for frozen CBraMod."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dreamcore.analysis.manager import FEATURE_K_COMPLEX, AutomaticAnalysisManager
from dreamcore.api.http import build_registry
from dreamcore.foundation_models.cbramod.adapter import CBraModAdapter
from dreamcore.foundation_models.cbramod.checkpoint import load_frozen_model
from dreamcore.k_complex import N2Bout, detect_k_complexes
from dreamcore.validation.synthetic import cross_talk_cases


def encode_window(adapter, model, values, rate, channel, *, dataset_id, device):
    prepared = adapter.prepare(
        values[None, :],
        rate,
        (channel,),
        unit="uV",
        reference=None,
        dataset_id=dataset_id,
    )
    with torch.inference_mode():
        return (
            model(torch.from_numpy(prepared.values[None]).to(device))
            .mean(dim=(1, 2))
            .cpu()
            .numpy()[0]
        )


def main() -> None:
    project = Path.cwd()
    full = yaml.safe_load(Path("configs/default.yaml").read_text())
    config = full["cbramod_kc_v1"]
    output = project / "results/cbramod_kc_v1"
    manifest_rows = list(csv.DictReader((output / "sample_manifest.csv").open()))
    embeddings = np.load(output / "embeddings.npz")["embeddings"]
    primary = np.asarray(
        [
            row["label_group"] in {"high_confidence_positive", "high_confidence_negative"}
            for row in manifest_rows
        ]
    )
    labels = np.asarray(
        [row["label_group"] == "high_confidence_positive" for row in manifest_rows], dtype=int
    )[primary]
    classifier = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=int(config["classifier"]["linear_max_iterations"]),
            class_weight=str(config["classifier"]["class_weight"]),
            random_state=int(config["random_seed"]),
        ),
    ).fit(embeddings[primary], labels)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_frozen_model(Path(config["checkpoint_path"]), config, device=device)
    adapter = CBraModAdapter(config)
    registry = build_registry(Path(full["session_transport"]["session_package_root"]))
    manager = AutomaticAnalysisManager(project, registry, full)
    try:
        manifest = registry.get_session_by_id("SN001")
        sources = manager._source_signals(manifest, FEATURE_K_COMPLEX)
        identity = manager._identity(manifest, FEATURE_K_COMPLEX, sources)
        result = manager._run_k_complex(manifest, sources, identity)
        events = json.loads(Path(result["artifacts"]["events"]).read_text())["events"]
        signal = sources[0]
        window = registry.load_signal_window(
            "SN001", signal.id, 0.0, manifest.recording.duration_seconds
        )
        scale = float(
            full["automatic_analysis"]["k_complex"]["input_scale_to_uv_by_unit"][signal.unit]
        )
        values = np.asarray(window.samples, dtype=float) * scale
        rate = float(signal.sampling_rate_hz)
        radius_before = int(round(float(config["context_before_s"]) * rate))
        radius_after = int(round(float(config["context_after_s"]) * rate))
        hmc_rows = []
        for event in events:
            center = int(round(float(event["negative_trough_s"]) * rate))
            start, end = center - radius_before, center + radius_after
            if start < 0 or end > values.size:
                probability = None
            else:
                embedding = encode_window(
                    adapter,
                    model,
                    values[start:end],
                    rate,
                    str(signal.original_channel_name or signal.channel_name),
                    dataset_id=manifest.dataset.id,
                    device=device,
                )
                probability = float(classifier.predict_proba(embedding[None, :])[0, 1])
            status = (
                "uncertain"
                if probability is None
                else "accepted"
                if probability >= 0.5
                else "rejected"
            )
            hmc_rows.append(
                {
                    "event_id": event["event_id"],
                    "n2_bout_id": event["n2_bout_id"],
                    "ordinal_in_n2_bout": event["ordinal_in_n2_bout"],
                    "negative_trough_s": event["negative_trough_s"],
                    "original_morphology_score": event["score"],
                    "cbramod_probability": probability,
                    "status": status,
                }
            )
    finally:
        manager.shutdown()
    with (output / "hmc_sn001_inference.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=hmc_rows[0].keys())
        writer.writeheader()
        writer.writerows(hmc_rows)
    first_second = defaultdict(dict)
    for row in hmc_rows:
        if row["status"] == "accepted" and row["ordinal_in_n2_bout"] in {1, 2}:
            first_second[row["n2_bout_id"]][str(row["ordinal_in_n2_bout"])] = row[
                "negative_trough_s"
            ]

    stress = full["signal_validation_v1"]["synthetic_crosstalk"]
    stress_rate = float(stress["sampling_rate_hz"])
    bout = N2Bout(
        "synthetic-N2-0001",
        "N2",
        0.0,
        float(stress["duration_s"]),
        ("synthetic",),
        ("ground_truth",),
    )
    stress_rows = []
    for case in cross_talk_cases(stress):
        events = detect_k_complexes(
            case.eeg_frontal_uv,
            stress_rate,
            str(stress["eeg_frontal_channel"]),
            (bout,),
            full["k_complex_v0"],
            dataset_id="synthetic-crosstalk",
            subject_id=str(case.seed),
            recording_id=case.case_id,
            detector_version=full["k_complex_v0"]["detector_version"],
            config_hash="frozen-k-complex-v0",
            source_fingerprint="deterministic-synthetic-case",
        )
        accepted = 0
        for event in events:
            center = int(round(event.negative_trough_s * stress_rate))
            start = center - int(round(float(config["context_before_s"]) * stress_rate))
            end = center + int(round(float(config["context_after_s"]) * stress_rate))
            if start < 0 or end > case.eeg_frontal_uv.size:
                continue
            embedding = encode_window(
                adapter,
                model,
                case.eeg_frontal_uv[start:end],
                stress_rate,
                str(stress["eeg_frontal_channel"]),
                dataset_id="synthetic-crosstalk",
                device=device,
            )
            accepted += int(classifier.predict_proba(embedding[None, :])[0, 1] >= 0.5)
        stress_rows.append(
            {
                "case_id": case.case_id,
                "family": case.family,
                "true_k_complex": case.true_k_complex,
                "v0_candidates": len(events),
                "cbramod_accepted": accepted,
            }
        )
    with (output / "ocular_leakage_inference.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=stress_rows[0].keys())
        writer.writeheader()
        writer.writerows(stress_rows)
    probabilities = [row["cbramod_probability"] for row in hmc_rows if row["cbramod_probability"]]
    counts = Counter(row["status"] for row in hmc_rows)
    false_stress = [row for row in stress_rows if not row["true_k_complex"]]
    summary = {
        "hmc_sn001": {
            "ground_truth_status": "unlabeled product sanity check only",
            "baseline_candidate_count": len(hmc_rows),
            "status_counts": dict(counts),
            "probability": {
                "minimum": min(probabilities),
                "median": float(np.median(probabilities)),
                "maximum": max(probabilities),
            },
            "accepted_first_second_by_n2_bout": first_second,
        },
        "ocular_leakage": {
            "false_v0_candidates": sum(row["v0_candidates"] for row in false_stress),
            "false_candidates_accepted": sum(row["cbramod_accepted"] for row in false_stress),
            "scope": "deterministic stress cases; classifier trained on DREAMS only",
        },
    }
    (output / "product_checks.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
