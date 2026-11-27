"""Tests for flat-field recalculation window selection and median calculation."""

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from planktoscope.segmenter import SegmenterProcess


class _FakeMqttClient:
    def publish(self, topic: str, payload: str) -> None:
        pass


class _FakeSegmenterClient:
    def __init__(self) -> None:
        self.client = _FakeMqttClient()

    def new_message_received(self) -> bool:
        return False


def _write_constant_image(path: Path, value: int) -> None:
    img = np.full((8, 8, 3), value, dtype=np.uint8)
    assert cv2.imwrite(str(path), img)


def _make_segmenter_for_pipe(tmp_path: Path, n_images: int, spike_frame: int) -> Any:
    """Create a SegmenterProcess wired to a temp directory of synthetic images.

    Avoids MQTT/filesystem side effects in __init__ and overrides the per-frame
    segmentation stages so _pipe() exercises flat-field recalculation directly.
    """
    img_root = tmp_path / "img"
    working_dir = img_root / "run1"
    working_dir.mkdir(parents=True)
    for k in range(n_images):
        _write_constant_image(working_dir / f"img_{k:03d}.jpg", 100 + (k % 5))

    seg: Any = SegmenterProcess.__new__(SegmenterProcess)
    seg.segmenter_client = _FakeSegmenterClient()
    seg._interrupt_requested = False
    seg._SegmenterProcess__working_path = str(working_dir)
    seg._SegmenterProcess__img_path = str(img_root)
    seg._SegmenterProcess__debug_objects_root = str(tmp_path / "debug")
    seg._SegmenterProcess__save_debug_img = False
    seg._SegmenterProcess__working_ecotaxa_path = str(tmp_path / "export")
    seg._SegmenterProcess__working_objects_root = str(tmp_path / "objects")
    seg._SegmenterProcess__working_archive_path = str(tmp_path / "archive.zip")

    flat_calls: list[list[str]] = []
    orig_calc_flat = seg._calculate_flat

    def tracking_calc_flat(images_list: list[str], images_number: int, root_path: str) -> Any:
        flat_calls.append(list(images_list))
        return orig_calc_flat(images_list, images_number, root_path)

    seg._calculate_flat = tracking_calc_flat
    seg._open_and_apply_flat = lambda filepath, flat_ref: np.zeros((8, 8, 3), dtype=np.uint8)
    seg._create_mask = lambda img, debug_path: np.zeros((8, 8), dtype=np.uint8)

    frame_counter = {"n": 0}

    def fake_slice_image(img: Any, name: str, mask: Any, total: int) -> tuple[int, int]:
        idx = frame_counter["n"]
        frame_counter["n"] += 1
        # Trigger recalculate_flat on the requested frame (objects_count > average + 20)
        return (50 if idx == spike_frame else 5), 0

    seg._slice_image = fake_slice_image
    return seg, flat_calls


class TestPipeFlatRecalculation:
    @pytest.mark.parametrize(
        "n_images,spike_frame",
        [
            (15, 4),  # i=5 triggers len-11 branch with negative start i-10=-5 -> []
            (15, 6),  # i=7 triggers negative start i-10=-3 -> []
            (11, 2),  # i=3 triggers negative start i-10=-7 -> []
            (19, 8),  # i=9 triggers negative start i-10=-1 -> []
        ],
    )
    def test_mid_length_acquisition_recalculates_flat_without_crashing(
        self, tmp_path: Path, n_images: int, spike_frame: int
    ) -> None:
        seg, flat_calls = _make_segmenter_for_pipe(tmp_path, n_images, spike_frame)
        seg._pipe(ecotaxa_export=False)
        assert len(flat_calls) >= 2
        # Every recalculated flat window must use 10 distinct frames (not empty [])
        for window in flat_calls[1:]:
            assert len(window) == 10
            assert len(set(window)) == 10

    @pytest.mark.parametrize("n_images,spike_frame", [(9, 4), (8, 3), (5, 2)])
    def test_short_acquisition_below_ten_uses_all_frames_on_recalculation(
        self, tmp_path: Path, n_images: int, spike_frame: int
    ) -> None:
        seg, flat_calls = _make_segmenter_for_pipe(tmp_path, n_images, spike_frame)
        seg._pipe(ecotaxa_export=False)
        assert len(flat_calls) >= 2
        for window in flat_calls[1:]:
            assert len(window) == n_images


class TestCalculateFlat:
    def test_even_short_list_clamps_to_odd_frame_count(self, tmp_path: Path) -> None:
        # 4 images with pixel values [10, 20, 30, 200]: clamping to odd count (3)
        # takes the median of [10, 20, 30] = 20, not index 2 of 4 = 30.
        filenames = []
        for idx, value in enumerate([10, 20, 30, 200]):
            name = f"img_{idx:03d}.png"
            _write_constant_image(tmp_path / name, value)
            filenames.append(name)

        seg: Any = SegmenterProcess.__new__(SegmenterProcess)
        flat = seg._calculate_flat(filenames, 10, str(tmp_path))
        assert flat.shape == (8, 8, 3)
        assert int(flat[0, 0, 0]) == 20

    def test_single_image_list_succeeds(self, tmp_path: Path) -> None:
        name = "img_000.png"
        _write_constant_image(tmp_path / name, 42)
        seg: Any = SegmenterProcess.__new__(SegmenterProcess)
        flat = seg._calculate_flat([name], 10, str(tmp_path))
        assert int(flat[0, 0, 0]) == 42

    def test_empty_image_list_raises_value_error(self, tmp_path: Path) -> None:
        seg: Any = SegmenterProcess.__new__(SegmenterProcess)
        with pytest.raises(ValueError):
            seg._calculate_flat([], 10, str(tmp_path))
