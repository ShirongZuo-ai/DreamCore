"""Run the frozen CBraMod K-complex verifier benchmark locally."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import resource
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from sklearn import __version__ as sklearn_version
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dreamcore.foundation_models.cbramod.adapter import CBraModAdapter
from dreamcore.foundation_models.cbramod.checkpoint import load_frozen_model, validate_checkpoint
from dreamcore.foundation_models.cbramod.labels import label_candidate
from dreamcore.foundation_models.cbramod.provenance import (
    CHECKPOINT_LICENSE,
    CHECKPOINT_REPOSITORY,
    CHECKPOINT_REVISION,
    UPSTREAM_LICENSE,
    UPSTREAM_REPOSITORY,
    UPSTREAM_REVISION,
)
from dreamcore.k_complex import (
    MORPHOLOGY_B1_FEATURE_NAMES,
    detect_k_complexes,
    morphology_b1_features,
)
from dreamcore.k_complex.verifier import artifact_checksum
from dreamcore.validation.dreams import (
    excerpt_index,
    load_k_complex_signal,
    load_n2_bouts,
    parse_interval_annotations,
    recording_paths,
)


def canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def intervals(path: Path, recording_id: str, scorer: str):
    if not path.is_file():
        return None
    return tuple(
        {"onset_s": item.onset_s, "end_s": item.end_s}
        for item in parse_interval_annotations(path, recording_id=recording_id, scorer=scorer)
        if item.valid
    )


def morphology(event) -> np.ndarray:
    """Compatibility wrapper for the authoritative product feature extractor."""

    return np.asarray(morphology_b1_features(event), dtype=float)


def metrics(y_true, probability, threshold):
    predicted = probability >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, predicted, average="binary", zero_division=0
    )
    negative, false_positive, false_negative, positive = confusion_matrix(
        y_true, predicted, labels=[0, 1]
    ).ravel()
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": negative / (negative + false_positive)
        if negative + false_positive
        else None,
        "auroc": roc_auc_score(y_true, probability) if len(set(y_true)) == 2 else None,
        "auprc": average_precision_score(y_true, probability) if len(set(y_true)) == 2 else None,
        "true_positive": int(positive),
        "false_positive": int(false_positive),
        "true_negative": int(negative),
        "false_negative": int(false_negative),
    }


def descriptive_recall_operating_point(y_true, probability, minimum_recall):
    """Summarize an OOF curve point; this is not a deployable tuned threshold."""

    positive = np.sort(probability[y_true == 1])
    allowed_misses = int(np.floor((1.0 - minimum_recall) * positive.size))
    threshold = float(positive[min(allowed_misses, positive.size - 1)])
    predicted = probability >= threshold
    retained = int(np.sum(predicted & (y_true == 1)))
    negatives = int(np.sum(y_true == 0))
    removed = int(np.sum(~predicted & (y_true == 0)))
    return {
        "descriptive_oof_threshold": threshold,
        "recall_retained": retained / int(np.sum(y_true == 1)),
        "false_candidates_removed": removed,
        "false_candidates_total": negatives,
        "false_candidates_removed_fraction": removed / negatives if negatives else None,
    }


def grouped_predictions(features, labels, groups, config):
    probabilities = np.full(labels.shape, np.nan)
    for held_out in sorted(set(groups)):
        test = groups == held_out
        train = ~test
        if len(set(labels[train])) < 2:
            continue
        classifier = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                max_iter=int(config["classifier"]["linear_max_iterations"]),
                class_weight=str(config["classifier"]["class_weight"]),
                random_state=int(config["random_seed"]),
            ),
        )
        classifier.fit(features[train], labels[train])
        probabilities[test] = classifier.predict_proba(features[test])[:, 1]
    return probabilities


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    args = parser.parse_args()
    project = Path.cwd()
    full = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    config = full["cbramod_kc_v1"]
    validation = full["signal_validation_v1"]
    dreams = validation["dreams"]
    dreams_kc = dreams["k_complex"]
    detector = full["k_complex_v0"]
    output = project / "results/cbramod_kc_v1"
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = validate_checkpoint(Path(config["checkpoint_path"]), config["checkpoint_sha256"])
    contract = {
        "schema_version": "dreamcore.cbramod_kc.validation.v1",
        "frozen_at": str(config["benchmark_contract_frozen_at"]),
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_revision": UPSTREAM_REVISION,
        "upstream_license": UPSTREAM_LICENSE,
        "checkpoint_repository": CHECKPOINT_REPOSITORY,
        "checkpoint_revision": CHECKPOINT_REVISION,
        "checkpoint_license": CHECKPOINT_LICENSE,
        "checkpoint_sha256": checkpoint["sha256"],
        "architecture": config["architecture"],
        "preprocessing": {
            "model_sampling_rate_hz": config["model_sampling_rate_hz"],
            "filtering": config["filtering"],
            "normalization": "none; preserve calibrated microvolts as official preprocessing does",
            "patching": "contiguous non-overlapping one-second patches",
        },
        "channel_policy": config["channel_policy"],
        "window": {"before_s": config["context_before_s"], "after_s": config["context_after_s"]},
        "labels": {
            "two_expert_match": "high_confidence_positive",
            "one_of_two_match": "single_expert_positive",
            "neither_with_margin": "high_confidence_negative",
            "expert_2_missing": "never interpreted as a negative vote",
            "exclusion_margin_s": config["exclusion_margin_s"],
        },
        "split_protocol": config["split_protocol"],
        "random_seed": config["random_seed"],
        "classifiers": [
            "B0 all V0 accepted",
            "B1 morphology logistic",
            "B2 CBraMod logistic",
            "B3 fusion logistic",
        ],
        "metrics": ["precision", "recall", "f1", "specificity", "auroc", "auprc"],
        "operating_point": {
            "minimum_recall_retained": config["operating_point"]["minimum_recall_retained"],
            "threshold_selection": "descriptive threshold on grouped out-of-fold predictions",
        },
    }
    contract_hash = canonical_hash(contract)
    (output / "validation_contract.json").write_text(
        json.dumps({**contract, "contract_sha256": contract_hash}, indent=2) + "\n"
    )
    adapter = CBraModAdapter(config)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rss_before_model = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    model = load_frozen_model(Path(config["checkpoint_path"]), config, device=device)
    rss_after_model = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    batch_sweep = []
    for batch_size in (1, 2, 4, 8):
        sample = torch.zeros(
            (
                batch_size,
                1,
                int(config["context_before_s"] + config["context_after_s"]),
                int(config["architecture"]["patch_points"]),
            ),
            device=device,
        )
        torch.cuda.reset_peak_memory_stats() if device == "cuda" else None
        with torch.inference_mode():
            model(sample)
        torch.cuda.synchronize() if device == "cuda" else None
        started = time.perf_counter()
        with torch.inference_mode():
            benchmark_output = model(sample)
        torch.cuda.synchronize() if device == "cuda" else None
        batch_sweep.append(
            {
                "batch_size": batch_size,
                "latency_s": time.perf_counter() - started,
                "output_shape": list(benchmark_output.shape),
                "peak_allocated_gpu_bytes": torch.cuda.max_memory_allocated()
                if device == "cuda"
                else None,
                "peak_reserved_gpu_bytes": torch.cuda.max_memory_reserved()
                if device == "cuda"
                else None,
            }
        )
        del sample, benchmark_output
    hardware = {
        "torch_version": torch.__version__,
        "cuda_runtime_version": torch.version.cuda,
        "device": device,
        "gpu_model": torch.cuda.get_device_name(0) if device == "cuda" else None,
        "gpu_total_bytes": torch.cuda.get_device_properties(0).total_memory
        if device == "cuda"
        else None,
        "gpu_available_bytes_before_extraction": torch.cuda.mem_get_info()[0]
        if device == "cuda"
        else None,
        "system_ram_total_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "system_ram_available_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES"),
        "checkpoint_size_bytes": checkpoint["size_bytes"],
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "cpu_rss_model_load_delta_bytes": rss_after_model - rss_before_model,
        "batch_sweep_10_second_single_channel": batch_sweep,
    }
    (output / "hardware.json").write_text(json.dumps(hardware, indent=2) + "\n")
    root = project / dreams_kc["extracted_root"]
    rate = float(dreams_kc["sampling_rate_hz"])
    detector_hash = canonical_hash(detector)
    rows = []
    embeddings = []
    morphologies = []
    recording_source_hashes = {}
    extraction_start = time.perf_counter()
    torch.cuda.reset_peak_memory_stats() if device == "cuda" else None
    for edf_path in recording_paths(root, dreams_kc["recording_glob"]):
        index = excerpt_index(edf_path)
        recording_id = f"dreams-kc-excerpt{index}"
        signal_path = root / dreams_kc["signal_text_template"].format(index=index)
        signal_fingerprint = source_hash(signal_path)
        recording_source_hashes[recording_id] = signal_fingerprint
        channel, signal = load_k_complex_signal(signal_path, expected_rate_hz=rate)
        bouts = load_n2_bouts(
            root / dreams_kc["hypnogram_template"].format(index=index), dreams, detector
        )
        events = detect_k_complexes(
            signal,
            rate,
            channel,
            bouts,
            detector,
            dataset_id="dreams-k-complexes",
            subject_id=f"excerpt{index}",
            recording_id=recording_id,
            detector_version=detector["detector_version"],
            config_hash=detector_hash,
            source_fingerprint=signal_fingerprint,
        )
        expert_1 = intervals(
            root / dreams_kc["expert_1_template"].format(index=index), recording_id, "expert_1"
        )
        expert_2 = intervals(
            root / dreams_kc["expert_2_template"].format(index=index), recording_id, "expert_2"
        )
        for event in events:
            center = int(round(event.negative_trough_s * rate))
            before = int(round(float(config["context_before_s"]) * rate))
            after = int(round(float(config["context_after_s"]) * rate))
            start = center - before
            end = center + after
            if start < 0 or end > signal.size:
                continue
            prepared = adapter.prepare(
                signal[None, start:end],
                rate,
                (channel,),
                unit=dreams_kc["unit"],
                reference="A1 (native DREAMS bipolar channel label CZ-A1)",
                dataset_id="dreams-k-complexes",
            )
            tensor = torch.from_numpy(prepared.values[None]).to(device)
            with torch.inference_mode():
                embedding = model(tensor).mean(dim=(1, 2)).cpu().numpy()[0]
            label = label_candidate(
                event.to_dict(),
                expert_1 or (),
                expert_2,
                exclusion_margin_s=float(config["exclusion_margin_s"]),
            )
            rows.append(
                {
                    "event_id": event.event_id,
                    "recording_id": recording_id,
                    "excerpt": index,
                    "channel": channel,
                    "original_sampling_rate_hz": rate,
                    "model_sampling_rate_hz": config["model_sampling_rate_hz"],
                    "unit": dreams_kc["unit"],
                    "reference": "A1",
                    "label_group": label,
                    "negative_trough_s": event.negative_trough_s,
                    "v0_score": event.score,
                }
            )
            embeddings.append(embedding)
            morphologies.append(morphology(event))
    elapsed = time.perf_counter() - extraction_start
    embedding_matrix = np.asarray(embeddings)
    morphology_matrix = np.asarray(morphologies)
    np.savez_compressed(output / "embeddings.npz", embeddings=embedding_matrix)
    with (output / "sample_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    primary = np.asarray(
        [
            row["label_group"] in {"high_confidence_positive", "high_confidence_negative"}
            for row in rows
        ]
    )
    labels = np.asarray(
        [row["label_group"] == "high_confidence_positive" for row in rows], dtype=int
    )[primary]
    groups = np.asarray([row["recording_id"] for row in rows])[primary]
    emb = embedding_matrix[primary]
    morph = morphology_matrix[primary]
    final_classifier = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=int(config["classifier"]["linear_max_iterations"]),
            class_weight=str(config["classifier"]["class_weight"]),
            random_state=int(config["random_seed"]),
        ),
    ).fit(morph, labels)
    scaler = final_classifier.named_steps["standardscaler"]
    logistic = final_classifier.named_steps["logisticregression"]
    product_verifier = full["automatic_analysis"]["k_complex"]["verifier"]
    benchmark_threshold = float(config["classifier"]["decision_threshold"])
    if benchmark_threshold != float(product_verifier["decision_threshold"]):
        raise RuntimeError("product B1 threshold differs from the frozen benchmark threshold")
    artifact = {
        "schema_version": "dreamcore.k_complex.morphology_verifier.v1",
        "algorithm_version": str(product_verifier["version"]),
        "verification_method": str(product_verifier["method"]),
        "feature_names": list(MORPHOLOGY_B1_FEATURE_NAMES),
        "feature_semantics": {
            "score": "K-Complex V0 morphology score",
            "duration_s": "original V0 end_s minus onset_s",
            "negative_trough_amplitude": "original signed V0 local-baseline amplitude in uV",
            "positive_peak_delay_s": "positive_peak_s minus negative_trough_s; 0.0 when absent",
        },
        "preprocessing": {
            "feature_extraction": "exact frozen B1 morphology(event) ordering",
            "standard_scaler": {
                "with_mean": True,
                "with_std": True,
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
            },
        },
        "classifier": {
            "family": "sklearn.linear_model.LogisticRegression",
            "effective_regularization": "L2 under the frozen scikit-learn default",
            "hyperparameters": {
                "C": float(logistic.C),
                "class_weight": logistic.class_weight,
                "dual": bool(logistic.dual),
                "fit_intercept": bool(logistic.fit_intercept),
                "intercept_scaling": float(logistic.intercept_scaling),
                "l1_ratio": float(logistic.l1_ratio),
                "max_iter": int(logistic.max_iter),
                "n_jobs": logistic.n_jobs,
                "penalty": str(logistic.penalty),
                "random_state": int(logistic.random_state),
                "solver": str(logistic.solver),
                "tol": float(logistic.tol),
                "verbose": int(logistic.verbose),
                "warm_start": bool(logistic.warm_start),
            },
            "coefficients": logistic.coef_[0].tolist(),
            "intercept": float(logistic.intercept_[0]),
        },
        "decision_threshold": benchmark_threshold,
        "threshold_semantics": (
            f"accepted when positive-class probability >= {benchmark_threshold:g}"
        ),
        "source_benchmark": {
            "contract_sha256": contract_hash,
            "split_protocol": str(config["split_protocol"]),
            "evaluation_separate_from_final_fit": True,
        },
        "training_data_provenance": {
            "dataset": str(dreams["dataset_title"]),
            "source_manifest": str(validation["source_manifest"]),
            "source_manifest_sha256": source_hash(project / validation["source_manifest"]),
            "archive_published_checksum": str(dreams_kc["published_checksum"]),
            "recording_source_sha256": recording_source_hashes,
            "eligible_recordings": sorted(set(groups)),
            "eligible_example_count": int(labels.size),
            "positive_example_count": int(np.sum(labels == 1)),
            "negative_example_count": int(np.sum(labels == 0)),
            "label_policy": {
                "included": ["high_confidence_positive", "high_confidence_negative"],
                "excluded": [
                    "ambiguous",
                    "single_expert_positive",
                    "single_expert_unmatched",
                ],
                "expert_2_missing": "never interpreted as a negative vote",
            },
        },
        "fit": {
            "scope": "all eligible frozen DREAMS B1 training examples",
            "random_seed": int(config["random_seed"]),
            "scikit_learn_version": sklearn_version,
        },
        "artifact_checksum": {
            "algorithm": "sha256-canonical-json-excluding-artifact_checksum",
            "value": "",
        },
    }
    artifact["artifact_checksum"]["value"] = artifact_checksum(artifact)
    artifact_path = project / str(product_verifier["artifact_path"])
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    models = {
        "B0_k_complex_v0": np.ones(labels.shape),
        "B1_morphology_linear": grouped_predictions(morph, labels, groups, config),
        "B2_cbramod_linear": grouped_predictions(emb, labels, groups, config),
        "B3_fusion_linear": grouped_predictions(np.hstack((emb, morph)), labels, groups, config),
    }
    metric_rows = []
    prediction_rows = []
    for name, probability in models.items():
        valid = np.isfinite(probability)
        result = metrics(labels[valid], probability[valid], benchmark_threshold)
        result.update(
            descriptive_recall_operating_point(
                labels[valid],
                probability[valid],
                float(config["operating_point"]["minimum_recall_retained"]),
            )
        )
        metric_rows.append({"baseline": name, **result})
        for group, truth, score in zip(
            groups[valid], labels[valid], probability[valid], strict=True
        ):
            prediction_rows.append(
                {"baseline": name, "recording_id": group, "label": truth, "probability": score}
            )
    for filename, values in (
        ("grouped_metrics.csv", metric_rows),
        ("prediction_rows.csv", prediction_rows),
    ):
        with (output / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=values[0].keys())
            writer.writeheader()
            writer.writerows(values)
    pca = PCA(n_components=2, random_state=int(config["random_seed"])).fit_transform(emb)
    figure, axis = plt.subplots(figsize=(8, 6))
    for value, name, color in (
        (1, "High-confidence positive", "#177245"),
        (0, "High-confidence negative", "#c84b31"),
    ):
        selected = labels == value
        axis.scatter(pca[selected, 0], pca[selected, 1], c=color, label=name, alpha=0.72, s=26)
    axis.set(xlabel="PCA 1", ylabel="PCA 2", title="Frozen CBraMod embeddings (color=KC label)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output / "embedding_pca.png", dpi=160)
    plt.close(figure)
    identity = None
    if len(rows) >= 20:
        folds = StratifiedKFold(n_splits=3, shuffle=True, random_state=int(config["random_seed"]))
        identity = float(
            np.mean(
                cross_val_score(
                    make_pipeline(
                        StandardScaler(),
                        LogisticRegression(
                            max_iter=int(config["classifier"]["linear_max_iterations"])
                        ),
                    ),
                    embedding_matrix,
                    np.asarray([row["excerpt"] for row in rows]),
                    cv=folds,
                )
            )
        )
    summary = {
        "contract_sha256": contract_hash,
        "device": device,
        "sample_count": len(rows),
        "label_counts": {
            name: sum(row["label_group"] == name for row in rows)
            for name in sorted({row["label_group"] for row in rows})
        },
        "embedding_dimension": int(embedding_matrix.shape[1]),
        "extraction_latency_s": elapsed,
        "throughput_candidates_per_s": len(rows) / elapsed,
        "peak_allocated_gpu_bytes": torch.cuda.max_memory_allocated() if device == "cuda" else None,
        "peak_reserved_gpu_bytes": torch.cuda.max_memory_reserved() if device == "cuda" else None,
        "excerpt_identity_random_candidate_cv_accuracy_diagnostic_only": identity,
        "metrics": metric_rows,
        "final_b1_product_fit": {
            "artifact_path": str(artifact_path.relative_to(project)),
            "artifact_checksum": artifact["artifact_checksum"]["value"],
            "eligible_example_count": int(labels.size),
            "evaluation_separate_from_final_fit": True,
        },
    }
    (output / "embedding_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
