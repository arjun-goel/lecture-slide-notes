/**
 * LectureSlide Notes - Client Application
 * Handles YouTube submission, live progress polling, slide curation grid,
 * OCR inspection, and PDF downloading.
 */

let currentJobId = null;
let pollInterval = null;
let currentJobData = null;

// DOM Elements
const inputSection = document.getElementById("input-section");
const processingSection = document.getElementById("processing-section");
const resultsSection = document.getElementById("results-section");

const lectureForm = document.getElementById("lecture-form");
const urlInput = document.getElementById("youtube-url-input");
const processBtn = document.getElementById("process-btn");
const runDemoBtn = document.getElementById("run-demo-btn");
const uploadFileInput = document.getElementById("upload-file-input");

const sampleIntervalSelect = document.getElementById("sample-interval-select");
const sensitivitySelect = document.getElementById("sensitivity-select");
const ocrToggle = document.getElementById("ocr-toggle");

const lectureTitleDisplay = document.getElementById("lecture-title-display");
const stageStatusMsg = document.getElementById("stage-status-msg");
const progressBar = document.getElementById("progress-bar");
const progressPercentage = document.getElementById("progress-percentage");
const progressFramesStat = document.getElementById("progress-frames-stat");
const progressSlidesStat = document.getElementById("progress-slides-stat");

const finalLectureTitle = document.getElementById("final-lecture-title");
const finalLectureSource = document.getElementById("final-lecture-source");
const metricSlidesCount = document.getElementById("metric-slides-count");
const metricFramesSampled = document.getElementById("metric-frames-sampled");
const metricProcessingTime = document.getElementById("metric-processing-time");
const metricOcrCount = document.getElementById("metric-ocr-count");
const slidesGrid = document.getElementById("slides-grid");

const downloadPdfBtn = document.getElementById("download-pdf-btn");
const regeneratePdfBtn = document.getElementById("regenerate-pdf-btn");
const newLectureBtn = document.getElementById("new-lecture-btn");

const imageModal = document.getElementById("image-modal");
const modalImage = document.getElementById("modal-image");
const modalCaption = document.getElementById("modal-caption");
const modalCloseBtn = document.getElementById("modal-close-btn");
const modalBackdrop = document.getElementById("modal-backdrop");
const toast = document.getElementById("toast");
const tesseractStatusPill = document.getElementById("tesseract-status-pill");

// Stage step indicators
const stageSteps = {
  video_loaded: document.getElementById("step-video-loaded"),
  sampling_frames: document.getElementById("step-sampling-frames"),
  detecting_slides: document.getElementById("step-detecting-slides"),
  deduplicating: document.getElementById("step-deduplicating"),
  running_ocr: document.getElementById("step-running-ocr"),
  pdf_ready: document.getElementById("step-pdf-ready"),
};

// -------------------------------------------------------------
// Initialization & System Capabilities Check
// -------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  checkSystemStatus();
  setupEventListeners();
});

async function checkSystemStatus() {
  try {
    const res = await fetch("/api/system-status");
    if (res.ok) {
      const data = await res.json();
      if (data.tesseract_ocr && data.tesseract_ocr.installed) {
        tesseractStatusPill.textContent = "OCR: Ready (Tesseract)";
        tesseractStatusPill.className = "badge badge-success";
      } else {
        tesseractStatusPill.textContent = "OCR: Optional (Install Tesseract)";
        tesseractStatusPill.className = "badge badge-neutral";
        tesseractStatusPill.title = "Tesseract not in PATH. Slides will be captured, OCR will be omitted.";
      }
    }
  } catch (err) {
    console.warn("System status check notice:", err);
  }
}

