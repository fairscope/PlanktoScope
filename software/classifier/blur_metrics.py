"""
blur_metrics.py - Professional Blurriness Quantification for PlanktoScope

Multi-method blur detection optimized for microscopy plankton images.
Provides robust focus quality metrics for each segmented object.

Methods implemented:
1. Laplacian Variance - Classic edge sharpness measure
2. Tenengrad (Sobel gradient) - Gradient magnitude energy
3. Brenner Gradient - Adjacent pixel difference
4. Normalized Variance - Intensity distribution spread
5. FFT High-Frequency Ratio - Frequency domain analysis

Each method returns a score where HIGHER = SHARPER (less blurry).
The composite score combines all methods with learned weights.

Integration:
    from blur_metrics import BlurAnalyzer
    analyzer = BlurAnalyzer()
    metrics = analyzer.analyze(roi_image, roi_mask)
    # metrics['blur_score'] -> 0-100 (100 = sharpest)
    # metrics['is_blurry'] -> True/False

Author: PlanktoScope Project
Version: 1.0.0
"""

import numpy as np

# Lazy import for cv2 (heavy library)
cv2 = None


def _ensure_cv2():
    global cv2
    if cv2 is None:
        import cv2 as _cv2

        cv2 = _cv2


class BlurAnalyzer:
    """
    Multi-method blur analysis for microscopy object images.

    Designed for robustness across varying:
    - Object sizes (10px to 500px)
    - Illumination conditions
    - Organism types (transparent to opaque)
    """

    # Empirically tuned weights for combining methods
    # Based on microscopy image characteristics
    DEFAULT_WEIGHTS = {
        "laplacian": 0.30,  # Best for edge detection
        "tenengrad": 0.25,  # Good gradient sensitivity
        "brenner": 0.20,  # Fast, size-invariant
        "norm_variance": 0.15,  # Handles low contrast
        "fft_ratio": 0.10,  # Frequency analysis backup
    }

    # Thresholds calibrated for PlanktoScope optics
    # Objects below this composite score are considered blurry
    BLUR_THRESHOLD = 35.0

    def __init__(self, weights=None, blur_threshold=None):
        """
        Initialize blur analyzer.

        Args:
            weights: Dict of method weights (must sum to 1.0)
            blur_threshold: Score below which object is "blurry"
        """
        _ensure_cv2()
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.blur_threshold = blur_threshold or self.BLUR_THRESHOLD

        # Normalize weights to sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def analyze(self, image, mask=None):
        """
        Compute comprehensive blur metrics for an object ROI.

        Args:
            image: BGR or grayscale image (numpy array)
            mask: Optional binary mask for the object

        Returns:
            dict with keys:
                - blur_score: Composite score 0-100 (100 = sharpest)
                - is_blurry: Boolean classification
                - laplacian_var: Laplacian variance (raw)
                - tenengrad: Tenengrad score (raw)
                - brenner: Brenner gradient (raw)
                - norm_variance: Normalized variance (raw)
                - fft_ratio: High-frequency ratio (raw)
                - confidence: Confidence in measurement (0-1)
        """
        if image is None or image.size == 0:
            return self._empty_result()

        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Apply mask if provided
        if mask is not None and mask.size == gray.size:
            # Ensure mask is binary
            mask_bin = (mask > 0).astype(np.uint8)
            gray = cv2.bitwise_and(gray, gray, mask=mask_bin)

        # Skip if image is too small for reliable analysis
        h, w = gray.shape
        if h < 8 or w < 8:
            return self._empty_result(reason="too_small")

        # Compute individual metrics
        laplacian = self._laplacian_variance(gray, mask)
        tenengrad = self._tenengrad(gray, mask)
        brenner = self._brenner_gradient(gray, mask)
        norm_var = self._normalized_variance(gray, mask)
        fft_ratio = self._fft_high_freq_ratio(gray, mask)

        # Normalize each metric to 0-100 scale
        scores = {
            "laplacian": self._normalize_laplacian(laplacian),
            "tenengrad": self._normalize_tenengrad(tenengrad),
            "brenner": self._normalize_brenner(brenner),
            "norm_variance": self._normalize_norm_var(norm_var),
            "fft_ratio": self._normalize_fft(fft_ratio),
        }

        # Compute weighted composite score
        composite = sum(
            scores[method] * self.weights[method] for method in self.weights
        )

        # Compute confidence based on agreement between methods
        values = list(scores.values())
        std_dev = np.std(values)
        confidence = max(0, 1.0 - (std_dev / 50.0))  # Lower std = higher confidence

        return {
            "blur_score": round(composite, 2),
            "is_blurry": composite < self.blur_threshold,
            "laplacian_var": round(laplacian, 4),
            "tenengrad": round(tenengrad, 4),
            "brenner": round(brenner, 4),
            "norm_variance": round(norm_var, 4),
            "fft_ratio": round(fft_ratio, 4),
            "confidence": round(confidence, 3),
            # Individual normalized scores for debugging
            "_scores": {k: round(v, 2) for k, v in scores.items()},
        }

    def _empty_result(self, reason="invalid"):
        """Return empty result for invalid inputs."""
        return {
            "blur_score": 0.0,
            "is_blurry": True,
            "laplacian_var": 0.0,
            "tenengrad": 0.0,
            "brenner": 0.0,
            "norm_variance": 0.0,
            "fft_ratio": 0.0,
            "confidence": 0.0,
            "_reason": reason,
        }

    # =========================================================================
    # BLUR DETECTION METHODS
    # =========================================================================

    def _laplacian_variance(self, gray, mask=None):
        """
        Laplacian variance - measures second derivative (edge sharpness).

        Sharp images have strong edges → high Laplacian response → high variance.
        Blurry images have smooth gradients → low Laplacian response → low variance.
        """
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)

        if mask is not None:
            # Only consider masked region
            valid_pixels = laplacian[mask > 0]
            if len(valid_pixels) == 0:
                return 0.0
            return float(np.var(valid_pixels))

        return float(np.var(laplacian))

    def _tenengrad(self, gray, mask=None):
        """
        Tenengrad - sum of squared Sobel gradients.

        Measures gradient magnitude energy. Sharp images have
        strong gradients at edges, blurry images have weak gradients.
        """
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

        gradient_magnitude = gx**2 + gy**2

        if mask is not None:
            valid_pixels = gradient_magnitude[mask > 0]
            if len(valid_pixels) == 0:
                return 0.0
            return float(np.mean(valid_pixels))

        return float(np.mean(gradient_magnitude))

    def _brenner_gradient(self, gray, mask=None):
        """
        Brenner gradient - difference between pixels 2 apart.

        Simple but effective measure. Computes (I[x+2] - I[x])^2.
        Less sensitive to noise than single-pixel differences.
        """
        if gray.shape[1] < 3:
            return 0.0

        # Horizontal gradient with 2-pixel gap
        diff = gray[:, 2:].astype(np.float64) - gray[:, :-2].astype(np.float64)
        brenner = diff**2

        if mask is not None:
            # Adjust mask for the shifted computation
            mask_valid = mask[:, 1:-1] if mask.shape[1] > 2 else mask
            if mask_valid.shape == brenner.shape:
                valid_pixels = brenner[mask_valid > 0]
                if len(valid_pixels) == 0:
                    return 0.0
                return float(np.mean(valid_pixels))

        return float(np.mean(brenner))

    def _normalized_variance(self, gray, mask=None):
        """
        Normalized variance - variance divided by mean.

        Handles varying brightness levels. Sharp images have
        higher relative contrast (variance) compared to their mean.
        """
        if mask is not None:
            pixels = gray[mask > 0].astype(np.float64)
        else:
            pixels = gray.astype(np.float64).flatten()

        if len(pixels) == 0:
            return 0.0

        mean_val = np.mean(pixels)
        if mean_val < 1.0:  # Avoid division by near-zero
            return 0.0

        variance = np.var(pixels)
        return float(variance / mean_val)

    def _fft_high_freq_ratio(self, gray, mask=None):
        """
        FFT high-frequency ratio - frequency domain analysis.

        Sharp images have more high-frequency content (fine details).
        Blurry images have energy concentrated in low frequencies.

        Returns ratio of high-freq to total energy.
        """
        # Pad to power of 2 for efficient FFT
        h, w = gray.shape
        h_pad = cv2.getOptimalDFTSize(h)
        w_pad = cv2.getOptimalDFTSize(w)

        padded = np.zeros((h_pad, w_pad), dtype=np.float32)
        padded[:h, :w] = gray.astype(np.float32)

        # Compute FFT
        dft = cv2.dft(padded, flags=cv2.DFT_COMPLEX_OUTPUT)
        dft_shift = np.fft.fftshift(dft)

        # Magnitude spectrum
        magnitude = cv2.magnitude(dft_shift[:, :, 0], dft_shift[:, :, 1])

        # Create high-frequency mask (exclude center 20%)
        center_y, center_x = h_pad // 2, w_pad // 2
        radius_low = int(min(h_pad, w_pad) * 0.1)  # Low freq region

        y, x = np.ogrid[:h_pad, :w_pad]
        low_freq_mask = (x - center_x) ** 2 + (y - center_y) ** 2 <= radius_low**2

        # Compute energy ratio
        total_energy = np.sum(magnitude)
        low_freq_energy = np.sum(magnitude[low_freq_mask])

        if total_energy < 1e-10:
            return 0.0

        high_freq_ratio = 1.0 - (low_freq_energy / total_energy)
        return float(high_freq_ratio)

    # =========================================================================
    # NORMALIZATION FUNCTIONS
    # =========================================================================
    # These convert raw metrics to 0-100 scale based on empirical calibration
    # for PlanktoScope microscopy images

    def _normalize_laplacian(self, value):
        """Normalize Laplacian variance to 0-100."""
        # Empirical range: 0 (very blurry) to ~2000 (very sharp)
        # Using log scale for better distribution
        if value <= 0:
            return 0.0
        log_val = np.log10(value + 1)
        # log10(1) = 0, log10(2001) ≈ 3.3
        normalized = (log_val / 3.3) * 100
        return min(100.0, max(0.0, normalized))

    def _normalize_tenengrad(self, value):
        """Normalize Tenengrad to 0-100."""
        # Empirical range: 0 to ~50000
        if value <= 0:
            return 0.0
        log_val = np.log10(value + 1)
        # log10(50001) ≈ 4.7
        normalized = (log_val / 4.7) * 100
        return min(100.0, max(0.0, normalized))

    def _normalize_brenner(self, value):
        """Normalize Brenner gradient to 0-100."""
        # Empirical range: 0 to ~10000
        if value <= 0:
            return 0.0
        log_val = np.log10(value + 1)
        # log10(10001) ≈ 4.0
        normalized = (log_val / 4.0) * 100
        return min(100.0, max(0.0, normalized))

    def _normalize_norm_var(self, value):
        """Normalize normalized variance to 0-100."""
        # Empirical range: 0 to ~100
        normalized = value
        return min(100.0, max(0.0, normalized))

    def _normalize_fft(self, value):
        """Normalize FFT ratio to 0-100."""
        # Value is already 0-1 ratio
        return min(100.0, max(0.0, value * 100))


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# Global analyzer instance for efficiency
_analyzer = None


