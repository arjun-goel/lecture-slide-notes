# Use official Python slim image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies: tesseract-ocr, ffmpeg, and build libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and grant write permissions for non-root cloud containers (e.g. Hugging Face Spaces)
COPY . .
RUN mkdir -p /app/data/jobs && chmod -R 777 /app

# Support dynamic PORT from cloud hosting providers (Hugging Face defaults to 7860, Render injects PORT)
ENV PORT=7860
EXPOSE 7860

# Start server reading PORT environment variable
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
