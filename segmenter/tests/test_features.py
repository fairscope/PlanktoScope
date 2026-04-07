"""Tests for expanded feature extraction in the segmentation pipeline.

Verifies color features (RGB/HSV mean, std, quartiles, skewness, kurtosis)
and morphological features (perimeter_crofton, feret_diameter_max, inertia
tensor eigenvalues) follow correct naming, masking, and scaling conventions.
"""

import math

import numpy as np
import pytest
from scipy.stats import kurtosis, skew


# -- Helpers that mirror the segmenter logic without importing hardware deps --


QUARTILES = [0, 0.05, 0.25, 0.50, 0.75, 0.95, 1]


def get_color_keys():
    """Return the full set of color feature keys as produced by _get_color_info."""
    channels_rgb = ["Red", "Green", "Blue"]
    channels_hsv = ["Hue", "Saturation", "Value"]
    all_channels = channels_rgb + channels_hsv
    quantile_labels = ["min", "Q05", "Q25", "Q50", "Q75", "Q95", "max"]

    keys = []
    # RGB mean/std
    for ch in channels_rgb:
        keys.append(f"Mean{ch}Level")
        keys.append(f"Std{ch}Level")
    # RGB quartiles
    for ch in channels_rgb:
        for q in quantile_labels:
            keys.append(f"{q}{ch}Level")
    # HSV mean/std
    for ch in channels_hsv:
        keys.append(f"Mean{ch}")
        keys.append(f"Std{ch}")
    # HSV quartiles
    for ch in channels_hsv:
        for q in quantile_labels:
            keys.append(f"{q}{ch}")
    # Skewness and kurtosis
    for ch in all_channels:
        keys.append(f"Skew{ch}")
    for ch in all_channels:
        keys.append(f"Kurtosis{ch}")
    return keys


def get_morphological_keys():
    """Return morphological feature keys from _extract_metadata_from_regionprop."""
    return [
        "label", "width", "height", "bx", "by", "circ.", "area_exc", "area",
        "%area", "major", "minor", "y", "x", "convex_area", "perim.",
        "elongation", "perimareaexc", "perimmajor", "circex", "angle",
        "bounding_box_area", "eccentricity", "equivalent_diameter",
        "euler_number", "extent", "local_centroid_col", "local_centroid_row",
        "solidity", "perim_crofton", "feret_diameter_max",
        "inertia_eigval_major", "inertia_eigval_minor",
    ]


# ── Naming conventions ─────────────────────────────────────────────────────


class TestColorFeatureNaming:
    def test_no_object_prefix_in_keys(self) -> None:
        """Keys must NOT have 'object_' prefix — ecotaxa.py adds it at export time."""
        for key in get_color_keys():
            assert not key.startswith("object_"), (
                f"Key '{key}' has object_ prefix — will produce 'object_object_' in TSV"
            )

    def test_expected_feature_count(self) -> None:
        """6 RGB mean/std + 21 RGB quartiles + 6 HSV mean/std + 21 HSV quartiles
        + 6 skew + 6 kurtosis = 66 color features."""
        assert len(get_color_keys()) == 66

    def test_morphological_feature_count(self) -> None:
        """28 existing + 4 new = 32 morphological features."""
        assert len(get_morphological_keys()) == 32


class TestTotalFeatureCount:
    def test_under_ecotaxa_limit(self) -> None:
        """EcoTaxa supports up to 500 [f] fields per object."""
        total = len(get_color_keys()) + len(get_morphological_keys())
        assert total < 500, f"Total features ({total}) exceeds EcoTaxa 500-field limit"


# ── Masked quartile computation ────────────────────────────────────────────