function setupEventListeners() {
  // Submit YouTube URL
  lectureForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();
    if (!url) return;
    startProcessingJob({
      url: url,
      sample_interval: parseFloat(sampleIntervalSelect.value),
      sensitivity: sensitivitySelect.value,
      run_ocr: ocrToggle.checked
    });
  });

  // Example chip buttons
  document.querySelectorAll(".btn-chip[data-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      urlInput.value = btn.getAttribute("data-url");
      urlInput.focus();
    });
  });

  // Synthetic Demo Lecture button (instant offline test)
  runDemoBtn.addEventListener("click", async () => {
    try {
      showToast("Starting synthetic lecture demonstration...");
      showProcessingView("Physics 101: Newton's Laws of Motion (Demo Lecture)");

      const res = await fetch("/api/demo", { method: "POST" });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to start demo lecture.");
      }

      currentJobId = data.job.job_id;
      startPolling(currentJobId);
    } catch (err) {
      showToast(err.message, true);
      showInputView();
    }
  });

  // Upload local video file
  uploadFileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
      showToast(`Uploading ${file.name}...`);
      showProcessingView(`Uploading & Processing: ${file.name}`);

      const formData = new FormData();
      formData.append("file", file);
      formData.append("sample_interval", sampleIntervalSelect.value);
      formData.append("sensitivity", sensitivitySelect.value);
      formData.append("run_ocr", ocrToggle.checked);

      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to upload video.");
      }

      currentJobId = data.job.job_id;
      startPolling(currentJobId);
    } catch (err) {
      showToast(err.message, true);
      showInputView();
    }
  });

  // Download PDF
  downloadPdfBtn.addEventListener("click", () => {
    if (!currentJobId) return;
    window.location.href = `/api/jobs/${currentJobId}/download-pdf`;
  });

  // Regenerate PDF
  regeneratePdfBtn.addEventListener("click", async () => {
    if (!currentJobId) return;
    try {
      showToast("Rebuilding PDF with current slides...");
      const res = await fetch(`/api/jobs/${currentJobId}/generate-pdf`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showToast("PDF updated successfully!");
      } else {
        throw new Error(data.detail || "Failed to regenerate PDF.");
      }
    } catch (err) {
      showToast(err.message, true);
    }
  });

  // Process Another Lecture
  newLectureBtn.addEventListener("click", () => {
    stopPolling();
    currentJobId = null;
    currentJobData = null;
    urlInput.value = "";
    showInputView();
  });

  // Modal close
  modalCloseBtn.addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

// -------------------------------------------------------------
// Job Dispatch & Polling
// -------------------------------------------------------------
async function startProcessingJob(payload) {
  try {
    showToast("Initializing video download & analysis...");
    showProcessingView("Retrieving lecture stream...");

    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Error starting video analysis.");
    }

    currentJobId = data.job.job_id;
    startPolling(currentJobId);
  } catch (err) {
    showToast(err.message, true);
    showInputView();
  }
}

function startPolling(jobId) {
  stopPolling();
  // Poll immediately and then every 1000ms
  pollJobStatus(jobId);
  pollInterval = setInterval(() => pollJobStatus(jobId), 1000);
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

async function pollJobStatus(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) {
      throw new Error("Failed to fetch job updates.");
    }

    const job = await res.json();
    currentJobData = job;

    // Update Progress Header & Bar
    if (job.lecture_title && job.lecture_title !== "Lecture Video") {
      lectureTitleDisplay.textContent = job.lecture_title;
    }
    stageStatusMsg.textContent = job.stage_message;

    const pct = Math.max(5, Math.min(100, job.progress_pct || 0));
    progressBar.style.width = `${pct}%`;
    progressPercentage.textContent = `${pct}%`;

    progressFramesStat.textContent = `Sampled frames: ${job.total_frames_sampled || 0}`;
    progressSlidesStat.textContent = `Detected slides: ${job.candidate_slides_count || 0}`;

    // Update Stages Checklist
    updateStageChecklist(job.stages_completed, job.status);

    // Completion Handlers
    if (job.status === "completed") {
      stopPolling();
      showToast("Lecture processing completed!");
      renderResults(job);
    } else if (job.status === "failed") {
      stopPolling();
      const errorMsg = job.error_message || "Something went wrong while processing this lecture.";
      showToast(errorMsg, true);
      alert(`Lecture Processing Error:\n\n${errorMsg}\n\nPlease verify that the YouTube video is publicly accessible.`);
      showInputView();
    }
  } catch (err) {
    console.error("Polling error:", err);
  }
}

function updateStageChecklist(stages, status) {
  if (!stages) return;

  const order = [
    "video_loaded",
    "sampling_frames",
    "detecting_slides",
    "deduplicating",
    "running_ocr",
    "pdf_ready"
  ];

  let firstIncompleteFound = false;

  order.forEach((stepKey) => {
    const el = stageSteps[stepKey];
    if (!el) return;

    if (stages[stepKey]) {
      el.className = "stage-step completed";
    } else if (!firstIncompleteFound && status !== "failed") {
      el.className = "stage-step active";
      firstIncompleteFound = true;
    } else {
      el.className = "stage-step";
    }
  });
}

// -------------------------------------------------------------
// Results & Slide Grid Rendering
// -------------------------------------------------------------
function renderResults(job) {
  inputSection.classList.add("hidden");
  processingSection.classList.add("hidden");
  resultsSection.classList.remove("hidden");

  finalLectureTitle.textContent = job.lecture_title;
  finalLectureSource.textContent = `Source: ${job.source_url} (${job.duration_formatted || ""})`;

  metricSlidesCount.textContent = job.slides ? job.slides.length : 0;
  metricFramesSampled.textContent = job.total_frames_sampled || 0;
  metricProcessingTime.textContent = `${job.processing_time_sec || 0}s`;
  metricOcrCount.textContent = job.ocr_count || 0;

  renderSlidesGrid(job.slides, job.source_url);
}

