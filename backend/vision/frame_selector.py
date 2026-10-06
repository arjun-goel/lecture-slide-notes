"""
Frame Selector Module for LectureSlide Notes.
Analyzes candidate frames within a slide's presentation duration
and selects the clearest, sharpest, most stable, and least obstructed representative frame.
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


def compute_sharpness(gray_frame: np.ndarray) -> float:
    """
    Computes sharpness using the variance of the Laplacian.
    Higher values represent sharper text/edges and absence of motion blur.
    """
    laplacian = cv2.Laplacian(gray_frame, cv2.CV_64F)
    variance = float(laplacian.var())
    return variance


def compute_unobstructed_score(frame_bgr: np.ndarray) -> float:
    """
    Heuristic to estimate how unobstructed the slide area is.
    Evaluates:
    - Text/diagram area consistency across quadrantal zones.
    - Presence of large, irregular moving blobs (typical of a walking professor).
    Returns a score [0.0 - 100.0] where 100 is completely unobstructed.
    """
    h, w = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    
    # Analyze quadrantal contrast balance:
    # A walking presenter typically causes localized dark/irregular blocks in lower halves
    q_top_left = gray[0:h//2, 0:w//2]
    q_top_right = gray[0:h//2, w//2:]
    q_bot_left = gray[h//2:, 0:w//2]
    q_bot_right = gray[h//2:, w//2:]

    # Text edges in slide headers and body
    edges = cv2.Canny(gray, 50, 150)
    top_edge_ratio = np.count_nonzero(edges[0:h//3, :]) / max(1, (h//3 * w))
    
    # Penalize extreme variance between left and right bottom halves when top is uniform
    bot_l_mean = np.mean(q_bot_left)
    bot_r_mean = np.mean(q_bot_right)
    bot_imbalance = abs(bot_l_mean - bot_r_mean) / 255.0

    score = 100.0 - (bot_imbalance * 30.0)
    # Boost if clear top edge structure (titles / headers)
    if top_edge_ratio > 0.01:
        score += 10.0

    return float(np.clip(score, 10.0, 100.0))


def select_best_frame(candidate_frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Given a list of candidates in a slide timeframe:
    [{'timestamp': float, 'frame': np.ndarray, 'frame_idx': int}, ...]
    
    Scores each candidate on:
    - Sharpness (Laplacian variance)
    - Temporal stability (consistency with neighboring candidates)
    - Unobstructedness
    
    Returns the optimal candidate dict with an added 'quality_score' field.
    """
    if not candidate_frames:
        raise ValueError("Cannot select best frame from an empty candidate list.")

    if len(candidate_frames) == 1:
        chosen = candidate_frames[0].copy()
        gray = cv2.cvtColor(chosen['frame'], cv2.COLOR_BGR2GRAY)
        chosen['sharpness'] = compute_sharpness(gray)
        chosen['quality_score'] = 100.0
        return chosen

    scored_candidates = []
    
    for i, item in enumerate(candidate_frames):
        frame = item['frame']
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = compute_sharpness(gray)
        unobstructed = compute_unobstructed_score(frame)

        # Temporal stability check with successor/predecessor:
        # If the frame differs wildly from the settled state, it's likely a transition in progress
        stability_bonus = 0.0
        if i > 0:
            prev_gray = cv2.cvtColor(candidate_frames[i - 1]['frame'], cv2.COLOR_BGR2GRAY)
            diff = float(np.mean(cv2.absdiff(gray, prev_gray)))
            # Lower difference between consecutive frames means the animation/slide is stable
            if diff < 15.0:
                stability_bonus += 20.0

        # Avoid the very first frame of a transition if multiple frames exist
        # because the first frame often contains half-switched content or slide wipes
        position_penalty = 15.0 if (i == 0 and len(candidate_frames) > 2) else 0.0

        composite_score = (
            min(sharpness, 1000.0) * 0.4 +
            unobstructed * 0.4 +
            stability_bonus * 0.2 -
            position_penalty
        )

        scored_candidates.append({
            **item,
            'sharpness': sharpness,
            'unobstructed': unobstructed,
            'quality_score': composite_score
        })

    # Sort descending by composite score
    scored_candidates.sort(key=lambda x: x['quality_score'], reverse=True)
    best = scored_candidates[0]
    logger.debug(
        f"Selected optimal frame at {best['timestamp']:.2f}s "
        f"(Sharpness: {best['sharpness']:.1f}, Score: {best['quality_score']:.1f})"
    )
    return best
