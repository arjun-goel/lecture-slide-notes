"""
Video Processor Module for LectureSlide Notes.
Handles fetching YouTube video streams/files via yt-dlp and
sampling video frames incrementally via OpenCV without filling system memory.
"""

import os
import re
import cv2
import yt_dlp
import logging
import shutil
import subprocess
from typing import Generator, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)

YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/live/)[a-zA-Z0-9_\-]{6,}'
)


def is_valid_youtube_url(url: str) -> bool:
    """Validate if the string is a recognized YouTube video URL format."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return bool(YOUTUBE_URL_REGEX.search(url))


def extract_video_info(url: str) -> Dict[str, Any]:
    """
    Extract video metadata (title, duration, thumbnail, author)
    without downloading the entire video stream.
    """
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not extract video metadata.")
            return {
                "title": info.get("title", "Lecture Video"),
                "duration": int(info.get("duration", 0) or 0),
                "uploader": info.get("uploader", "Unknown Uploader"),
                "thumbnail": info.get("thumbnail", ""),
                "description": (info.get("description", "") or "")[:200]
            }
    except Exception as e:
        logger.error(f"Failed to extract video info: {e}")
        raise RuntimeError(f"Unable to access video metadata: {str(e)}")


def download_lecture_video(url: str, target_dir: str, max_height: int = 720) -> Tuple[str, Dict[str, Any]]:
    """
    Download video stream at a lightweight resolution (e.g., <=720p or 480p)
    using yt-dlp. Downloads single-file mp4 without requiring ffmpeg post-merge.
    """
    os.makedirs(target_dir, exist_ok=True)
    out_tmpl = os.path.join(target_dir, "lecture_source.%(ext)s")

    # Target lightweight mp4 to minimize download time, bandwidth, and processing CPU
    # Prioritizes direct mp4 stream so no post-processing ffmpeg merge is required
    ydl_opts = {
        'format': f'best[ext=mp4][height<={max_height}]/best[height<={max_height}]/best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'overwrites': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise ValueError("Failed to retrieve video stream.")
            
            downloaded_path = ydl.prepare_filename(info)
            # If extension differed (e.g. mkv/webm), locate the file
            if not os.path.exists(downloaded_path):
                for f in os.listdir(target_dir):
                    if f.startswith("lecture_source."):
                        downloaded_path = os.path.join(target_dir, f)
                        break

            metadata = {
                "title": info.get("title", "Lecture Video"),
                "duration": int(info.get("duration", 0) or 0),
                "uploader": info.get("uploader", "Unknown Uploader"),
                "thumbnail": info.get("thumbnail", ""),
            }

            return downloaded_path, metadata
    except Exception as e:
        logger.error(f"Video download failed: {e}")
        raise RuntimeError(f"Could not download lecture video: {str(e)}")


def get_video_properties(video_path: str) -> Dict[str, Any]:
    """Read basic video dimensions, FPS, and total duration using OpenCV."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration_sec = total_frames / fps if fps > 0 else 0
    cap.release()

    return {
        "fps": fps,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "duration_sec": duration_sec
    }


def sample_frames_incremental(
    video_path: str,
    interval_sec: float = 1.5,
    max_duration_sec: Optional[float] = None
) -> Generator[Tuple[float, Any, int], None, None]:
    """
    Incrementally stream video frames sampled every `interval_sec` seconds.
    Yields (timestamp_seconds, frame_bgr, frame_index).
    Does NOT load the entire video into RAM!
    """
    processing_path = video_path
    fallback_path: Optional[str] = None

    # OpenCV's bundled decoder cannot read every browser-created MP4. In
    # particular, cloud containers often fail on AV1 uploads even though they
    # can still read the file metadata. Normalise only those files that fail a
    # real frame decode, keeping ordinary H.264 uploads fast.
    probe = cv2.VideoCapture(video_path)
    can_decode = probe.isOpened()
    if can_decode:
        can_decode, _ = probe.read()
    probe.release()

    if not can_decode:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise ValueError(
                "This video codec is not supported by the server and FFmpeg is unavailable to convert it."
            )

        stem, _ = os.path.splitext(video_path)
        fallback_path = f"{stem}_opencv_compatible.mp4"
        command = [
            ffmpeg_path, "-y", "-i", video_path,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-c:a", "aac", "-movflags", "+faststart", fallback_path,
        ]
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Video conversion timed out after 10 minutes.") from exc

        if completed.returncode != 0 or not os.path.exists(fallback_path):
            detail = (completed.stderr or "unknown FFmpeg error").splitlines()[-1:]
            raise ValueError(f"Could not convert this video to a readable format: {' '.join(detail)}")

        processing_path = fallback_path
        logger.info("Converted unsupported video codec to H.264 for OpenCV processing: %s", video_path)

    cap = cv2.VideoCapture(processing_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {processing_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25.0

    step_frames = max(1, int(round(fps * interval_sec)))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    
    current_frame_idx = 0

    try:
        while True:
            # Check frame index bounds
            if total_frames > 0 and current_frame_idx >= total_frames:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            timestamp_sec = current_frame_idx / fps
            if max_duration_sec and timestamp_sec > max_duration_sec:
                break

            yield (timestamp_sec, frame, current_frame_idx)
            current_frame_idx += step_frames
    finally:
        cap.release()
        if fallback_path and os.path.exists(fallback_path):
            try:
                os.remove(fallback_path)
            except OSError:
                logger.warning("Could not remove temporary converted video: %s", fallback_path)


def remove_temp_video(video_path: str) -> None:
    """Delete temporary video file to reclaim disk space after frame sampling."""
    try:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Cleaned up temporary video file: {video_path}")
    except Exception as e:
        logger.warning(f"Failed to delete temporary video file {video_path}: {e}")
