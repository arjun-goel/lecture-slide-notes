"""
Slide Detector Module for LectureSlide Notes.
Implements robust computer-vision algorithms to detect when a presenter
advances to a new slide or writes new content on a lecture board.
"""

import cv2
import numpy as np
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


def compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """
    Computes Structural Similarity Index (SSIM) between two grayscale images
    using local Gaussian windowing without external heavy dependencies.
    Returns float in range [-1, 1], where 1.0 indicates identical images.
    """
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    img1 = img1.astype(np.float64)
    img2 = img2.astype(np.float64)
    kernel = cv2.getGaussianKernel(11, 1.5)
    window = np.outer(kernel, kernel.transpose())

    mu1 = cv2.filter2D(img1, -1, window)[5:-5, 5:-5]
    mu2 = cv2.filter2D(img2, -1, window)[5:-5, 5:-5]
    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.filter2D(img1 ** 2, -1, window)[5:-5, 5:-5] - mu1_sq
    sigma2_sq = cv2.filter2D(img2 ** 2, -1, window)[5:-5, 5:-5] - mu2_sq
    sigma12 = cv2.filter2D(img1 * img2, -1, window)[5:-5, 5:-5] - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return float(np.clip(np.mean(ssim_map), 0.0, 1.0))


def compute_histogram_similarity(frame1: np.ndarray, frame2: np.ndarray) -> float:
    """
    Compute Bhattacharyya / correlation metric on HSV color histograms.
    Returns similarity between 0.0 (completely distinct) and 1.0 (identical).
    """
    hsv1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2HSV)
    hsv2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2HSV)

    hist1 = cv2.calcHist([hsv1], [0, 1], None, [30, 32], [0, 180, 0, 256])
    hist2 = cv2.calcHist([hsv2], [0, 1], None, [30, 32], [0, 180, 0, 256])

    cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    return float(max(0.0, min(1.0, correlation)))


def compute_edge_difference(gray1: np.ndarray, gray2: np.ndarray) -> float:
    """
    Measure edge divergence using Canny detector.
    Distinguishes actual textual/diagram changes from mere lighting or small motion.
    Returns normalized difference [0.0, 1.0].
    """
    edges1 = cv2.Canny(gray1, 50, 150)
    edges2 = cv2.Canny(gray2, 50, 150)

    diff = cv2.absdiff(edges1, edges2)
    non_zero = np.count_nonzero(diff)
    total_pixels = diff.shape[0] * diff.shape[1]
    return float(non_zero / total_pixels)


def calculate_frame_difference_metrics(
    prev_frame_bgr: np.ndarray,
    curr_frame_bgr: np.ndarray,
    eval_dim: Tuple[int, int] = (320, 180)
) -> Dict[str, float]:
    """
    Downsamples frames to a standardized evaluation dimension and computes
    multi-faceted comparison metrics:
    - pixel_diff: Normalized mean absolute pixel difference [0.0 - 1.0]
    - ssim: Structural similarity [0.0 - 1.0]
    - hist_sim: Color distribution correlation [0.0 - 1.0]
    - edge_diff: Edge divergence ratio [0.0 - 1.0]
    - combined_change_score: Weighted composite change indicator [0.0 - 1.0]
    """
    # Downsample for fast processing
    p_small = cv2.resize(prev_frame_bgr, eval_dim, interpolation=cv2.INTER_AREA)
    c_small = cv2.resize(curr_frame_bgr, eval_dim, interpolation=cv2.INTER_AREA)

    p_gray = cv2.cvtColor(p_small, cv2.COLOR_BGR2GRAY)
    c_gray = cv2.cvtColor(c_small, cv2.COLOR_BGR2GRAY)

    # Blur to mitigate sensor noise
    p_blur = cv2.GaussianBlur(p_gray, (5, 5), 0)
    c_blur = cv2.GaussianBlur(c_gray, (5, 5), 0)

    # Pixel absolute difference
    abs_diff = cv2.absdiff(p_blur, c_blur)
    pixel_diff = float(np.mean(abs_diff) / 255.0)

    # SSIM
    ssim = compute_ssim(p_blur, c_blur)

    # Color histogram similarity
    hist_sim = compute_histogram_similarity(p_small, c_small)

    # Edge difference
    edge_diff = compute_edge_difference(p_blur, c_blur)

    # Combined change score (0 = identical, 1 = completely different slide)
    # High pixel diff + low ssim + low hist_sim + high edge_diff indicate a slide change
    combined_change_score = (
        0.35 * pixel_diff +
        0.35 * (1.0 - ssim) +
        0.15 * (1.0 - hist_sim) +
        0.15 * min(1.0, edge_diff * 4.0)
    )

    return {
        "pixel_diff": pixel_diff,
        "ssim": ssim,
        "hist_sim": hist_sim,
        "edge_diff": edge_diff,
        "combined_change_score": float(np.clip(combined_change_score, 0.0, 1.0))
    }


def is_slide_change(
    metrics: Dict[str, float],
    sensitivity: str = "medium"
) -> bool:
    """
    Determines whether the calculated metrics represent a true slide/board change.
    Sensitivity presets:
    - low: Requires substantial visual shift (higher threshold, avoids false positives)
    - medium: Balanced (standard presentation slides)
    - high: More sensitive (captures subtle board updates / progressive builds)
    """
    thresholds = {
        "low": {"change_score": 0.075, "ssim_max": 0.90, "pixel_min": 0.025},
        "medium": {"change_score": 0.045, "ssim_max": 0.94, "pixel_min": 0.012},
        "high": {"change_score": 0.028, "ssim_max": 0.96, "pixel_min": 0.007},
    }

    cfg = thresholds.get(sensitivity.lower(), thresholds["medium"])
    change_score = metrics["combined_change_score"]
    ssim = metrics["ssim"]
    pixel_diff = metrics["pixel_diff"]

    # Rule 1: High composite change score
    if change_score >= cfg["change_score"]:
        return True

    # Rule 2: SSIM drop with non-trivial pixel difference
    if ssim <= cfg["ssim_max"] and pixel_diff >= cfg["pixel_min"]:
        return True

    return False


def estimate_slide_quality(frame_bgr: np.ndarray) -> float:
    """
    Measures slide visual clarity:
    - High contrast text/graphics
    - Clean distribution of light background or dark theme
    Returns a score from 0.0 to 100.0.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    contrast = float(np.std(gray))
    # Edge density
    edges = cv2.Canny(gray, 50, 150)
    edge_density = float(np.count_nonzero(edges) / (edges.shape[0] * edges.shape[1]))
    
    # Combined score
    score = (contrast * 0.6) + (edge_density * 400.0 * 0.4)
    return float(score)
