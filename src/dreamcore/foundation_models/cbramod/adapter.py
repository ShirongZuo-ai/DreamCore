"""Config-driven EEG-to-CBraMod tensor adapter."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt


@dataclass(frozen=True)
class PreparedEEG:
    values: np.ndarray
    channels: tuple[str, ...]
    original_sampling_rate_hz: float
    model_sampling_rate_hz: float
    unit: str
    reference: str | None
    dataset_id: str


class CBraModAdapter:
    def __init__(self, config):
        self.config = config

    def prepare(
        self,
        signal,
        sampling_rate: float,
        channels,
        *,
        unit: str,
        reference: str | None,
        dataset_id: str,
    ) -> PreparedEEG:
        values = np.asarray(signal, dtype=np.float64)
        if values.ndim == 1:
            values = values[None, :]
        names = tuple(str(name) for name in channels)
        if values.ndim != 2 or values.shape[0] != len(names) or not names:
            raise ValueError("signal must have shape (channels, samples) with original names")
        if not np.isfinite(values).all():
            raise ValueError("CBraMod input contains non-finite samples")
        normalized_unit = unit.replace("µ", "u").replace("μ", "u").casefold()
        if normalized_unit == "v":
            values = values * float(self.config["volts_to_microvolts"])
        elif normalized_unit != "uv":
            raise ValueError(f"Unsupported EEG unit: {unit}")
        target = float(self.config["model_sampling_rate_hz"])
        source = float(sampling_rate)
        if source <= 0:
            raise ValueError("sampling_rate must be positive")
        if source != target:
            from fractions import Fraction

            ratio = Fraction(target / source).limit_denominator(
                int(self.config["resampling_max_denominator"])
            )
            values = resample_poly(values, ratio.numerator, ratio.denominator, axis=-1)
        filtering = self.config["filtering"]
        nyquist = target / 2.0
        high = min(float(filtering["high_hz"]), nyquist * float(filtering["nyquist_guard"]))
        sos = butter(
            int(filtering["order"]),
            [float(filtering["low_hz"]) / nyquist, high / nyquist],
            btype="band",
            output="sos",
        )
        values = sosfiltfilt(sos, values, axis=-1)
        notch = float(filtering["notch_hz"])
        if notch < nyquist:
            from scipy.signal import iirnotch

            b, a = iirnotch(notch, float(filtering["notch_quality"]), fs=target)
            from scipy.signal import filtfilt

            values = filtfilt(b, a, values, axis=-1)
        patch_points = int(self.config["architecture"]["patch_points"])
        complete = values.shape[-1] // patch_points
        if complete < 1:
            raise ValueError("EEG window is shorter than one CBraMod patch")
        tensor = values[..., : complete * patch_points].reshape(
            values.shape[0], complete, patch_points
        )
        return PreparedEEG(
            tensor.astype(np.float32, copy=False),
            names,
            source,
            target,
            "uV",
            reference,
            dataset_id,
        )

    def encode_eeg(self, signal, sampling_rate, channels, **metadata) -> np.ndarray:
        import torch

        from dreamcore.foundation_models.cbramod.checkpoint import load_frozen_model

        prepared = self.prepare(signal, sampling_rate, channels, **metadata)
        configured = str(self.config["device"])
        device = "cuda" if configured == "auto" and torch.cuda.is_available() else configured
        if device == "auto":
            device = "cpu"
        model = load_frozen_model(self.config["checkpoint_path"], self.config, device=device)
        tensor = torch.from_numpy(prepared.values[None]).to(device)
        with torch.inference_mode():
            features = model(tensor)
        return features.mean(dim=(1, 2)).cpu().numpy()[0]
