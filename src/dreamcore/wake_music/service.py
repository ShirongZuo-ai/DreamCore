"""Wake Music orchestration kept separate from read-only Session transport."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from dreamcore.datasets.registry import DatasetRegistry
from dreamcore.wake_music.mapping import (
    build_profile,
    manual_window,
    select_wake_window,
    summarize_physiology,
)
from dreamcore.wake_music.profile import GenerationRecord
from dreamcore.wake_music.prompt import build_prompt
from dreamcore.wake_music.provider import WakeMusicProvider
from dreamcore.wake_music.storage import WakeMusicStorage


class WakeMusicService:
    def __init__(
        self,
        registry: DatasetRegistry,
        config: Mapping[str, Any],
        provider: WakeMusicProvider,
        storage: WakeMusicStorage,
    ) -> None:
        self.registry = registry
        self.config = config
        self.provider = provider
        self.storage = storage

    def generate(
        self,
        *,
        session_id: str,
        style: str,
        seed: int,
        force_new: bool = False,
        window_start_s: float | None = None,
        window_end_s: float | None = None,
    ) -> GenerationRecord:
        profile = self.prepare_profile(
            session_id=session_id,
            style=style,
            seed=seed,
            window_start_s=window_start_s,
            window_end_s=window_end_s,
        )
        return self._generate_profile(profile, force_new=force_new)

    def prepare_profile(
        self,
        *,
        session_id: str,
        style: str,
        seed: int,
        window_start_s: float | None = None,
        window_end_s: float | None = None,
    ):
        """Build the local profile without invoking the music provider."""

        manifest = self.registry.get_session_by_id(session_id)
        if (window_start_s is None) is not (window_end_s is None):
            raise ValueError("manual window requires both window_start_s and window_end_s")
        if window_start_s is not None and window_end_s is not None:
            source_window = manual_window(
                window_start_s, window_end_s, manifest.recording.duration_seconds
            )
        else:
            annotations = self.registry.load_annotations(
                session_id, str(self.config["wake_window"]["annotation_type"])
            )
            source_window = select_wake_window(annotations, self.config["wake_window"])
        source_feature = str(self.config["source_feature_metric"])
        rows = self.registry.load_derived_window(
            session_id, source_feature, source_window.start_s, source_window.end_s
        )
        rows = tuple(
            row
            for row in rows
            if source_window.start_s
            < float(row.get("window_end_s", source_window.start_s))
            <= source_window.end_s
        )
        physiology = summarize_physiology(
            rows,
            source_feature,
            int(self.config["wake_window"]["minimum_feature_rows"]),
        )
        return build_profile(
            session_id=session_id,
            source_window=source_window,
            physiology=physiology,
            requested_style=style,
            generation_seed=seed,
            config=self.config,
        )

    def new_variation(self, *, generation_id: str, style: str | None = None) -> GenerationRecord:
        previous = self.get(generation_id)
        profile = build_profile(
            session_id=previous.session_id,
            source_window=previous.profile.source_window,
            physiology=previous.profile.physiology,
            requested_style=style or previous.profile.music.style_family,
            generation_seed=(previous.profile.generation_seed + int(self.config["seed_increment"])),
            config=self.config,
        )
        return self._generate_profile(profile, force_new=False)

    def _generate_profile(self, profile, *, force_new: bool) -> GenerationRecord:
        prompt = build_prompt(profile, self.config)
        cache_key = self.storage.cache_key(profile, prompt, self.provider.name, self.provider.model)
        if not force_new:
            cached = self.storage.lookup(profile.session_id, cache_key)
            if cached:
                return cached
        provider_result = self.provider.generate(prompt.prompt)
        generation_id = self.storage.generation_id(cache_key)
        return self.storage.save(
            generation_id=generation_id,
            cache_key=cache_key,
            profile=profile,
            prompt=prompt,
            provider_name=self.provider.name,
            model=self.provider.model,
            generated_at=datetime.now(UTC).isoformat(),
            provider_result=provider_result,
            audio_url_path=f"/api/wake-music/{generation_id}/audio",
        )

    def get(self, generation_id: str) -> GenerationRecord:
        return self.storage.get(generation_id)

    def latest(self, session_id: str) -> GenerationRecord | None:
        return self.storage.latest(session_id)
