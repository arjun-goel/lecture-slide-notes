"""
Duplicate Detector Module for LectureSlide Notes.
Uses perceptual hashing (dHash) and Structural Similarity (SSIM)
to eliminate duplicate slides and repeated frames across the lecture timeline.
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Tuple
from backend.vision.slide_detector import compute_ssim

logger = logging.getLogger(__name__)


def compute_dhash(frame_bgr: np.ndarray, hash_size: int = 8) -> int:
    """
    Computes difference hash (dHash) of an image.
    1. Converts to grayscale.
    2. Resizes to (hash_size + 1, hash_size), e.g. 9x8.
    3. Compares adjacent horizontal pixels (P[x] > P[x+1]).
    4. Produces a 64-bit integer perceptual fingerprint.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    
    # Compare adjacent pixels
    diff = resized[:, 1:] > resized[:, :-1]
    
    # Flatten bool array into binary integer
    hash_int = 0
    for bit in diff.flatten():
        hash_int = (hash_int << 1) | int(bit)
        
    return hash_int


def compute_ahash(frame_bgr: np.ndarray, hash_size: int = 8) -> int:
    """
    Computes average hash (aHash) of an image.
    Resizes to 8x8 grayscale and compares each pixel to the mean value.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    avg = np.mean(resized)
    diff = resized > avg
    
    hash_int = 0
    for bit in diff.flatten():
        hash_int = (hash_int << 1) | int(bit)
        
    return hash_int


def hamming_distance(h1: int, h2: int) -> int:
    """Calculate the Hamming distance (number of bit differences) between two 64-bit hashes."""
    x = h1 ^ h2
    return bin(x).count('1')


def is_duplicate_slide(
    new_frame_bgr: np.ndarray,
    existing_slides: List[Dict[str, Any]],
    max_hamming_dist: int = 6,
    min_ssim: float = 0.88
) -> Tuple[bool, int]:
    """
    Determines if `new_frame_bgr` matches any previously approved slide in `existing_slides`.
    Returns (is_duplicate: bool, matching_slide_index: int).
    """
    if not existing_slides:
        return False, -1

    new_hash = compute_dhash(new_frame_bgr)
    new_small = cv2.resize(cv2.cvtColor(new_frame_bgr, cv2.COLOR_BGR2GRAY), (320, 180), interpolation=cv2.INTER_AREA)

    for idx, slide in enumerate(existing_slides):
        # Compare perceptual hash
        slide_hash = slide.get('dhash')
        if slide_hash is None:
            slide_hash = compute_dhash(slide['frame'])
            slide['dhash'] = slide_hash

        h_dist = hamming_distance(new_hash, slide_hash)
        
        # If perceptual hash is extremely close, confirm with SSIM
        if h_dist <= max_hamming_dist:
            ref_small = cv2.resize(cv2.cvtColor(slide['frame'], cv2.COLOR_BGR2GRAY), (320, 180), interpolation=cv2.INTER_AREA)
            ssim_score = compute_ssim(new_small, ref_small)
            if ssim_score >= min_ssim:
                logger.debug(
                    f"Slide at timestamp {new_frame_bgr} identified as duplicate of Slide #{idx+1} "
                    f"(Hamming: {h_dist}, SSIM: {ssim_score:.3f})"
                )
                return True, idx

    return False, -1


def filter_duplicate_slides(
    slides: List[Dict[str, Any]],
    max_hamming_dist: int = 6,
    min_ssim: float = 0.88
) -> List[Dict[str, Any]]:
    """
    Scans an ordered list of candidate slides and removes redundant copies,
    retaining chronological ordering of distinct slides.
    """
    unique_slides: List[Dict[str, Any]] = []

    for item in slides:
        is_dup, _ = is_duplicate_slide(
            item['frame'],
            unique_slides,
            max_hamming_dist=max_hamming_dist,
            min_ssim=min_ssim
        )
        if not is_dup:
            if 'dhash' not in item:
                item['dhash'] = compute_dhash(item['frame'])
            unique_slides.append(item)

    logger.info(f"Deduplication complete: {len(slides)} candidate slides reduced to {len(unique_slides)} unique slides.")
    return unique_slides