function renderSlidesGrid(slides, sourceUrl) {
  slidesGrid.innerHTML = "";

  if (!slides || slides.length === 0) {
    slidesGrid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: #64748b;">
        <p>No unique slides were detected in this video segment.</p>
      </div>
    `;
    return;
  }

  slides.forEach((slide) => {
    const card = document.createElement("div");
    card.className = "slide-card";
    card.id = `slide-card-${slide.slide_id}`;

    // Construct YouTube timestamp link if applicable
    let ytTimestampUrl = "#";
    if (sourceUrl.includes("youtube.com") || sourceUrl.includes("youtu.be")) {
      const cleanUrl = sourceUrl.split("&t=")[0];
      const delim = cleanUrl.includes("?") ? "&" : "?";
      ytTimestampUrl = `${cleanUrl}${delim}t=${Math.floor(slide.timestamp)}s`;
    }

    const ocrSnippet = slide.ocr_text ? slide.ocr_text.trim() : "";
    const hasOcr = Boolean(ocrSnippet);

    card.innerHTML = `
      <div class="slide-thumbnail-wrap" title="Click to enlarge slide">
        <img class="slide-thumbnail" src="${slide.image_url}" alt="Slide ${slide.slide_id}" loading="lazy" />
        <div class="slide-badges-overlay">
          <span class="slide-number-badge">Slide ${String(slide.slide_id).padStart(2, '0')}</span>
          <a href="${ytTimestampUrl}" target="_blank" rel="noopener noreferrer" class="timestamp-badge" title="Open YouTube at this timestamp">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span>${slide.timestamp_formatted}</span>
          </a>
        </div>
      </div>

      <div class="slide-card-body">
        <div class="slide-meta-row">
          <span class="slide-sharpness">Sharpness: ${slide.sharpness}</span>
          <button type="button" class="btn-icon-danger" title="Remove slide from PDF notes" data-delete-id="${slide.slide_id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>

        <div class="ocr-drawer">
          <div class="ocr-drawer-header">
            <span class="ocr-title">OCR Text</span>
            ${hasOcr ? `<button type="button" class="btn-copy-ocr" data-copy-id="${slide.slide_id}">Copy</button>` : ""}
          </div>
          <div class="ocr-text-content ${hasOcr ? '' : 'ocr-text-empty'}">
            ${hasOcr ? escapeHtml(ocrSnippet) : "No text transcribed on this slide."}
          </div>
        </div>
      </div>
    `;

    // Click thumbnail to zoom modal
    const thumbWrap = card.querySelector(".slide-thumbnail-wrap");
    thumbWrap.addEventListener("click", () => {
      openModal(slide.image_url, `Slide ${slide.slide_id} • ${slide.timestamp_formatted}`);
    });

    // Delete slide button
    const deleteBtn = card.querySelector(`[data-delete-id="${slide.slide_id}"]`);
    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSlide(slide.slide_id);
    });

    // Copy OCR text button
    if (hasOcr) {
      const copyBtn = card.querySelector(`[data-copy-id="${slide.slide_id}"]`);
      copyBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(ocrSnippet).then(() => {
          showToast(`Copied Slide #${slide.slide_id} text to clipboard!`);
        });
      });
    }

    slidesGrid.appendChild(card);
  });
}

async function deleteSlide(slideId) {
  if (!confirm(`Are you sure you want to remove Slide #${slideId}? It will be removed from your final PDF.`)) {
    return;
  }

  try {
    showToast(`Removing slide #${slideId}...`);
    const res = await fetch(`/api/jobs/${currentJobId}/delete-slide/${slideId}`, {
      method: "POST"
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Failed to remove slide.");
    }

    showToast(`Slide #${slideId} removed and PDF updated!`);
    currentJobData = data.job;
    renderResults(data.job);
  } catch (err) {
    showToast(err.message, true);
  }
}

// -------------------------------------------------------------
// UI View Transitions & Helpers
// -------------------------------------------------------------
function showInputView() {
  inputSection.classList.remove("hidden");
  processingSection.classList.add("hidden");
  resultsSection.classList.add("hidden");
}

function showProcessingView(title) {
  inputSection.classList.add("hidden");
  processingSection.classList.remove("hidden");
  resultsSection.classList.add("hidden");

  lectureTitleDisplay.textContent = title || "Processing Lecture...";
  stageStatusMsg.textContent = "Beginning pipeline execution...";
  progressBar.style.width = "5%";
  progressPercentage.textContent = "5%";

  Object.values(stageSteps).forEach((el) => {
    el.className = "stage-step";
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openModal(imgSrc, caption) {
  modalImage.src = imgSrc;
  modalCaption.textContent = caption || "";
  imageModal.classList.remove("hidden");
}

function closeModal() {
  imageModal.classList.add("hidden");
  modalImage.src = "";
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.style.backgroundColor = isError ? "#dc2626" : "#0f172a";
  toast.classList.remove("hidden");

  setTimeout(() => {
    toast.classList.add("hidden");
  }, 4000);
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