def get_blur_metrics(image, mask=None):
    """
    Quick function to get blur metrics for an image ROI.

    Args:
        image: BGR or grayscale numpy array
        mask: Optional binary mask

    Returns:
        dict with blur_score, is_blurry, and individual metrics
    """
    global _analyzer
    if _analyzer is None:
        _analyzer = BlurAnalyzer()
    return _analyzer.analyze(image, mask)


def get_blur_score(image, mask=None):
    """
    Get just the composite blur score (0-100).

    Args:
        image: BGR or grayscale numpy array
        mask: Optional binary mask

    Returns:
        float: Blur score 0-100 (100 = sharpest)
    """
    metrics = get_blur_metrics(image, mask)
    return metrics["blur_score"]


def is_blurry(image, mask=None, threshold=None):
    """
    Check if an image/ROI is blurry.

    Args:
        image: BGR or grayscale numpy array
        mask: Optional binary mask
        threshold: Custom threshold (default 35)

    Returns:
        bool: True if blurry, False if sharp
    """
    metrics = get_blur_metrics(image, mask)
    thresh = threshold or BlurAnalyzer.BLUR_THRESHOLD
    return metrics["blur_score"] < thresh


# =============================================================================
# ECOTAXA INTEGRATION
# =============================================================================


def get_ecotaxa_blur_columns():
    """
    Return column names for EcoTaxa TSV integration.

    Returns:
        list of column name strings
    """
    return [
        "object_blur_score",  # Composite 0-100
        "object_blur_laplacian",  # Laplacian variance (raw)
        "object_blur_tenengrad",  # Tenengrad (raw)
        "object_blur_confidence",  # Confidence 0-1
    ]


