# LectureSlide Notes

> **Turn lecture videos into organized, downloadable study notes.**  
> 100% Free and Open-Source Software (FOSS) • Zero API Keys • Zero Paid Subscriptions.

---

## 📌 Overview

**LectureSlide Notes** is a local computer-vision web application that takes a YouTube lecture URL (or uploaded lecture video) and automatically:

1. **Retrieves the video stream** incrementally via `yt-dlp`.
2. **Samples video frames** without loading the whole video into RAM.
3. **Detects slide and chalkboard changes** using Structural Similarity (SSIM), frame differencing, color histogram correlation, and edge divergence.
4. **Selects the clearest, sharpest representative frame** using Laplacian variance and occlusion scoring (filtering animations, motion blur, and teacher movement).
5. **Deduplicates repeated slides** using perceptual difference hashing (`dHash`) and SSIM.
6. **Extracts slide text locally** using Tesseract OCR (with graceful fallback if not installed).
7. **Presents an interactive preview grid** allowing students to review, inspect, and delete unwanted slides.
8. **Compiles a publication-quality PDF** containing timestamps, slide snapshots, and OCR transcripts using `ReportLab`.

---

## 🛡️ Cost & FOSS Audit (Zero Paid Dependencies)

This project strictly adheres to a **100% Free and Open-Source** mandate:

| Component | Technology | Cost / License | Paid Alternative Avoided |
| :--- | :--- | :--- | :--- |
| **Video Retrieval** | `yt-dlp` | Free / Unlicense | Paid video download / transcoding APIs |
| **Video Decoding** | `OpenCV` (`cv2`) | Free / Apache 2.0 | Paid Computer Vision cloud services |
| **Slide Detection** | SSIM / Frame Differencing / Canny | Free / Native Math & NumPy | OpenAI Vision API / Gemini API |
| **Frame Selection** | Laplacian Variance / Occlusion Filter | Free / OpenCV | Paid frame analysis pipelines |
| **Deduplication** | Perceptual Hashing (`dHash` / `aHash`) | Free / NumPy | Paid embedding vector databases |
| **OCR Text Extraction** | Tesseract OCR (`pytesseract`) | Free / Apache 2.0 | Google Cloud Vision / AWS Textract |
| **PDF Generation** | `ReportLab` Open Source | Free / BSD License | Adobe Document API / DocuSign |
| **Web Server** | `FastAPI` + `Uvicorn` | Free / MIT License | Paid serverless platforms |
| **Frontend UI** | HTML5 / CSS3 / Vanilla JavaScript | Free / Native Browser APIs | Paid UI component libraries |

---

## 🚀 Quick Start on Windows

### 1. Prerequisites
- **Python 3.10+** (Tested and verified up to Python 3.14 on Windows 64-bit).
- **Tesseract OCR (Optional)**: If you want automatic text transcription from slides:
  - Install via winget:
    ```powershell
    winget install --id UB-Mannheim.TesseractOCR
    ```
  - Or download the Windows installer from [UB-Mannheim Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
  - *Note: If Tesseract is not installed, the application continues to run normally, captures all slide frames, and generates the PDF with snapshots.*

### 2. Setup Virtual Environment

Open PowerShell or Command Prompt in the project directory:

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Install free and open-source dependencies
pip install -r requirements.txt
```

### 3. Start the Application

```powershell
# Start FastAPI backend server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 🧪 Automated Verification Suite

To verify all 10 core pipeline stages without needing internet access or YouTube downloads, run the automated verification script:

```powershell
python backend/tests/verify_pipeline.py
```

This test:
1. Validates YouTube URL parsing.
2. Generates a synthetic 5-slide physics lecture video with transitions and animated professor movement.
3. Incrementally samples frames.
4. Detects slide changes with computer vision.
5. Evaluates Laplacian sharpness and selects the best representative frames.
6. Deduplicates repeated slides via perceptual hashing (`dHash`).
7. Tests local OCR extraction.
8. Compiles a PDF and verifies the `%PDF-` binary format.
9. Validates asynchronous background job scheduling.
10. Verifies slide deletion curation and dynamic PDF re-generation.

---

## 🖥️ User Interface Features

- **Hero Input**: Paste any valid YouTube URL (e.g. `https://www.youtube.com/watch?v=...` or `https://youtu.be/...`).
- **Quick Test Buttons**: One-click fill for verified public MIT OpenCourseWare and educational lectures.
- **Built-in Synthetic Demo**: Click `⚡ Run Built-in Synthetic Demo` for an immediate 1.5-second end-to-end test.
- **Local File Upload**: Upload `.mp4`, `.webm`, or `.mkv` files directly for offline/private recordings.
- **Configurable Settings**:
  - Sampling interval (1.0s, 1.5s, 2.0s, 3.0s).
  - Sensitivity preset (Low, Medium, High).
  - OCR text extraction toggle.
- **Live Pipeline Checklist**: Visual progress tracking across all 6 processing stages.
- **Slide Preview Grid**:
  - High-resolution slide thumbnails with click-to-zoom modal.
  - Slide number and exact timestamp badges (clicking opens YouTube directly at that second).
  - Collapsible OCR transcript with one-click copy button.
  - Delete button (`🗑`) to discard false positives or blurry slides with instant PDF rebuild.
- **PDF Download**: One-click download of the complete study notes PDF.

---

## 📐 Architecture & Project Structure

```
lecture_slide_notes/
├── backend/
│   ├── main.py                     # FastAPI web server and REST API
│   ├── video/
│   │   └── video_processor.py       # yt-dlp downloader & incremental frame sampler
│   ├── vision/
│   │   ├── slide_detector.py        # SSIM, color histogram & edge change detection
│   │   ├── frame_selector.py        # Laplacian sharpness & occlusion evaluator
│   │   └── duplicate_detector.py    # dHash perceptual hashing & deduplication
│   ├── ocr/
│   │   └── ocr_processor.py         # Local Tesseract OCR with adaptive binarization
│   ├── pdf/
│   │   └── pdf_generator.py         # ReportLab lecture notes PDF builder
│   ├── services/
│   │   └── job_manager.py           # Background job manager & lifecycle coordinator
│   ├── utils/
│   │   └── demo_generator.py        # Synthetic multi-slide video generator
│   └── tests/
│       └── verify_pipeline.py       # End-to-end automated test suite
├── frontend/
│   ├── index.html                  # Responsive UI layout
│   ├── style.css                   # Modern CSS styling (Slate/Indigo theme)
│   └── app.js                      # Client polling, slide curation & PDF actions
├── data/                           # Local storage for temporary jobs and slides
├── requirements.txt                # 100% Free Python dependencies
├── .gitignore                      # Git ignore rules
└── README.md                       # Documentation & instructions
```

---

## 🔒 Privacy & Performance Guarantees

- **Zero Cloud Leakage**: Video frames and transcripts are processed 100% locally on your machine.
- **Bounded RAM Footprint**: Video streams are decoded incrementally frame-by-frame; multi-gigabyte videos are never buffered completely in RAM.
- **Disk Cleanup**: Temporary video files are automatically deleted immediately after frame extraction.

---

## 📄 License

Free and Open-Source Software under the MIT License.
