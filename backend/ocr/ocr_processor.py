"""
OCR Processor Module for LectureSlide Notes.
Extracts slide text using Tesseract OCR (via pytesseract) and OpenCV image preprocessing.
Operates 100% locally with zero paid APIs. Handles missing Tesseract installations gracefully.
"""

import os
import shutil
import cv2
import numpy as np
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Search common paths on Windows where Tesseract OCR might be installed
KNOWN_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    r"C:\tools\tesseract\tesseract.exe",
]

_TESSERACT_AVAILABLE = False
_TESSERACT_CHECKED = False


def find_tesseract_binary() -> Optional[str]:
    """Locate the tesseract executable on system PATH or standard installation directories."""
    # Check if 'tesseract' is directly on PATH
    cmd_path = shutil.which("tesseract")
    if cmd_path and os.path.exists(cmd_path):
        return cmd_path

    # Check known Windows locations
    for p in KNOWN_TESSERACT_PATHS:
        if os.path.exists(p):
            return p

    return None


def init_tesseract() -> bool:
    """Initialize pytesseract configuration and verify availability."""
    global _TESSERACT_AVAILABLE, _TESSERACT_CHECKED
    if _TESSERACT_CHECKED:
        return _TESSERACT_AVAILABLE

    _TESSERACT_CHECKED = True
    try:
        import pytesseract
        exe_path = find_tesseract_binary()
        if exe_path:
            pytesseract.pytesseract.tesseract_cmd = exe_path
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract OCR initialized successfully: {exe_path} (v{version})")
            _TESSERACT_AVAILABLE = True
        else:
            logger.warning(
                "Tesseract OCR executable not detected in system PATH or standard locations. "
                "Slide extraction will succeed, but OCR text extraction will be skipped until Tesseract is installed."
            )
            _TESSERACT_AVAILABLE = False
    except Exception as e:
        logger.warning(f"Tesseract OCR initialization note: {e}")
        _TESSERACT_AVAILABLE = False

    return _TESSERACT_AVAILABLE


def preprocess_slide_for_ocr(frame_bgr: np.ndarray) -> np.ndarray:
    """
    Applies image preprocessing specifically optimized for document/slide OCR:
    1. Grayscale conversion
    2. Upscaling if frame is small
    3. Contrast adjustment (CLAHE)
    4. Bilateral filter for noise smoothing while preserving text edge sharpness
    5. Adaptive thresholding / Otsu binarization
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    # Upscale slightly if dimensions are low (e.g. 720p or lower) to aid small font recognition
    h, w = gray.shape
    if w < 1280:
        scale = 1280 / w
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # Enhance contrast using CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Denoise while maintaining sharp edges
    denoised = cv2.bilateralFilter(enhanced, 7, 50, 50)

    # Otsu thresholding
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return thresh


def clean_ocr_text(text: str) -> str:
    """
    Normalizes extracted OCR text:
    - Strips non-printable artifacts
    - Eliminates excessive empty lines
    - Preserves bullet structures and paragraph flow
    """
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines()]
    # Remove lines consisting solely of noisy single punctuation marks
    cleaned_lines = []
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        # Skip pure noise (e.g. single symbols or random unreadable characters)
        if len(line) <= 2 and not line.isalnum():
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def extract_text_from_slide(frame_bgr: np.ndarray) -> Dict[str, Any]:
    """
    Attempts to extract text from a slide frame.
    Returns:
    {
        "text": str,
        "success": bool,
        "word_count": int,
        "status_message": str
    }
    """
    has_tesseract = init_tesseract()
    if not has_tesseract:
        return {
            "text": "",
            "success": False,
            "word_count": 0,
            "status_message": "Tesseract OCR binary not installed on host PATH. Text extraction skipped."
        }

    try:
        import pytesseract

        # 1. Try standard text extraction on original image
        custom_config = r'--oem 3 --psm 6'  # Assume uniform block of text
        text = pytesseract.image_to_string(frame_bgr, config=custom_config)
        cleaned = clean_ocr_text(text)

        # 2. If short or empty, retry with preprocessed binarized image and automatic page segmentation
        if len(cleaned.split()) < 5:
            processed = preprocess_slide_for_ocr(frame_bgr)
            fallback_text = pytesseract.image_to_string(processed, config=r'--oem 3 --psm 3')
            cleaned_fallback = clean_ocr_text(fallback_text)
            if len(cleaned_fallback) > len(cleaned):
                cleaned = cleaned_fallback

        words = cleaned.split()
        return {
            "text": cleaned,
            "success": bool(cleaned),
            "word_count": len(words),
            "status_message": f"Successfully extracted {len(words)} words." if cleaned else "No text detected on slide."
        }
    except Exception as e:
        logger.warning(f"OCR execution warning: {e}")
        return {
            "text": "",
            "success": False,
            "word_count": 0,
            "status_message": f"OCR processing notice: {str(e)}"
        }