def extract_blur_features(image, mask=None):
    """
    Extract blur features formatted for EcoTaxa TSV.

    Args:
        image: BGR or grayscale numpy array
        mask: Optional binary mask

    Returns:
        dict with EcoTaxa column names as keys
    """
    metrics = get_blur_metrics(image, mask)

    return {
        "object_blur_score": metrics["blur_score"],
        "object_blur_laplacian": metrics["laplacian_var"],
        "object_blur_tenengrad": metrics["tenengrad"],
        "object_blur_confidence": metrics["confidence"],
    }


# =============================================================================
# CLI TESTING
# =============================================================================

if __name__ == "__main__":
    import sys

    _ensure_cv2()

    if len(sys.argv) < 2:
        print("Usage: python blur_metrics.py <image_path> [mask_path]")
        print("\nTests blur detection on an image.")
        sys.exit(1)

    image_path = sys.argv[1]
    mask_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Load image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image: {image_path}")
        sys.exit(1)

    # Load mask if provided
    mask = None
    if mask_path:
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

    # Analyze
    analyzer = BlurAnalyzer()
    metrics = analyzer.analyze(img, mask)

    # Print results
    print(f"\n{'=' * 50}")
    print(f"BLUR ANALYSIS: {image_path}")
    print(f"{'=' * 50}")
    print(f"  Composite Score: {metrics['blur_score']:.1f}/100")
    print(f"  Classification:  {'BLURRY' if metrics['is_blurry'] else 'SHARP'}")
    print(f"  Confidence:      {metrics['confidence'] * 100:.1f}%")
    print(f"\nIndividual Metrics (raw):")
    print(f"  Laplacian Var:   {metrics['laplacian_var']:.2f}")
    print(f"  Tenengrad:       {metrics['tenengrad']:.2f}")
    print(f"  Brenner:         {metrics['brenner']:.2f}")
    print(f"  Norm Variance:   {metrics['norm_variance']:.2f}")
    print(f"  FFT Ratio:       {metrics['fft_ratio']:.4f}")
    print(f"\nNormalized Scores (0-100):")
    for method, score in metrics.get("_scores", {}).items():
        print(f"  {method:15s}: {score:.1f}")
    print(f"{'=' * 50}\n")
