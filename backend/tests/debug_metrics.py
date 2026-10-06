import os, sys
sys.path.insert(0, ".")
from backend.video.video_processor import sample_frames_incremental
from backend.vision.slide_detector import calculate_frame_difference_metrics, is_slide_change

video_path = "data/test_verification/test_lecture.mp4"
frames = list(sample_frames_incremental(video_path, 1.0))
print(f"Total sampled frames: {len(frames)}")

prev = None
for ts, f, idx in frames:
    if prev is not None:
        m = calculate_frame_difference_metrics(prev, f)
        chg = is_slide_change(m, "medium")
        print(f"t={ts:4.1f}s | score={m['combined_change_score']:.3f} | ssim={m['ssim']:.3f} | pixel_diff={m['pixel_diff']:.3f} | hist={m['hist_sim']:.3f} | chg={chg}")
    prev = f
