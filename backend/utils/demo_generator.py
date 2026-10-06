"""
Demo Generator Utility for LectureSlide Notes.
Creates a synthetic multi-slide lecture MP4 video with real typography,
transitions, formulas, and simulated lecturer movement.
Used for instant offline testing and automated verification.
"""

import os
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


def create_synthetic_lecture_video(output_mp4_path: str, width: int = 800, height: int = 450, fps: int = 20) -> str:
    """
    Renders a realistic 20-second lecture video consisting of:
    - Slide 1: Introduction to Physics & Motion (4 seconds)
    - Transition fade to Slide 2 (1 second)
    - Slide 2: Newton's First Law with professor moving across (5 seconds)
    - Slide 3: Newton's Second Law & Formula (5 seconds)
    - Slide 4: Summary Slide (identical to Slide 1 to test deduplication!) (3 seconds)
    - Slide 5: Q&A / Discussion (2 seconds)
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_mp4_path)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_mp4_path, fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError("OpenCV VideoWriter failed to open MP4 destination.")

    def make_slide_bg(title: str, subtitle: str, body_lines: list, bg_color=(245, 247, 250)):
        # Canvas
        img = np.full((height, width, 3), bg_color, dtype=np.uint8)
        
        # Header banner
        cv2.rectangle(img, (0, 0), (width, 70), (79, 70, 229), -1)  # Indigo
        cv2.putText(img, "PHYSICS 101: CLASSICAL MECHANICS", (30, 45),
                    cv2.FONT_HERSHEY_DUPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

        # Slide Title
        cv2.putText(img, title, (40, 120),
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, (15, 23, 42), 2, cv2.LINE_AA)
        
        # Subtitle
        cv2.putText(img, subtitle, (40, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 116, 139), 1, cv2.LINE_AA)
        
        cv2.line(img, (40, 165), (width - 40, 165), (203, 213, 225), 1, cv2.LINE_AA)

        # Body Text
        y = 210
        for line in body_lines:
            cv2.putText(img, f"*  {line}", (50, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 41, 59), 1, cv2.LINE_AA)
            y += 45

        # Footer
        cv2.putText(img, "Department of Applied Mathematics & Physics", (40, height - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (148, 163, 184), 1, cv2.LINE_AA)
        return img

    slide1 = make_slide_bg(
        "Lecture 04: Newton's Laws of Motion",
        "Professor J. Reynolds -- Principles of Classical Dynamics",
        [
            "Fundamental Principles of Inertia and Acceleration",
            "Vector Analysis of Net Applied Forces",
            "Conservation of Linear Momentum in Closed Systems",
            "Mathematical Formulations and Calculus Proofs"
        ]
    )

    slide2 = make_slide_bg(
        "Newton's First Law: The Law of Inertia",
        "Every body perseveres in its state of rest or uniform motion.",
        [
            "An object at rest stays at rest unless acted upon by force.",
            "An object in motion continues with constant velocity.",
            "Inertial Reference Frames: No fictitious forces.",
            "Sigma F = 0 implies acceleration a = 0."
        ]
    )

    slide3 = make_slide_bg(
        "Newton's Second Law: Fundamental Force Equation",
        "Rate of change of momentum is proportional to the impressed force.",
        [
            "Mathematical formulation: F = m * a",
            "Force is a vector: F_net = m * (dv / dt)",
            "SI Units: 1 Newton (N) = 1 kg * m / s^2",
            "Free body diagram resolution along Cartesian axes"
        ]
    )

    # Slide 4 is intentionally identical to slide 1 (to test duplicate detection!)
    slide4 = slide1.copy()

    slide5 = make_slide_bg(
        "Summary & Assignment 4 Questions",
        "Review of concepts before the problem solving session",
        [
            "Reading Chapter 5 in Halliday and Resnick",
            "Problem Set 4 due next Tuesday at 11:59 PM",
            "Office hours on Wednesday in Hall 302"
        ]
    )

    # Write frames:
    # 1. Slide 1 for 4 seconds (80 frames)
    for _ in range(int(fps * 4.0)):
        writer.write(slide1)

    # 2. Fade transition from Slide 1 to Slide 2 (1 second, 20 frames)
    for alpha_step in range(20):
        w2 = alpha_step / 20.0
        w1 = 1.0 - w2
        blended = cv2.addWeighted(slide1, w1, slide2, w2, 0)
        writer.write(blended)

    # 3. Slide 2 for 5 seconds (100 frames) with simulated professor walking in front (left to right)
    for f in range(int(fps * 5.0)):
        frame = slide2.copy()
        # Draw a simulated lecturer avatar moving along the bottom right
        avatar_x = int(550 + np.sin(f * 0.1) * 60)
        cv2.circle(frame, (avatar_x, height - 90), 30, (70, 60, 50), -1)  # Head
        cv2.rectangle(frame, (avatar_x - 25, height - 60), (avatar_x + 25, height), (50, 45, 40), -1)  # Body
        writer.write(frame)

    # 4. Slide 3 for 5 seconds (100 frames)
    for _ in range(int(fps * 5.0)):
        writer.write(slide3)

    # 5. Slide 4 (Duplicate of Slide 1) for 3 seconds (60 frames)
    for _ in range(int(fps * 3.0)):
        writer.write(slide4)

    # 6. Slide 5 for 2.5 seconds (50 frames)
    for _ in range(int(fps * 2.5)):
        writer.write(slide5)

    writer.release()
    logger.info(f"Synthetic test lecture video created successfully at: {output_mp4_path}")
    return output_mp4_path
