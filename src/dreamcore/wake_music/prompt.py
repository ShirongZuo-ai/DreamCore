"""Structured, reproducible MiniMax prompt construction."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from dreamcore.wake_music.profile import PromptConfiguration, WakeMusicProfile


def build_prompt(profile: WakeMusicProfile, config: Mapping[str, Any]) -> PromptConfiguration:
    styles = config["styles"]
    phrases = config["prompt_phrases"]
    style = styles[profile.music.style_family]
    variants = tuple(str(item) for item in style["variants"])
    variation_index = profile.generation_seed % len(variants)
    variation = variants[variation_index]
    prompt = "\n\n".join(
        (
            "Create an instrumental morning wake-up piece.",
            "No vocals, singing, spoken words, or lyrics. Do not generate or infer lyrics.",
            f"Style:\n{style['description']} Arrangement variant: {variation}.",
            (
                "Overall mood:\nGentle, pleasant, coherent, fresh, clear, and uplifting. "
                "Never aggressive, harsh, intense, dark, or frightening."
            ),
            f"Melodic register:\n{phrases['register'][profile.music.register]}",
            (
                "Melodic activity:\n"
                f"{phrases['density'][profile.music.density]} Avoid sudden loud transients."
            ),
            f"Brightness:\n{phrases['brightness'][profile.music.brightness]}",
            (
                "Expression and energy:\n"
                f"{phrases['expression'][profile.music.expressive_strength]} "
                f"Energy must remain at or below {profile.constraints.max_energy}. "
                "No dramatic climax or extreme crescendo."
            ),
            (
                "Percussion:\nNone or extremely subtle, always at or below "
                f"{profile.constraints.max_percussiveness}. No intense drums, EDM drops, "
                "aggressive trap rhythms, or very heavy bass."
            ),
            (
                "Arrangement:\nMaintain coherent musical development. Introduce a noticeable "
                "but smooth variation in melody, harmonic texture, and instrument balance. "
                "Keep the tempo slow to moderate and the morning character comfortable."
            ),
            f"Ending:\n{phrases['ending'][profile.music.energy_curve]}",
        )
    )
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    return PromptConfiguration(
        prompt=prompt,
        prompt_hash=prompt_hash,
        style_family=profile.music.style_family,
        style_label=profile.music.style_label,
        variation_id=profile.variation_id,
        variation_description=variation,
        generation_seed=profile.generation_seed,
    )
