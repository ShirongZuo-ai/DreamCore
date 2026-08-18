"""Frozen EOG validation matching, staging, sampling, and review contracts."""

from __future__ import annotations

from pathlib import Path

from dreamcore.eog_validation.core import (
    assign_event_stage,
    build_control_sample,
    deterministic_stratified_sample,
    match_events,
    stage_exposure,
)
from dreamcore.eog_validation.reviews import HumanReviewStore, ReviewValidationError


def _event(candidate_id: str, timestamp: float) -> dict:
    return {"candidate_id": candidate_id, "timestamp": timestamp}


def test_one_to_one_event_matching_tolerances_and_no_duplicate_assignment():
    channel_a = [_event("a1", 1.0), _event("a2", 1.4), _event("a3", 3.0)]
    channel_b = [_event("b1", 1.2), _event("b2", 1.45), _event("b3", 3.8)]

    quarter = match_events(channel_a, channel_b, 0.25)
    half = match_events(channel_a, channel_b, 0.5)
    one = match_events(channel_a, channel_b, 1.0)

    assert [(item.event_a_id, item.event_b_id) for item in quarter] == [
        ("a2", "b2"),
        ("a1", "b1"),
    ]
    assert len(half) == 2
    assert len(one) == 3
    assert len({item.event_a_id for item in one}) == len(one)
    assert len({item.event_b_id for item in one}) == len(one)


def test_event_matching_ties_are_deterministic_by_timestamp_then_id():
    a = [_event("a2", 1.0), _event("a1", 1.0)]
    b = [_event("b2", 0.9), _event("b1", 1.1)]
    first = match_events(a, b, 0.2)
    second = match_events(list(reversed(a)), list(reversed(b)), 0.2)
    assert first == second
    assert [(row.event_a_id, row.event_b_id) for row in first] == [
        ("a1", "b2"),
        ("a2", "b1"),
    ]


def test_stage_assignment_preserves_raw_label_and_exposure_denominator():
    annotations = [
        {
            "start_seconds": 0.0,
            "duration_seconds": 30.0,
            "raw_label": "Sleep stage 4",
            "normalized_label": "N3",
            "scorer": "official",
        },
        {
            "start_seconds": 30.0,
            "duration_seconds": 60.0,
            "raw_label": "Sleep stage R",
            "normalized_label": "REM",
            "scorer": "official",
        },
    ]
    assignment = assign_event_stage(29.999, annotations, unknown_label="UNKNOWN")
    assert assignment["raw_label"] == "Sleep stage 4"
    assert assignment["normalized_label"] == "N3"
    assert (
        assign_event_stage(30.0, annotations, unknown_label="UNKNOWN")["normalized_label"] == "REM"
    )
    exposure = stage_exposure(
        annotations,
        recording_duration_s=75.0,
        canonical_labels=["W", "N1", "N2", "N3", "REM", "UNKNOWN", "MOVEMENT"],
    )
    assert exposure["N3"] == 30.0
    assert exposure["REM"] == 45.0
    assert exposure["W"] == 0.0


def test_isruc_scorers_remain_independent_for_candidate_assignment():
    scorer_one = [
        {"start_seconds": 0.0, "duration_seconds": 30.0, "raw_label": "2", "normalized_label": "N2"}
    ]
    scorer_two = [
        {"start_seconds": 0.0, "duration_seconds": 30.0, "raw_label": "3", "normalized_label": "N3"}
    ]
    first = assign_event_stage(12.0, scorer_one, unknown_label="UNKNOWN")
    second = assign_event_stage(12.0, scorer_two, unknown_label="UNKNOWN")
    assert (first["raw_label"], first["normalized_label"]) == ("2", "N2")
    assert (second["raw_label"], second["normalized_label"]) == ("3", "N3")


def test_qc_sampling_is_seeded_stratified_and_controls_avoid_candidates():
    items = [
        {"id": f"{stage}-{index}", "stage": stage, "class": agreement}
        for stage in ("W", "N2", "REM")
        for agreement in ("matched", "only")
        for index in range(4)
    ]
    kwargs = {
        "target": 12,
        "seed": 42,
        "stratum": lambda row: (row["stage"], row["class"]),
        "identity": lambda row: row["id"],
    }
    first = deterministic_stratified_sample(items, **kwargs)
    second = deterministic_stratified_sample(list(reversed(items)), **kwargs)
    assert first == second
    assert {row["stage"] for row in first} == {"W", "N2", "REM"}
    assert {row["class"] for row in first} == {"matched", "only"}

    controls = build_control_sample(
        [{"start_seconds": 0.0, "duration_seconds": 100.0, "normalized_label": "N2"}],
        [25.0, 75.0],
        dataset_id="dataset",
        stage="N2",
        target=10,
        seed=7,
        window_s=10.0,
        exclusion_s=5.0,
        minimum_separation_s=10.0,
    )
    assert controls == build_control_sample(
        [{"start_seconds": 0.0, "duration_seconds": 100.0, "normalized_label": "N2"}],
        [25.0, 75.0],
        dataset_id="dataset",
        stage="N2",
        target=10,
        seed=7,
        window_s=10.0,
        exclusion_s=5.0,
        minimum_separation_s=10.0,
    )
    assert all(abs(row["center_s"] - event) > 10.0 for row in controls for event in (25.0, 75.0))


def test_human_review_save_reload_update_preserves_uncertain_and_notes(tmp_path: Path):
    sample = {
        "review_id": "candidate:test:001",
        "sample_kind": "candidate",
        "candidate_id": "candidate-1",
        "dataset_id": "dataset",
        "subject_id": "subject",
        "recording_id": "recording",
        "source_channel": "EOG",
        "timestamp": "12.5",
        "confidence": "0.7",
        "amplitude_uv": "22.0",
        "normalized_stage": "N2",
    }
    config = {
        "review_schema_version": "review.v1",
        "maximum_notes_characters": 100,
        "candidate_labels": [
            "Likely Eye Movement",
            "Artifact / Non-eye-movement",
            "Uncertain",
        ],
        "control_labels": [
            "No obvious eye movement",
            "Possible missed eye movement",
            "Artifact / unusable",
            "Uncertain",
        ],
    }
    database = tmp_path / "reviews.sqlite"
    export = tmp_path / "human_reviews.csv"
    store = HumanReviewStore(database, export, [sample], config)
    store.save(sample["review_id"], "Uncertain", "needs second review")

    reloaded = HumanReviewStore(database, export, [sample], config)
    assert reloaded.list()[0]["review_label"] == "Uncertain"
    assert reloaded.list()[0]["notes"] == "needs second review"
    reloaded.save(sample["review_id"], "Likely Eye Movement", "updated")
    assert len(reloaded.list()) == 1
    assert reloaded.list()[0]["notes"] == "updated"
    assert "raw" not in export.read_text(encoding="utf-8").casefold()

    try:
        reloaded.save(sample["review_id"], "True REM", "")
    except ReviewValidationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unsupported clinical label was accepted")
