"""
Job Manager Service for LectureSlide Notes.
Coordinates asynchronous video fetching, incremental frame sampling,
computer vision slide detection, deduplication, OCR, and PDF generation.
"""

import os
import time
import uuid
import cv2
import logging
import threading
from typing import Dict, Any, List, Optional

from backend.video.video_processor import (
    is_valid_youtube_url,
    extract_video_info,
    download_lecture_video,
    sample_frames_incremental,
    remove_temp_video,
    get_video_properties
)
from backend.vision.slide_detector import (
    calculate_frame_difference_metrics,
    is_slide_change
)
from backend.vision.frame_selector import select_best_frame
from backend.vision.duplicate_detector import filter_duplicate_slides, compute_dhash
from backend.ocr.ocr_processor import extract_text_from_slide, init_tesseract
from backend.pdf.pdf_generator import generate_lecture_pdf, format_timestamp

logger = logging.getLogger(__name__)

# Base storage directory for jobs and artifacts
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "jobs"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)


class LectureJob:
    """Represents the lifecycle and data of a single lecture processing task."""
    def __init__(self, job_id: str, source_url: str, options: Optional[Dict[str, Any]] = None):
        self.job_id = job_id
        self.source_url = source_url
        self.options = options or {}
        
        # Options with defaults
        self.sample_interval = float(self.options.get("sample_interval", 1.5))
        self.sensitivity = str(self.options.get("sensitivity", "medium"))
        self.run_ocr = bool(self.options.get("run_ocr", True))
        self.max_height = int(self.options.get("max_height", 720))

        # Runtime directories
        self.job_dir = os.path.join(WORKSPACE_DIR, self.job_id)
        self.slides_dir = os.path.join(self.job_dir, "slides")
        os.makedirs(self.slides_dir, exist_ok=True)

        # Status tracking
        self.status = "queued"
        self.progress_pct = 0
        self.stage_message = "Job queued for processing..."
        self.error_message: Optional[str] = None
        
        self.stages_completed = {
            "video_loaded": False,
            "sampling_frames": False,
            "detecting_slides": False,
            "deduplicating": False,
            "running_ocr": False,
            "pdf_ready": False,
        }

        # Metadata
        self.lecture_title = "Lecture Video"
        self.duration_sec = 0.0
        self.total_frames_sampled = 0
        self.candidate_slides_count = 0
        self.unique_slides_count = 0
        self.ocr_count = 0
        self.processing_time_sec = 0.0
        self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")

        # Results
        self.slides: List[Dict[str, Any]] = []
        self.pdf_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize job state for client responses."""
        return {
            "job_id": self.job_id,
            "source_url": self.source_url,
            "lecture_title": self.lecture_title,
            "duration_sec": self.duration_sec,
            "duration_formatted": format_timestamp(self.duration_sec),
            "status": self.status,
            "progress_pct": self.progress_pct,
            "stage_message": self.stage_message,
            "stages_completed": self.stages_completed,
            "total_frames_sampled": self.total_frames_sampled,
            "candidate_slides_count": self.candidate_slides_count,
            "unique_slides_count": len(self.slides),
            "ocr_count": self.ocr_count,
            "processing_time_sec": round(self.processing_time_sec, 1),
            "created_at": self.created_at,
            "slides": [
                {
                    "slide_id": s["slide_id"],
                    "timestamp": s["timestamp"],
                    "timestamp_formatted": s["timestamp_formatted"],
                    "image_url": f"/api/jobs/{self.job_id}/slides/{s['filename']}",
                    "ocr_text": s.get("ocr_text", ""),
                    "sharpness": round(s.get("sharpness", 0.0), 1)
                }
                for s in self.slides
            ],
            "pdf_available": bool(self.pdf_path and os.path.exists(self.pdf_path)),
            "error_message": self.error_message
        }


class JobManager:
    """Thread-safe manager for tracking and executing lecture processing jobs."""
    def __init__(self):
        self._jobs: Dict[str, LectureJob] = {}
        self._lock = threading.Lock()

    def create_job(self, source_url: str, options: Optional[Dict[str, Any]] = None) -> LectureJob:
        job_id = str(uuid.uuid4())[:12]
        job = LectureJob(job_id, source_url, options)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[LectureJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def start_job(self, job_id: str) -> None:
        """Launch background worker thread for the job."""
        thread = threading.Thread(target=self._process_pipeline, args=(job_id,), daemon=True)
        thread.start()

    def delete_slide(self, job_id: str, slide_id: int) -> bool:
        """Remove a slide specified by user and re-number remaining slides."""
        job = self.get_job(job_id)
        if not job:
            return False

        with self._lock:
            before_count = len(job.slides)
            job.slides = [s for s in job.slides if s["slide_id"] != slide_id]
            after_count = len(job.slides)
            
            # Re-index remaining slides
            for idx, s in enumerate(job.slides, start=1):
                s["slide_id"] = idx

        if before_count != after_count and job.status == "completed":
            # Automatically update the PDF with current curated slides
            self.rebuild_pdf(job_id)
            return True
        return False

    def rebuild_pdf(self, job_id: str) -> bool:
        """Regenerate final PDF for a job with currently curated slides."""
        job = self.get_job(job_id)
        if not job or not job.slides:
            return False

        pdf_output_path = os.path.join(job.job_dir, f"{job.job_id}_lecture_notes.pdf")
        try:
            generate_lecture_pdf(
                lecture_title=job.lecture_title,
                youtube_url=job.source_url,
                slides=job.slides,
                output_pdf_path=pdf_output_path,
                include_ocr=job.run_ocr
            )
            job.pdf_path = pdf_output_path
            return True
        except Exception as e:
            logger.error(f"Failed to rebuild PDF for job {job_id}: {e}")
            return False

    def _process_pipeline(self, job_id: str) -> None:
        """Complete, end-to-end processing pipeline."""
        job = self.get_job(job_id)
        if not job:
            return

        start_time = time.time()
        temp_video_path = None

        try:
            # ---------------------------------------------------------
            # STAGE 1: Acquire Video
            # ---------------------------------------------------------
            job.status = "downloading"
            job.progress_pct = 5
            job.stage_message = "Retrieving video stream / metadata..."

            # If input is already a local video file (e.g. from local test/upload)
            if os.path.exists(job.source_url):
                temp_video_path = job.source_url
                props = get_video_properties(temp_video_path)
                job.lecture_title = os.path.basename(temp_video_path)
                job.duration_sec = props["duration_sec"]
            else:
                # Validate URL
                if not is_valid_youtube_url(job.source_url):
                    raise ValueError("The provided link is not a recognized YouTube video URL.")

                try:
                    info = extract_video_info(job.source_url)
                    job.lecture_title = info.get("title", "Lecture Video")
                    job.duration_sec = info.get("duration", 0)
                except Exception as meta_err:
                    logger.warning(f"Could not fetch metadata ahead of download: {meta_err}")

                job.stage_message = f"Downloading video stream '{job.lecture_title[:35]}...' (lightweight stream)..."
                downloaded_file, meta = download_lecture_video(
                    job.source_url,
                    job.job_dir,
                    max_height=job.max_height
                )
                temp_video_path = downloaded_file
                if not job.lecture_title or job.lecture_title == "Lecture Video":
                    job.lecture_title = meta.get("title", "Lecture Video")
                if not job.duration_sec:
                    job.duration_sec = meta.get("duration", 0)

            job.stages_completed["video_loaded"] = True
            job.progress_pct = 20
            logger.info(f"[{job_id}] Video acquired: {temp_video_path} (Duration: {job.duration_sec:.1f}s)")

            # ---------------------------------------------------------
            # STAGE 2 & 3: Incremental Frame Sampling & Slide Detection
            # ---------------------------------------------------------
            job.status = "detecting"
            job.stages_completed["sampling_frames"] = True
            job.stage_message = "Scanning video frames & detecting slide transitions..."

            raw_candidate_segments: List[List[Dict[str, Any]]] = []
            current_segment: List[Dict[str, Any]] = []
            prev_frame = None
            ref_frame = None

            props = get_video_properties(temp_video_path)
            total_duration = props["duration_sec"] or job.duration_sec or 1.0

            sampled_count = 0
            for ts, frame, frame_idx in sample_frames_incremental(temp_video_path, interval_sec=job.sample_interval):
                sampled_count += 1
                job.total_frames_sampled = sampled_count

                # Update progress smoothly across 20% -> 60%
                pct = 20 + int(min(40.0, (ts / total_duration) * 40.0))
                job.progress_pct = min(60, pct)

                frame_entry = {
                    "timestamp": ts,
                    "frame": frame,
                    "frame_idx": frame_idx
                }

                if prev_frame is None:
                    # First sampled frame initiates slide #1 segment
                    current_segment.append(frame_entry)
                    prev_frame = frame
                    ref_frame = frame
                    continue

                # Compute difference metrics against both immediate predecessor and segment reference frame
                metrics_prev = calculate_frame_difference_metrics(prev_frame, frame)
                metrics_ref = calculate_frame_difference_metrics(ref_frame, frame) if ref_frame is not None else metrics_prev

                if is_slide_change(metrics_prev, sensitivity=job.sensitivity) or is_slide_change(metrics_ref, sensitivity=job.sensitivity):
                    # Transition event triggered: close current segment and begin new one
                    if current_segment:
                        raw_candidate_segments.append(current_segment)
                    current_segment = [frame_entry]
                    ref_frame = frame
                else:
                    # Same slide: buffer frame to analyze clarity/motion
                    # Keep at most 5 frames per segment to bound memory usage
                    if len(current_segment) < 5:
                        current_segment.append(frame_entry)
                    else:
                        # Replace last if current has higher sharpness
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        cur_sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                        last_gray = cv2.cvtColor(current_segment[-1]['frame'], cv2.COLOR_BGR2GRAY)
                        last_sharpness = float(cv2.Laplacian(last_gray, cv2.CV_64F).var())
                        if cur_sharpness > last_sharpness:
                            current_segment[-1] = frame_entry

                prev_frame = frame

            if current_segment:
                raw_candidate_segments.append(current_segment)

            if sampled_count == 0:
                raise ValueError(
                    "No video frames could be decoded. Please try another video format or contact the site owner."
                )

            job.stages_completed["detecting_slides"] = True
            job.candidate_slides_count = len(raw_candidate_segments)
            job.progress_pct = 65
            job.stage_message = f"Detected {len(raw_candidate_segments)} raw candidate slides. Selecting clearest frames..."

            # ---------------------------------------------------------
            # STAGE 4: Intelligent Frame Selection
            # ---------------------------------------------------------
            candidate_slides: List[Dict[str, Any]] = []
            for seg in raw_candidate_segments:
                best = select_best_frame(seg)
                candidate_slides.append(best)

            # ---------------------------------------------------------
            # STAGE 5: Duplicate Removal & Slide Saving
            # ---------------------------------------------------------
            job.status = "deduplicating"
            job.progress_pct = 70
            job.stage_message = "Removing duplicate slides and transitions..."

            unique_slides = filter_duplicate_slides(candidate_slides)
            job.stages_completed["deduplicating"] = True
            job.progress_pct = 75

            # Save unique slide images to disk as high quality PNGs
            saved_slides: List[Dict[str, Any]] = []
            for idx, item in enumerate(unique_slides, start=1):
                filename = f"slide_{idx:03d}_{int(item['timestamp'])}s.png"
                img_path = os.path.join(job.slides_dir, filename)
                cv2.imwrite(img_path, item['frame'])

                saved_slides.append({
                    "slide_id": idx,
                    "timestamp": item['timestamp'],
                    "timestamp_formatted": format_timestamp(item['timestamp']),
                    "filename": filename,
                    "image_path": img_path,
                    "sharpness": item.get('sharpness', 0.0),
                    "frame": item['frame'],  # Kept in memory temporarily for OCR
                    "ocr_text": ""
                })

            job.slides = saved_slides
            job.unique_slides_count = len(saved_slides)

            # Cleanup video file immediately to free disk space!
            if temp_video_path and os.path.exists(temp_video_path) and not temp_video_path.endswith("_demo_lecture.mp4"):
                remove_temp_video(temp_video_path)
                temp_video_path = None

            # ---------------------------------------------------------
            # STAGE 6: OCR Processing
            # ---------------------------------------------------------
            job.status = "ocr"
            job.progress_pct = 80
            if job.run_ocr and job.slides:
                job.stage_message = "Extracting text from slides using local OCR..."
                for idx, s in enumerate(job.slides, start=1):
                    ocr_res = extract_text_from_slide(s["frame"])
                    s["ocr_text"] = ocr_res.get("text", "")
                    if s["ocr_text"]:
                        job.ocr_count += 1
                    # Progress from 80% to 92%
                    job.progress_pct = 80 + int((idx / len(job.slides)) * 12)
            else:
                job.stage_message = "OCR text extraction skipped or disabled."

            job.stages_completed["running_ocr"] = True
            job.progress_pct = 92

            # Free OpenCV frames from RAM now that images are on disk and OCR is done
            for s in job.slides:
                if "frame" in s:
                    del s["frame"]

            # ---------------------------------------------------------
            # STAGE 7: PDF Generation
            # ---------------------------------------------------------
            job.status = "building_pdf"
            job.progress_pct = 95
            job.stage_message = "Compiling lecture notes PDF with ReportLab..."

            pdf_output_path = os.path.join(job.job_dir, f"{job.job_id}_lecture_notes.pdf")
            generate_lecture_pdf(
                lecture_title=job.lecture_title,
                youtube_url=job.source_url,
                slides=job.slides,
                output_pdf_path=pdf_output_path,
                include_ocr=job.run_ocr
            )
            job.pdf_path = pdf_output_path
            job.stages_completed["pdf_ready"] = True

            # Complete!
            job.status = "completed"
            job.progress_pct = 100
            job.processing_time_sec = time.time() - start_time
            job.stage_message = f"Processing finished successfully in {job.processing_time_sec:.1f}s! Found {len(job.slides)} unique slides."
            logger.info(f"[{job_id}] Processing completed successfully!")

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.stage_message = f"Processing error: {str(e)}"
            logger.exception(f"[{job_id}] Processing pipeline failure: {e}")
        finally:
            if temp_video_path and os.path.exists(temp_video_path) and not temp_video_path.endswith("_demo_lecture.mp4"):
                remove_temp_video(temp_video_path)


# Global singleton instance
job_manager = JobManager()
