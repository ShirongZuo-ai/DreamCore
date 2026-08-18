"""Candidate labels that preserve expert availability and disagreement."""

from __future__ import annotations


def label_candidate(candidate, expert_1, expert_2, *, exclusion_margin_s: float):
    start = float(candidate["onset_s"])
    end = float(candidate["end_s"])

    def overlaps(events):
        return any(start < float(item["end_s"]) and end > float(item["onset_s"]) for item in events)

    def near(events):
        return any(
            start < float(item["end_s"]) + exclusion_margin_s
            and end > float(item["onset_s"]) - exclusion_margin_s
            for item in events
        )

    first = overlaps(expert_1)
    if expert_2 is None:
        if first:
            return "single_expert_positive"
        return "single_expert_unmatched" if not near(expert_1) else "ambiguous"
    second = overlaps(expert_2)
    if first and second:
        return "high_confidence_positive"
    if first != second:
        return "single_expert_positive"
    if near(expert_1) or near(expert_2):
        return "ambiguous"
    return "high_confidence_negative"


def leave_one_recording_out(recording_ids):
    groups = tuple(dict.fromkeys(recording_ids))
    return tuple(
        {
            "test_recordings": (held_out,),
            "train_recordings": tuple(group for group in groups if group != held_out),
        }
        for held_out in groups
    )
