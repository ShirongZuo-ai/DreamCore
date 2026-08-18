"""Deterministic signals for algorithm validation, not clinical simulation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AlphaSyntheticCase:
    case_id: str
    family: str
    seed: int
    snr_db: float | None
    injected_frequency_hz: float | None
    injected_amplitude_uv: float
    samples_uv: np.ndarray


@dataclass(frozen=True)
class CrossTalkCase:
    case_id: str
    family: str
    seed: int
    level: float
    eeg_posterior_uv: np.ndarray
    eeg_frontal_uv: np.ndarray
    eog_uv: np.ndarray
    true_alpha: bool
    true_k_complex: bool
    true_eog: bool


def colored_background(
    sample_count: int, sampling_rate_hz: float, rms_uv: float, seed: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    white = rng.normal(size=sample_count)
    spectrum = np.fft.rfft(white)
    frequencies = np.fft.rfftfreq(sample_count, d=1.0 / sampling_rate_hz)
    shaping = np.ones_like(frequencies)
    shaping[1:] = 1.0 / np.sqrt(frequencies[1:])
    shaped = np.fft.irfft(spectrum * shaping, n=sample_count)
    shaped -= np.mean(shaped)
    standard_deviation = np.std(shaped)
    return shaped * (rms_uv / standard_deviation) if standard_deviation else shaped


def _oscillation(
    times: np.ndarray, frequency_hz: float, amplitude_uv: float | np.ndarray
) -> np.ndarray:
    return np.asarray(amplitude_uv) * np.sin(2.0 * np.pi * frequency_hz * times)


def _biphasic(
    times: np.ndarray,
    center_s: float,
    negative_uv: float,
    positive_uv: float,
    width_s: float,
) -> np.ndarray:
    negative = negative_uv * np.exp(-0.5 * ((times - center_s) / width_s) ** 2)
    positive = positive_uv * np.exp(
        -0.5 * ((times - center_s - width_s * 2.5) / (width_s * 1.4)) ** 2
    )
    return negative + positive


def alpha_cases(config: Mapping[str, object]) -> tuple[AlphaSyntheticCase, ...]:
    rate = float(config["sampling_rate_hz"])
    duration = float(config["duration_s"])
    sample_count = int(round(rate * duration))
    times = np.arange(sample_count, dtype=float) / rate
    background_rms = float(config["background_rms_uv"])
    stationary = float(config["stationary_amplitude_uv"])
    reference_frequency = float(config["reference_frequency_hz"])
    output = []
    for seed in config["seeds"]:
        seed = int(seed)
        for frequency in config["frequencies_hz"]:
            for snr in config["snr_db"]:
                frequency = float(frequency)
                snr = float(snr)
                noise_rms = stationary / np.sqrt(2.0) / (10.0 ** (snr / 20.0))
                signal = colored_background(sample_count, rate, noise_rms, seed)
                signal += _oscillation(times, frequency, stationary)
                output.append(
                    AlphaSyntheticCase(
                        f"stationary-{frequency:g}hz-{snr:g}db-{seed}",
                        "stationary_alpha",
                        seed,
                        snr,
                        frequency,
                        stationary,
                        signal,
                    )
                )
        for control_index in range(int(config["no_alpha_controls_per_seed"])):
            output.append(
                AlphaSyntheticCase(
                    f"no-alpha-{seed}-{control_index + 1}",
                    "no_alpha",
                    seed,
                    None,
                    None,
                    0.0,
                    colored_background(
                        sample_count,
                        rate,
                        background_rms,
                        seed + 10_000 + control_index,
                    ),
                )
            )
        for amplitude in config["amplitude_levels_uv"]:
            amplitude = float(amplitude)
            signal = colored_background(sample_count, rate, background_rms, seed + 20_000)
            signal += _oscillation(times, reference_frequency, amplitude)
            output.append(
                AlphaSyntheticCase(
                    f"amplitude-{amplitude:g}uv-{seed}",
                    "amplitude_ordering",
                    seed,
                    None,
                    reference_frequency,
                    amplitude,
                    signal,
                )
            )
        amplitude = np.linspace(
            float(config["ramp_start_uv"]), float(config["ramp_end_uv"]), sample_count
        )
        ramp = colored_background(sample_count, rate, background_rms, seed + 30_000)
        ramp += _oscillation(times, reference_frequency, amplitude)
        output.append(
            AlphaSyntheticCase(
                f"amplitude-ramp-{seed}",
                "amplitude_ramp",
                seed,
                None,
                reference_frequency,
                float(np.mean(amplitude)),
                ramp,
            )
        )
        transient = colored_background(sample_count, rate, background_rms, seed + 40_000)
        transient += _oscillation(times, reference_frequency, stationary)
        transient += _biphasic(
            times,
            float(config["transient_center_s"]),
            float(config["transient_negative_uv"]),
            float(config["transient_positive_uv"]),
            float(config["transient_width_s"]),
        )
        output.append(
            AlphaSyntheticCase(
                f"alpha-plus-slow-transient-{seed}",
                "alpha_plus_slow_transient",
                seed,
                None,
                reference_frequency,
                stationary,
                transient,
            )
        )
    return tuple(output)


def cross_talk_cases(config: Mapping[str, object]) -> tuple[CrossTalkCase, ...]:
    rate = float(config["sampling_rate_hz"])
    sample_count = int(round(rate * float(config["duration_s"])))
    times = np.arange(sample_count, dtype=float) / rate
    output = []
    for seed in config["seeds"]:
        for level in config["levels"]:
            seed = int(seed)
            level = float(level)
            base = colored_background(sample_count, rate, float(config["background_rms_uv"]), seed)
            alpha = _oscillation(
                times,
                float(config["alpha_frequency_hz"]),
                float(config["alpha_amplitude_uv"]) * level,
            )
            kc = _biphasic(
                times,
                float(config["k_complex_time_s"]),
                float(config["k_complex_negative_uv"]) * level,
                float(config["k_complex_positive_uv"]) * level,
                float(config["k_complex_width_s"]),
            )
            eog = _biphasic(
                times,
                float(config["eog_time_s"]),
                -float(config["eog_amplitude_uv"]) * level,
                float(config["eog_amplitude_uv"]) * 0.8 * level,
                float(config["eog_width_s"]),
            )
            for family in config["cases"]:
                family = str(family)
                true_alpha = family in {
                    "alpha_only",
                    "alpha_plus_k_complex",
                    "alpha_plus_ocular_leakage",
                }
                true_kc = family in {"k_complex_only", "alpha_plus_k_complex", "k_complex_plus_eog"}
                true_eog = family in {"eog_only", "alpha_plus_ocular_leakage", "k_complex_plus_eog"}
                posterior = base.copy() + (alpha if true_alpha else 0.0) + (kc if true_kc else 0.0)
                eog_signal = base.copy() + (eog if true_eog else 0.0)
                frontal = base.copy() + (kc if true_kc else 0.0)
                if family == "alpha_plus_ocular_leakage":
                    frontal += eog * float(config["ocular_leakage_fraction"])
                output.append(
                    CrossTalkCase(
                        f"{family}-{level:g}-{seed}",
                        family,
                        seed,
                        level,
                        posterior,
                        frontal,
                        eog_signal,
                        true_alpha,
                        true_kc,
                        true_eog,
                    )
                )
    return tuple(output)
