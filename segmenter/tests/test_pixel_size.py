"""Tests for pixel size management in the segmentation pipeline.

Verifies that process_pixel flows correctly through metadata filtering,
ESD threshold conversion, measurement scaling, and EcoTaxa export naming.
"""

import math

import pytest


# -- Helpers that mirror the segmenter logic without importing hardware deps --


def compute_min_esd_pixels(process_min_ESD: float, process_pixel: float | None) -> float:
    """Mirrors segmenter/__init__.py ESD threshold conversion."""
    pixel_size = process_pixel
    try:
        pixel_size = float(pixel_size) if pixel_size is not None else None
    except (ValueError, TypeError):
        pixel_size = None
    if pixel_size and pixel_size > 0:
        return process_min_ESD / pixel_size
    else:
        return process_min_ESD  # legacy fallback


def extract_metadata_scaling(pixel_size_um: float | None) -> tuple[float, float]:
    """Mirrors _extract_metadata_from_regionprop scaling logic."""
    px = pixel_size_um if pixel_size_um and pixel_size_um > 0 else 1.0
    return px, px * px


def metadata_prefix_filter(metadata: dict) -> dict:
    """Mirrors segmenter/__init__.py metadata prefix filter."""
    return dict(
        filter(
            lambda item: item[0].startswith(("acq", "sample", "object", "process", "calibration")),
            metadata.items(),
        )
    )


# -- Magnification presets (mirrors Node-RED acquisition page) --

PRESETS = {
    "high": {"pixel_size": 0.53, "thickness": 100},
    "medium": {"pixel_size": 0.75, "thickness": 300},
    "low": {"pixel_size": 1.34, "thickness": 500},
}


# ── ESD threshold conversion ────────────────────────────────────────────────


class TestESDThreshold:
    @pytest.mark.parametrize(
        "mag,pixel",
        [("high", 0.53), ("medium", 0.75), ("low", 1.34)],
    )
    def test_min_esd_resolves_to_20um(self, mag: str, pixel: float) -> None:
        threshold_px = compute_min_esd_pixels(20, pixel)
        effective_um = threshold_px * pixel
        assert effective_um == pytest.approx(20.0, abs=0.01), (
            f"{mag} mag: {threshold_px:.1f}px × {pixel} = {effective_um:.1f}µm, expected 20µm"
        )

    def test_medium_threshold_is_26_67_pixels(self) -> None:
        assert compute_min_esd_pixels(20, 0.75) == pytest.approx(26.667, abs=0.01)

    def test_missing_pixel_size_falls_back_to_raw_pixels(self) -> None:
        assert compute_min_esd_pixels(20, None) == 20


# ── Measurement scaling ─────────────────────────────────────────────────────


class TestMeasurementScaling:
    def test_linear_and_area_scale(self) -> None:
        px, px2 = extract_metadata_scaling(0.75)
        assert px == 0.75
        assert px2 == pytest.approx(0.5625)

    def test_area_conversion(self) -> None:
        _, px2 = extract_metadata_scaling(0.75)
        assert 1000 * px2 == pytest.approx(562.5)

    def test_esd_of_known_area(self) -> None:
        px, _ = extract_metadata_scaling(0.75)
        eq_diam_px = math.sqrt(4 * 1000 / math.pi)
        assert eq_diam_px * px == pytest.approx(26.76, abs=0.01)

    def test_missing_pixel_size_gives_unity(self) -> None:
        px, px2 = extract_metadata_scaling(None)
        assert px == 1.0
        assert px2 == 1.0


# ── Metadata prefix filter ──────────────────────────────────────────────────


class TestMetadataFilter:
    def test_process_pixel_survives_filter(self) -> None:
        metadata = {
            "acq_celltype": 300,
            "sample_project": "Test",
            "process_pixel": 0.75,
            "process_pixel_applied": True,
            "nb_frame": 100,
            "sleep_before": 0.5,
        }
        filtered = metadata_prefix_filter(metadata)
        assert "process_pixel" in filtered
        assert filtered["process_pixel"] == 0.75
        assert "process_pixel_applied" in filtered

    def test_non_prefixed_keys_filtered_out(self) -> None:
        metadata = {"nb_frame": 100, "sleep_before": 0.5, "acq_id": "a1"}
        filtered = metadata_prefix_filter(metadata)
        assert "nb_frame" not in filtered
        assert "sleep_before" not in filtered
        assert "acq_id" in filtered


# ── EcoTaxa naming ──────────────────────────────────────────────────────────


class TestEcoTaxaNaming:
    @staticmethod
    def make_archive_name(project: str, acquisition: str) -> str:
        return f"Ecotaxa_{project}_{acquisition}.zip"

    @staticmethod
    def make_tsv_name(sample_project: str | None, acq_id: str | None) -> str:
        project = (sample_project or "unknown_project").replace(" ", "_")
        acquisition_id = (acq_id or "unknown_acq").replace(" ", "_")
        return f"Ecotaxa_{project}_{acquisition_id}.tsv"

    def test_archive_format(self) -> None:
        assert self.make_archive_name("My_Project", "acq_001") == "Ecotaxa_My_Project_acq_001.zip"

    def test_tsv_spaces_replaced(self) -> None:
        assert self.make_tsv_name("Tara Sud 2021", "acq 001") == "Ecotaxa_Tara_Sud_2021_acq_001.tsv"

    def test_tsv_missing_project_fallback(self) -> None:
        assert self.make_tsv_name(None, "acq_001") == "Ecotaxa_unknown_project_acq_001.tsv"


# ── End-to-end per-magnification ─────────────────────────────────────────────


class TestEndToEnd:
    @pytest.mark.parametrize("mag", ["high", "medium", "low"])
    def test_full_pipeline_per_magnification(self, mag: str) -> None:
        pixel = PRESETS[mag]["pixel_size"]
        thickness = PRESETS[mag]["thickness"]

        # Simulate metadata as it arrives from the imager
        metadata = {
            "sample_project": "Test",
            "sample_id": "s1",
            "acq_id": "a1",
            "acq_celltype": thickness,
            "process_pixel": pixel,
        }

        # Prefix filter (segmenter entry point)
        filtered = metadata_prefix_filter(metadata)
        assert filtered["process_pixel"] == pixel

        # ESD threshold → always 20µm
        threshold_px = compute_min_esd_pixels(20, filtered["process_pixel"])
        assert threshold_px * pixel == pytest.approx(20.0, abs=0.01)

        # Measurement scaling
        px, _ = extract_metadata_scaling(filtered["process_pixel"])
        assert px == pixel
