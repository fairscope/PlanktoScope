# Copyright (C) 2021 Romain Bazile
#
# This file is part of the PlanktoScope software.
#
# PlanktoScope is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PlanktoScope is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PlanktoScope.  If not, see <http://www.gnu.org/licenses/>.

# Logger library compatible with multiprocessing
import cv2
import numpy as np
from loguru import logger

__mask_to_remove = None
__last_threshold_value = None


def get_last_threshold_value():
    """Return the threshold value from the most recent simple_threshold() call."""
    return __last_threshold_value


def adaptative_threshold(img):
    """Apply a threshold to a color image to get a mask from it
    Uses an adaptative threshold with a blocksize of 19 and reduction of 4.

    Args:
        img (cv2 img): Image to extract the mask from

    Returns:
        cv2 img: binary mask
    """
    # start = time.monotonic()
    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    logger.debug("Adaptative threshold calc")
    # img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # ret, mask = cv2.threshold(img_gray, 127, 200, cv2.THRESH_OTSU)
    mask = cv2.adaptiveThreshold(
        img_gray,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_MEAN_C,
        thresholdType=cv2.THRESH_BINARY_INV,
        blockSize=19,  # must be odd
        C=4,
    )
    # mask = 255 - img_tmaskhres

    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # logger.debug(time.monotonic() - start)
    # logger.success(f"Threshold used was {ret}")
    logger.success("Adaptative threshold is done")
    return mask


def simple_threshold(img):
    """Apply a threshold to a color image to get a mask from it

    Args:
        img (cv2 img): Image to extract the mask from

    Returns:
        cv2 img: binary mask
    """
    global __last_threshold_value

    logger.debug("Simple threshold calc")
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, mask = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_TRIANGLE)

    __last_threshold_value = float(ret)
    logger.info(f"Threshold value used was {ret}")
    logger.success("Simple threshold is done")
    return mask


def erode(mask):
    """Erode the given mask with a rectangular kernel of 2x2

    Args:
        mask (cv2 img): mask to erode

    Returns:
        cv2 img: binary mask after transformation
    """
    logger.info("Erode calc")
    # start = time.monotonic()
    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    mask_erode = cv2.erode(mask, kernel)

    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # logger.debug(time.monotonic() - start)
    logger.success("Erode calc")
    return mask_erode


def dilate(mask):
    """Apply a dilate operation to the given mask, with an elliptic kernel of 8x8

    Args:
        mask (cv2 img): mask to apply the operation on

    Returns:
        cv2 img: mask after the transformation
    """
    logger.info("Dilate calc")
    # start = time.monotonic()
    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
    mask_dilate = cv2.dilate(mask, kernel)

    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # logger.debug(time.monotonic() - start)
    logger.success("Dilate calc")
    return mask_dilate


def close(mask):
    """Apply a close operation to the given mask, with an elliptic kernel of 8x8

    Args:
        mask (cv2 img): mask to apply the operation on

    Returns:
        cv2 img: mask after the transformation
    """
    logger.info("Close calc")
    # start = time.monotonic()
    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
    mask_close = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # logger.debug(time.monotonic() - start)
    logger.success("Close calc")
    return mask_close


def erode2(mask):
    """Apply an erode operation to the given mask, with an elliptic kernel of 8x8

    Args:
        mask (cv2 img): mask to apply the operation on

    Returns:
        cv2 img: mask after the transformation
    """
    logger.info("Erode calc 2")
    # start = time.monotonic()
    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (8, 8))
    mask_erode_2 = cv2.erode(mask, kernel)

    # logger.debug(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # logger.debug(time.monotonic() - start)
    logger.success("Erode calc 2")
    return mask_erode_2


# https://planktoscope.slack.com/archives/C01V5ENKG0M/p1714146253356569
def remove_previous_mask(mask):
    """Remove the mask from the previous pass from the given mask
    The given mask is then saved to be applied to the next pass

    Args:
        mask (cv2 img): mask to apply the operation on

    Returns:
        cv2 img: mask after the transformation
    """
    global __mask_to_remove
    if __mask_to_remove is not None:
        # start = time.monotonic()
        # np.append(__mask_to_remove, img_erode_2)
        # logger.debug(time.monotonic() - start)
        mask_and = mask & __mask_to_remove
        mask_final = mask - mask_and
        logger.success("Done removing the previous mask")
        __mask_to_remove = mask
        return mask_final
    else:
        logger.debug("First mask")
        __mask_to_remove = mask
        return __mask_to_remove


def no_op(mask):
    """Return the mask without modifying it.

    This is provided as a quick-and-dirty hack to disable certain steps in the pipeline such as
    remove_previous_mask, by allowing those steps to be substituted with this no-op step.
    """
    return mask


def reset_previous_mask():
    """Remove the mask from the previous pass from the given mask
    The given mask is then saved to be applied to the next pass

    Args:
        mask (cv2 img): mask to apply the operation on

    Returns:
        cv2 img: mask after the transformation
    """
    global __mask_to_remove
    __mask_to_remove = None


def calculate_blur(img, mask=None):
    """Calculate a scale- and contrast-invariant focus measure for an object.

    Higher values indicate a sharper image, lower values indicate more blur.

    The previous metric was the raw Laplacian variance over the bounding-box
    crop. That metric is biased toward small, high-contrast objects: the edge
    (high-Laplacian) pixels scale with the object perimeter (~r) while the
    variance divides by the crop area (~r^2), so the score scales as ~1/r and
    small objects always look "sharper". It also scales with contrast^2, so a
    dark, well-focused object can score lower than a faint, blurry one.

    Instead we return the ratio of Laplacian energy to gradient energy over the
    object's edge band (the standard way scale/contrast invariance is achieved
    in focus-measure literature, e.g. Pertuz et al. 2013):

        S = sum(Laplacian^2) / sum(|grad I|^2)

    For an edge blurred by a Gaussian of width sigma, |Laplacian| ~ |grad|/sigma,
    so this ratio scales as ~1/sigma^2 — a direct measure of focus that is
    independent of object size (both sums run over the same edge pixels) and of
    contrast (it cancels in the ratio). One extra Sobel pass; cheap on a Pi.

    Args:
        img (cv2 img): Image to calculate blur for (BGR or grayscale).
        mask (ndarray, optional): Boolean/uint8 object mask aligned with ``img``
            (e.g. skimage ``region.filled_image``). When given, the measure is
            restricted to the object's edge band so background corners of the
            bounding box don't dilute it.

    Returns:
        float: Focus score (higher = sharper), or None if the image is invalid
        or contains no measurable edges.
    """
    if img is None or img.size == 0 or img.ndim < 2:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    gray = gray.astype(np.float32)

    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_sq = grad_x * grad_x + grad_y * grad_y

    if mask is not None and mask.shape == gray.shape:
        # Dilate by one pixel so the object boundary — where the focus signal
        # lives — is included, then keep only that edge band.
        band = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        lap = lap[band]
        grad_sq = grad_sq[band]

    edge_energy = float(grad_sq.sum())
    if edge_energy <= 1e-6:
        return None  # no edges -> focus is undefined for this object
    return float((lap * lap).sum() / edge_energy)
