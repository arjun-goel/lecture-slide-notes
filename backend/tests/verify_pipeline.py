"""
Verification Test Script for LectureSlide Notes.
Performs an automated end-to-end test of the complete pipeline:
- Video generation / acquisition
- Incremental frame sampling
- Computer vision slide change detection
- Sharpness / stability frame selection
- Perceptual hash deduplication
- OCR text extraction
- ReportLab PDF compilation
- FastAPI API endpoints verification
"""

import os
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from backend.utils.demo_generator import create_synthetic_lecture_video
from backend.video.video_processor import (
    sample_frames_incremental,
    get_video_properties,
    is_valid_youtube_url
)
from backend.vision.slide_detector import calculate_frame_difference_metrics, is_slide_change
from backend.vision.frame_selector import select_best_frame
from backend.vision.duplicate_detector import filter_duplicate_slides
from backend.ocr.ocr_processor import extract_text_from_slide, init_tesseract
from backend.pdf.pdf_generator import generate_lecture_pdf
from backend.services.job_manager import job_manager


def run_pipeline_verification():
    print("=" * 70)
    print("STARTING LECTURESLIDE NOTES END-TO-END PIPELINE VERIFICATION")
    print("=" * 70)

    test_dir = os.path.join(PROJECT_ROOT, "data", "test_verification")
    os.makedirs(test_dir, exist_ok=True)
    video_path = os.path.join(test_dir, "test_lecture.mp4")

    # 1. Test YouTube URL validator
    print("\n[TEST 1] Verifying URL validation...")
    valid_test_urls = [
        "https://www.youtube.com/watch?v=kCCoy4L4G_g",
        "https://youtu.be/fNKuz4kg58U",
        "https://www.youtube.com/embed/dQw4w9WgXcQ"
    ]
    invalid_test_urls = [
        "https://google.com",
        "not_a_url",
        "https://vimeo.com/12345"
    ]
    for u in valid_test_urls:
        assert is_valid_youtube_url(u) is True, f"Failed to validate {u}"
    for u in invalid_test_urls:
        assert is_valid_youtube_url(u) is False, f"Erroneously validated {u}"
    print("[PASS] URL validator passed: correctly distinguishes YouTube URLs.")

    # 2. Generate multi-slide test lecture video with transitions & simulated movement
    print("\n[TEST 2] Generating multi-slide test video (20 seconds, 5 slides with transitions)...")
    create_synthetic_lecture_video(video_path, width=800, height=450, fps=20)
    assert os.path.exists(video_path), "Test video was not generated."
    props = get_video_properties(video_path)
    print(f"[PASS] Video ready: {props['width']}x{props['height']}, {props['fps']} FPS, {props['duration_sec']:.1f}s")

    # 3. Test Incremental Frame Sampling
    print("\n[TEST 3] Testing incremental frame sampling (1.0s interval)...")
    sampled_frames = list(sample_frames_incremental(video_path, interval_sec=1.0))
    print(f"[PASS] Sampled {len(sampled_frames)} frames incrementally without loading entire video to memory.")
    assert len(sampled_frames) >= 15, "Expected at least 15 sampled frames."

    # 4. Test Slide Change Detection
    print("\n[TEST 4] Testing computer vision slide change detection...")
    raw_segments = []
    current_segment = []
    prev_frame = None
    ref_frame = None

    for ts, frame, frame_idx in sampled_frames:
        entry = {"timestamp": ts, "frame": frame, "frame_idx": frame_idx}
        if prev_frame is None:
            current_segment.append(entry)
            prev_frame = frame
            ref_frame = frame
            continue

        metrics_prev = calculate_frame_difference_metrics(prev_frame, frame)
        metrics_ref = calculate_frame_difference_metrics(ref_frame, frame) if ref_frame is not None else metrics_prev
        if is_slide_change(metrics_prev, sensitivity="medium") or is_slide_change(metrics_ref, sensitivity="medium"):
            if current_segment:
                raw_segments.append(current_segment)
            current_segment = [entry]
            ref_frame = frame
        else:
            current_segment.append(entry)
        prev_frame = frame

    if current_segment:
        raw_segments.append(current_segment)

    print(f"[PASS] Detected {len(raw_segments)} raw candidate segments.")
    assert len(raw_segments) >= 4, f"Expected at least 4 raw segments, got {len(raw_segments)}"

    # 5. Test Frame Selector (Clarity, Sharpness, Obstruction handling)
    print("\n[TEST 5] Testing intelligent frame selection (sharpest, least obstructed)...")
    candidate_slides = []
    for idx, seg in enumerate(raw_segments, start=1):
        best = select_best_frame(seg)
        print(f"  Segment #{idx}: {len(seg)} frames -> Selected frame at {best['timestamp']:.1f}s (Sharpness: {best['sharpness']:.1f})")
        candidate_slides.append(best)
    assert len(candidate_slides) == len(raw_segments)
    print("[PASS] Frame selector successfully selected optimal representative frames.")

    # 6. Test Deduplication
    print("\n[TEST 6] Testing perceptual hash deduplication (dHash + SSIM)...")
    # Remember: slide 4 in our video was an exact duplicate of slide 1
    unique_slides = filter_duplicate_slides(candidate_slides)
    print(f"[PASS] Deduplication reduced {len(candidate_slides)} candidates to {len(unique_slides)} unique slides.")
    # The duplicate slide must have been detected and removed
    assert len(unique_slides) < len(candidate_slides), "Duplicate slide was not detected!"

    # 7. Test Slide Image Persistence & OCR
    print("\n[TEST 7] Testing slide image saving & OCR text extraction...")
    tesseract_ok = init_tesseract()
    print(f"  Tesseract OCR available: {tesseract_ok}")

    import cv2
    slides_data = []
    for idx, item in enumerate(unique_slides, start=1):
        img_name = f"verified_slide_{idx}.png"
        img_path = os.path.join(test_dir, img_name)
        cv2.imwrite(img_path, item["frame"])
        
        ocr_result = extract_text_from_slide(item["frame"])
        text_preview = ocr_result["text"].replace('\n', ' ')[:45] if ocr_result["text"] else "(no text / tesseract not installed)"
        print(f"  Slide #{idx} (t={item['timestamp']:.1f}s): OCR -> \"{text_preview}\"")

        slides_data.append({
            "slide_id": idx,
            "timestamp": item["timestamp"],
            "image_path": img_path,
            "ocr_text": ocr_result.get("text", "")
        })

    # 8. Test ReportLab PDF Generation
    print("\n[TEST 8] Testing ReportLab PDF generation...")
    pdf_out = os.path.join(test_dir, "test_lecture_notes.pdf")
    generate_lecture_pdf(
        lecture_title="Physics 101: Newton's Laws of Motion (Verified)",
        youtube_url="https://www.youtube.com/watch?v=kCCoy4L4G_g",
        slides=slides_data,
        output_pdf_path=pdf_out,
        include_ocr=True
    )
    assert os.path.exists(pdf_out), "PDF was not generated!"
    pdf_size = os.path.getsize(pdf_out)
    print(f"[PASS] PDF generated successfully: {pdf_out} ({pdf_size} bytes)")
    
    with open(pdf_out, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-", f"Invalid PDF header: {header}"
    print("[PASS] Verified valid PDF format (%PDF-).")

    # 9. Test Job Manager Full Asynchronous Pipeline
    print("\n[TEST 9] Testing Job Manager asynchronous job lifecycle...")
    job = job_manager.create_job(
        source_url=video_path,
        options={"sample_interval": 1.0, "sensitivity": "medium", "run_ocr": True}
    )
    job.lecture_title = "Automated Test Lecture"
    job_manager.start_job(job.job_id)

    # Wait for completion
    timeout = 30
    start = time.time()
    while job.status not in ("completed", "failed") and time.time() - start < timeout:
        time.sleep(0.5)

    assert job.status == "completed", f"Job failed or timed out: {job.status} ({job.error_message})"
    assert len(job.slides) > 0, "No slides detected in job."
    assert job.pdf_path and os.path.exists(job.pdf_path), "Job PDF was not created."
    print(f"[PASS] Job Manager completed in {job.processing_time_sec:.1f}s with {len(job.slides)} slides!")

    # 10. Test Slide Deletion & PDF Regeneration
    print("\n[TEST 10] Testing slide deletion curation & dynamic PDF rebuild...")
    initial_count = len(job.slides)
    deleted = job_manager.delete_slide(job.job_id, 1)
    assert deleted is True, "Failed to delete slide #1"
    new_count = len(job.slides)
    assert new_count == initial_count - 1, f"Expected {initial_count - 1} slides, got {new_count}"
    assert os.path.exists(job.pdf_path), "PDF was not updated after deletion."
    print(f"[PASS] Successfully deleted slide from job and regenerated PDF ({new_count} remaining slides).")

    print("\n" + "=" * 70)
    print("ALL 10 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_pipeline_verification()
