Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Starting LectureSlide Notes Web Application..." -ForegroundColor Green
Write-Host "Open http://127.0.0.1:8000 in your browser." -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