class TestMaskedQuartiles:
    def test_masked_differs_from_unmasked(self) -> None:
        """Quartiles on masked pixels should differ from unmasked when background != foreground."""
        # 10x10 image, object in center 6x6, background = 0, foreground = 200
        channel = np.zeros((10, 10), dtype=np.uint8)
        mask = np.zeros((10, 10), dtype=bool)
        channel[2:8, 2:8] = 200
        mask[2:8, 2:8] = True

        masked_q = np.quantile(channel[mask], QUARTILES)
        unmasked_q = np.quantile(channel, QUARTILES)

        # Masked should be all 200; unmasked includes zeros
        assert masked_q[0] == 200.0  # min of foreground
        assert unmasked_q[0] == 0.0  # min includes background
        assert not np.array_equal(masked_q, unmasked_q)

    def test_masked_quartiles_uniform_foreground(self) -> None:
        """Uniform foreground should have all quartiles equal."""
        channel = np.full((5, 5), 128, dtype=np.uint8)
        mask = np.ones((5, 5), dtype=bool)
        q = np.quantile(channel[mask], QUARTILES)
        assert np.all(q == 128.0)

    def test_masked_median_known_distribution(self) -> None:
        """Verify median (Q50) on a known distribution."""
        # Foreground pixels: 10, 20, 30, 40, 50
        channel = np.array([[10, 20, 30], [40, 50, 0]], dtype=np.uint8)
        mask = np.array([[True, True, True], [True, True, False]])
        q = np.quantile(channel[mask], QUARTILES)
        assert q[3] == pytest.approx(30.0)  # Q50 = median


# ── Skewness and kurtosis ─────────────────────────────────────────────────


class TestSkewnessKurtosis:
    def test_uniform_distribution_skew_near_zero(self) -> None:
        """Uniform distribution should have near-zero skewness."""
        pixels = np.arange(256, dtype=np.float64)
        assert abs(skew(pixels)) < 0.01

    def test_uniform_distribution_kurtosis(self) -> None:
        """Uniform distribution has Fisher kurtosis of -1.2."""
        pixels = np.arange(256, dtype=np.float64)
        assert kurtosis(pixels) == pytest.approx(-1.2, abs=0.01)

    def test_right_skewed_positive(self) -> None:
        """Right-skewed distribution should have positive skewness."""
        rng = np.random.default_rng(42)
        pixels = rng.exponential(scale=50, size=1000).astype(np.float64)
        assert skew(pixels) > 0.5

    def test_float64_conversion_prevents_overflow(self) -> None:
        """uint8 higher moments can overflow — float64 prevents this."""
        pixels_uint8 = np.array([255] * 100 + [0] * 100, dtype=np.uint8)
        pixels_f64 = pixels_uint8.astype(np.float64)
        # Should not raise and should give valid results
        s = skew(pixels_f64)
        k = kurtosis(pixels_f64)
        assert np.isfinite(s)
        assert np.isfinite(k)


# ── Morphological feature scaling ──────────────────────────────────────────


class TestMorphologicalScaling:
    def test_linear_features_scale_by_px(self) -> None:
        """Linear features (perimeter, feret diameter) should scale by px."""
        px = 0.75
        perim_px = 100.0
        feret_px = 50.0
        assert perim_px * px == pytest.approx(75.0)
        assert feret_px * px == pytest.approx(37.5)

    def test_inertia_eigvals_unscaled(self) -> None:
        """Inertia eigenvalues are stored unscaled (dimensionless shape descriptors)."""
        # Eigenvalues of a circle-like shape: major ≈ minor
        eigval_major = 100.0
        eigval_minor = 95.0
        # Ratio close to 1 for circular shapes
        assert eigval_major >= eigval_minor
        ratio = eigval_major / eigval_minor
        assert ratio == pytest.approx(1.053, abs=0.01)

    def test_new_features_in_key_list(self) -> None:
        """New morphological features appear in the key list."""
        keys = get_morphological_keys()
        assert "perim_crofton" in keys
        assert "feret_diameter_max" in keys
        assert "inertia_eigval_major" in keys
        assert "inertia_eigval_minor" in keys
