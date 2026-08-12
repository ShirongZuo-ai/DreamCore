"""Minimal import test — ensures the dreamcore package loads correctly."""

from pathlib import Path

import yaml


def test_package_imports():
    """Verify all dreamcore submodules can be imported."""
    import dreamcore
    from dreamcore import (
        data,
        evaluation,
        phase_prediction,
        precision_gating,
        preprocessing,
        simulation,
        sleep_staging,
        slow_oscillation,
    )

    assert dreamcore.__version__ == "0.1.0"

    # All submodules should exist (no ImportError raised)
    assert data is not None
    assert preprocessing is not None
    assert sleep_staging is not None
    assert slow_oscillation is not None
    assert phase_prediction is not None
    assert precision_gating is not None
    assert simulation is not None
    assert evaluation is not None


def test_config_loads():
    """Verify default config is valid YAML and has expected top-level keys."""
    config_path = Path(__file__).parent.parent / "configs" / "default.yaml"
    assert config_path.exists(), f"Config not found: {config_path}"

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    expected_sections = [
        "general",
        "eeg",
        "data",
        "preprocessing",
        "sleep_staging",
        "n3_extraction",
        "slow_oscillation",
        "phase_prediction",
        "precision_gating",
        "simulation",
        "evaluation",
        "output",
    ]
    for section in expected_sections:
        assert section in cfg, f"Missing config section: {section}"


def test_numpy_scipy_mne_available():
    """Verify core scientific dependencies are importable."""
    import matplotlib
    import numpy
    import pandas
    import scipy

    # Check we have these available — version constraints handled by pip
    assert numpy is not None
    assert scipy is not None
    assert pandas is not None
    assert matplotlib is not None
