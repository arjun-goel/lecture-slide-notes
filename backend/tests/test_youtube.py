import sys
sys.path.insert(0, ".")
from backend.video.video_processor import extract_video_info

test_url = "https://www.youtube.com/watch?v=fNKuz4kg58U"
print("Connecting to YouTube via yt-dlp...")
try:
    info = extract_video_info(test_url)
    print("[PASS] Successfully fetched YouTube metadata:")
    print("Title:", info["title"])
    print("Duration:", info["duration"], "seconds")
    print("Uploader:", info["uploader"])
except Exception as e:
    print("[NOTE] YouTube network note:", e)
