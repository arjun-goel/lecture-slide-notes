"""
Live Server API Integration Test for LectureSlide Notes.
Tests the running web server and all HTTP endpoints.
"""

import time
import requests

BASE_URL = "http://127.0.0.1:8000"


def test_live_server():
    print("=" * 65)
    print("TESTING LECTURESLIDE NOTES LIVE SERVER ENDPOINTS")
    print("=" * 65)

    # 1. Test Static Frontend Files
    print("\n[1] Testing frontend static file serving...")
    r_index = requests.get(f"{BASE_URL}/")
    assert r_index.status_code == 200, f"Expected 200, got {r_index.status_code}"
    assert "LectureSlide Notes" in r_index.text, "Index HTML missing title"
    print("  [PASS] GET / returned valid HTML with brand title.")

    r_css = requests.get(f"{BASE_URL}/style.css")
    assert r_css.status_code == 200, "Failed to fetch style.css"
    print("  [PASS] GET /style.css served successfully.")

    r_js = requests.get(f"{BASE_URL}/app.js")
    assert r_js.status_code == 200, "Failed to fetch app.js"
    print("  [PASS] GET /app.js served successfully.")

    # 2. Test System Status Endpoint
    print("\n[2] Testing /api/system-status...")
    r_status = requests.get(f"{BASE_URL}/api/system-status")
    assert r_status.status_code == 200
    status_data = r_status.json()
    assert status_data["open_source_compliant"] is True
    assert status_data["paid_apis_used"] is False
    print(f"  [PASS] FOSS compliance verified (Paid APIs: {status_data['paid_apis_used']}, Python: {status_data['python_version']}).")

    # 3. Test Invalid URL Handling (Graceful Error, No Stack Trace)
    print("\n[3] Testing invalid URL error handling...")
    r_invalid = requests.post(f"{BASE_URL}/api/process", json={"url": "https://invalid-website.com/test"})
    assert r_invalid.status_code == 400
    err_json = r_invalid.json()
    assert "Please enter a valid YouTube video URL" in err_json["detail"]
    print(f"  [PASS] Invalid URL rejected with user-friendly message: '{err_json['detail']}'")

    # 4. Trigger Synthetic Lecture Demo Job
    print("\n[4] Triggering synthetic lecture job via POST /api/demo...")
    r_demo = requests.post(f"{BASE_URL}/api/demo")
    assert r_demo.status_code == 200, f"Failed to start demo: {r_demo.text}"
    job_info = r_demo.json()["job"]
    job_id = job_info["job_id"]
    print(f"  [PASS] Demo job created with ID: {job_id}")

    # 5. Poll Job Progress
    print(f"\n[5] Polling job updates for {job_id}...")
    start_time = time.time()
    final_job = None
    while time.time() - start_time < 30:
        r_poll = requests.get(f"{BASE_URL}/api/jobs/{job_id}")
        assert r_poll.status_code == 200
        data = r_poll.json()
        print(f"  Status: {data['status']:<12} | Progress: {data['progress_pct']:>3}% | Stage: {data['stage_message'][:40]}...")
        if data["status"] in ("completed", "failed"):
            final_job = data
            break
        time.sleep(1.0)

    assert final_job is not None, "Job timed out."
    assert final_job["status"] == "completed", f"Job failed: {final_job.get('error_message')}"
    slides = final_job["slides"]
    assert len(slides) > 0, "No slides produced."
    print(f"  [PASS] Job completed! Found {len(slides)} unique slides in {final_job['processing_time_sec']}s.")

    # 6. Verify Slide Image Serving
    print("\n[6] Verifying slide image serving endpoint...")
    first_slide = slides[0]
    img_url = f"{BASE_URL}{first_slide['image_url']}"
    r_img = requests.get(img_url)
    assert r_img.status_code == 200, f"Failed to load slide image at {img_url}"
    assert len(r_img.content) > 1000, "Slide image content too small."
    print(f"  [PASS] Slide image served successfully ({len(r_img.content)} bytes, PNG).")

    # 7. Verify PDF Download Endpoint
    print("\n[7] Verifying PDF download endpoint...")
    pdf_url = f"{BASE_URL}/api/jobs/{job_id}/download-pdf"
    r_pdf = requests.get(pdf_url)
    assert r_pdf.status_code == 200, f"Failed to download PDF: {r_pdf.status_code}"
    assert r_pdf.headers.get("content-type") == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF-"), "Invalid PDF binary format."
    print(f"  [PASS] PDF downloaded successfully ({len(r_pdf.content)} bytes, valid %PDF-).")

    # 8. Test Slide Deletion & Dynamic PDF Update
    print("\n[8] Testing slide curation deletion & auto PDF rebuild...")
    initial_slide_count = len(slides)
    r_del = requests.post(f"{BASE_URL}/api/jobs/{job_id}/delete-slide/1")
    assert r_del.status_code == 200, f"Delete failed: {r_del.text}"
    updated_job = r_del.json()["job"]
    assert len(updated_job["slides"]) == initial_slide_count - 1
    print(f"  [PASS] Slide #1 deleted. Slide count updated from {initial_slide_count} to {len(updated_job['slides'])}.")

    # Verify updated PDF download
    r_pdf_updated = requests.get(pdf_url)
    assert r_pdf_updated.status_code == 200
    assert r_pdf_updated.content.startswith(b"%PDF-")
    print("  [PASS] Updated PDF verified after curation.")

    print("\n" + "=" * 65)
    print("ALL LIVE SERVER INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    test_live_server()
