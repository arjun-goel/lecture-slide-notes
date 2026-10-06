"""
LectureSlide Notes - Main Backend Application
FastAPI web server exposing REST endpoints for lecture video processing,
slide detection, deduplication, OCR inspection, and PDF downloading.
"""

import os
import sys
import shutil
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.services.job_manager import job_manager, WORKSPACE_DIR
from backend.video.video_processor import is_valid_youtube_url
from backend.ocr.ocr_processor import find_tesseract_binary
from backend.utils.demo_generator import create_synthetic_lecture_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("LectureSlideNotes")

app = FastAPI(
    title="LectureSlide Notes API",
    description="FOSS AI & Computer Vision pipeline turning YouTube lecture videos into organized study notes and PDF documents.",
    version="1.0.0"
)

# Enable CORS for local development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessRequest(BaseModel):
    url: str = Field(..., description="YouTube video URL or direct video URL")
    sample_interval: float = Field(1.5, ge=0.5, le=10.0, description="Seconds between sampled frames")
    sensitivity: str = Field("medium", description="Slide transition sensitivity: low, medium, or high")
    run_ocr: bool = Field(True, description="Whether to extract text via local Tesseract OCR")
    max_height: int = Field(720, ge=360, le=1080, description="Max stream resolution height")


@app.get("/api/system-status")
def get_system_status():
    """Verify local FOSS tools and system capabilities."""
    tesseract_path = find_tesseract_binary()
    return {
        "status": "ready",
        "python_version": sys.version.split()[0],
        "open_source_compliant": True,
        "paid_apis_used": False,
        "tesseract_ocr": {
            "installed": bool(tesseract_path),
            "binary_path": tesseract_path,
            "note": "Local Tesseract OCR available" if tesseract_path else "Tesseract OCR binary not detected on PATH (OCR text will be omitted, slides and PDF still generated)"
        },
        "workspace_dir": WORKSPACE_DIR
    }


@app.post("/api/process")
def process_lecture(payload: ProcessRequest):
    """
    Initiate processing of a YouTube lecture URL.
    Validates URL format and begins asynchronous computer vision pipeline.
    """
    url = payload.url.strip()
    if not is_valid_youtube_url(url):
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid YouTube video URL (e.g. https://www.youtube.com/watch?v=... or https://youtu.be/...)"
        )

    job = job_manager.create_job(
        source_url=url,
        options={
            "sample_interval": payload.sample_interval,
            "sensitivity": payload.sensitivity,
            "run_ocr": payload.run_ocr,
            "max_height": payload.max_height
        }
    )

    # Launch background processing pipeline
    job_manager.start_job(job.job_id)

    return {
        "status": "success",
        "message": "Lecture processing initialized.",
        "job": job.to_dict()
    }


@app.post("/api/upload")
async def upload_local_lecture(
    file: UploadFile = File(...),
    sample_interval: float = 1.5,
    sensitivity: str = "medium",
    run_ocr: bool = True
):
    """
    Upload a local video file (MP4, MKV, WebM, AVI) to process directly.
    Ideal for local lectures, private recordings, and offline testing.
    """
    if not file.filename.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov')):
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload an MP4, MKV, or WebM video.")

    temp_upload_dir = os.path.join(WORKSPACE_DIR, "uploads")
    os.makedirs(temp_upload_dir, exist_ok=True)
    saved_path = os.path.join(temp_upload_dir, file.filename)

    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    job = job_manager.create_job(
        source_url=saved_path,
        options={
            "sample_interval": sample_interval,
            "sensitivity": sensitivity,
            "run_ocr": run_ocr
        }
    )
    job.lecture_title = file.filename

    job_manager.start_job(job.job_id)

    return {
        "status": "success",
        "message": f"Uploaded file '{file.filename}' queued for processing.",
        "job": job.to_dict()
    }


@app.post("/api/demo")
def run_demo_lecture():
    """
    Generates a synthetic 5-slide physics lecture video and processes it
    through the complete pipeline (detection, deduplication, OCR, PDF).
    Enables instant offline testing and demonstration!
    """
    demo_dir = os.path.join(WORKSPACE_DIR, "demo")
    os.makedirs(demo_dir, exist_ok=True)
    demo_video_path = os.path.join(demo_dir, "newtons_laws_demo_lecture.mp4")

    # Generate synthetic video if not exists
    create_synthetic_lecture_video(demo_video_path)

    job = job_manager.create_job(
        source_url=demo_video_path,
        options={
            "sample_interval": 1.0,
            "sensitivity": "medium",
            "run_ocr": True
        }
    )
    job.lecture_title = "Physics 101: Newton's Laws of Motion (Sample Lecture)"

    job_manager.start_job(job.job_id)

    return {
        "status": "success",
        "message": "Demo lecture created and started.",
        "job": job.to_dict()
    }


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    """Retrieve live processing status, progress percentage, and detected slides."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Lecture job not found.")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/delete-slide/{slide_id}")
def delete_slide_from_job(job_id: str, slide_id: int):
    """
    Remove an unwanted or false-positive slide from the preview list.
    Automatically regenerates the updated lecture PDF document.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Lecture job not found.")

    deleted = job_manager.delete_slide(job_id, slide_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Slide could not be removed or invalid slide ID.")

    return {
        "status": "success",
        "message": f"Slide #{slide_id} deleted and PDF updated.",
        "job": job.to_dict()
    }


@app.post("/api/jobs/{job_id}/generate-pdf")
def regenerate_pdf(job_id: str):
    """Rebuild the final PDF with current slide selection."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Lecture job not found.")

    success = job_manager.rebuild_pdf(job_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to compile PDF.")

    return {
        "status": "success",
        "message": "PDF updated successfully.",
        "pdf_available": True
    }


@app.get("/api/jobs/{job_id}/download-pdf")
def download_pdf(job_id: str):
    """Download the compiled lecture notes PDF."""
    job = job_manager.get_job(job_id)
    if not job or not job.pdf_path or not os.path.exists(job.pdf_path):
        raise HTTPException(status_code=404, detail="PDF has not been generated for this job yet.")

    safe_title = "".join(c for c in job.lecture_title if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_title = safe_title.replace(" ", "_")[:40] or "lecture_notes"
    filename = f"{safe_title}_slides.pdf"

    return FileResponse(
        path=job.pdf_path,
        media_type="application/pdf",
        filename=filename
    )


@app.get("/api/jobs/{job_id}/slides/{filename}")
def get_slide_image(job_id: str, filename: str):
    """Serve a captured slide screenshot."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    image_path = os.path.join(job.slides_dir, filename)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Slide image file not found.")

    return FileResponse(image_path, media_type="image/png")


# Mount frontend static directory
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
