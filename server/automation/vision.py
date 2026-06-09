#!/usr/bin/env python3
import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from server.config import (
        HSV_RANGES,
        CAMERA_INDEX,
        FRAME_WIDTH,
        FRAME_HEIGHT,
        MIN_AREA,
        MAX_AREA_RATIO,
        MIN_FILL_RATIO,
        MIN_CONFIDENCE,
        STABLE_FRAMES,
        CAMERA_WARMUP_FRAMES,
        PROCESS_EVERY,
        PREVIEW_SCALE,
    )
except ModuleNotFoundError:
    from config import (
        HSV_RANGES,
        CAMERA_INDEX,
        FRAME_WIDTH,
        FRAME_HEIGHT,
        MIN_AREA,
        MAX_AREA_RATIO,
        MIN_FILL_RATIO,
        MIN_CONFIDENCE,
        STABLE_FRAMES,
        CAMERA_WARMUP_FRAMES,
        PROCESS_EVERY,
        PREVIEW_SCALE,
    )


ColorRange = Tuple[Tuple[int, int, int], Tuple[int, int, int]]
Rect = Tuple[int, int, int, int]
Point = Tuple[int, int]

DRAW_COLORS = {
    "blue": (255, 0, 0),
    "red": (0, 0, 255),
}


@dataclass(frozen=True)
class VisionConfig:
    min_area: int = MIN_AREA
    max_area_ratio: float = MAX_AREA_RATIO
    min_fill_ratio: float = MIN_FILL_RATIO
    min_confidence: float = MIN_CONFIDENCE
    stable_frames: int = STABLE_FRAMES
    pick_roi: Optional[Rect] = None
    gripper_roi: Optional[Rect] = None
    camera_warmup_frames: int = CAMERA_WARMUP_FRAMES
    frame_width: int = FRAME_WIDTH
    frame_height: int = FRAME_HEIGHT
    process_every: int = PROCESS_EVERY
    preview_scale: float = PREVIEW_SCALE


@dataclass(frozen=True)
class ObjectDetection:
    color: str
    confidence: float
    area: float
    center: Point
    bbox: Rect
    frame_size: Tuple[int, int]
    fill_ratio: float
    stable_count: int = 1


@dataclass(frozen=True)
class GripCheck:
    has_object: bool
    detection: Optional[ObjectDetection]
    reason: str


class CameraVision:
    def __init__(self, camera_index: int, config: VisionConfig):
        self.camera_index = camera_index
        self.config = config
        self.camera = cv2.VideoCapture(camera_index)
        if not self.camera.isOpened():
            raise RuntimeError(f"cannot open camera index {camera_index}")

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.frame_width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.frame_height)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._frame_index = 0
        self._last_detection: Optional[ObjectDetection] = None
        self._last_color: Optional[str] = None
        self._stable_count = 0
        self._warmup()

    def close(self) -> None:
        self.camera.release()
        cv2.destroyAllWindows()

    def read_frame(self) -> np.ndarray:
        ok, frame = self.camera.read()
        if not ok:
            raise RuntimeError("camera read failed")
        return frame

    def detect_object(self, frame: np.ndarray) -> Optional[ObjectDetection]:
        self._frame_index += 1
        should_process = self._frame_index % max(1, self.config.process_every) == 0
        if should_process:
            detection = detect_colored_object(frame, self.config, self.config.pick_roi)
            self._last_detection = detection
        else:
            detection = self._last_detection

        if detection is None:
            self._last_color = None
            self._stable_count = 0
            return None

        if detection.color == self._last_color:
            self._stable_count += 1
        else:
            self._last_color = detection.color
            self._stable_count = 1

        return ObjectDetection(
            color=detection.color,
            confidence=detection.confidence,
            area=detection.area,
            center=detection.center,
            bbox=detection.bbox,
            frame_size=detection.frame_size,
            fill_ratio=detection.fill_ratio,
            stable_count=self._stable_count,
        )

    def wait_for_object(self, timeout: float, preview: bool = True) -> Optional[ObjectDetection]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.read_frame()
            detection = self.detect_object(frame)

            if preview:
                show_preview(frame, detection, self.config)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    return None

            if detection is not None and detection.stable_count >= self.config.stable_frames:
                return detection

        return None

    def check_grip(self, samples: int = 5, delay: float = 0.15, preview: bool = True) -> GripCheck:
        detections: List[ObjectDetection] = []
        for _ in range(samples):
            frame = self.read_frame()
            detection = detect_colored_object(frame, self.config, self.config.gripper_roi)
            if detection is not None:
                detections.append(detection)

            if preview:
                show_preview(frame, detection, self.config)
                cv2.waitKey(1)

            time.sleep(delay)

        if not detections:
            return GripCheck(False, None, "no red/blue object visible in gripper ROI")

        best = max(detections, key=lambda item: item.confidence)
        enough_votes = len(detections) >= max(1, samples // 2)
        if enough_votes and best.confidence >= self.config.min_confidence:
            return GripCheck(True, best, "object visible in gripper ROI")

        return GripCheck(False, best, "object confidence too low in gripper ROI")

    def pump_preview(self) -> bool:
        frame = self.read_frame()
        detection = detect_colored_object(frame, self.config, self.config.pick_roi)
        show_preview(frame, detection, self.config)
        return (cv2.waitKey(1) & 0xFF) != ord("q")

    def _warmup(self) -> None:
        for _ in range(self.config.camera_warmup_frames):
            self.camera.read()


def detect_colored_object(
    frame: np.ndarray,
    config: VisionConfig,
    roi: Optional[Rect] = None,
) -> Optional[ObjectDetection]:
    frame_height, frame_width = frame.shape[:2]
    x_offset = 0
    y_offset = 0
    work_frame = frame

    if roi is not None:
        x, y, w, h = clamp_rect(roi, frame_width, frame_height)
        work_frame = frame[y : y + h, x : x + w]
        x_offset = x
        y_offset = y

    blurred = cv2.GaussianBlur(work_frame, (7, 7), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    frame_area = work_frame.shape[0] * work_frame.shape[1]

    best: Optional[ObjectDetection] = None

    for color, ranges in HSV_RANGES.items():
        mask = build_color_mask(hsv, ranges)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        if area < config.min_area or area > frame_area * config.max_area_ratio:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        bbox_area = max(1, w * h)
        fill_ratio = area / bbox_area
        if fill_ratio < config.min_fill_ratio:
            continue

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue

        confidence = score_detection(area, frame_area, fill_ratio)
        if confidence < config.min_confidence:
            continue

        detection = ObjectDetection(
            color=color,
            confidence=confidence,
            area=area,
            center=(
                int(moments["m10"] / moments["m00"]) + x_offset,
                int(moments["m01"] / moments["m00"]) + y_offset,
            ),
            bbox=(x + x_offset, y + y_offset, w, h),
            frame_size=(frame_width, frame_height),
            fill_ratio=fill_ratio,
        )

        if best is None or detection.confidence > best.confidence:
            best = detection

    return best


def build_color_mask(hsv: np.ndarray, ranges: List[ColorRange]) -> np.ndarray:
    mask = None
    for lower, upper in ranges:
        current = cv2.inRange(hsv, np.array(lower), np.array(upper))
        mask = current if mask is None else cv2.bitwise_or(mask, current)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def score_detection(area: float, frame_area: int, fill_ratio: float) -> float:
    area_score = min(1.0, area / max(1.0, frame_area * 0.08))
    fill_score = min(1.0, fill_ratio / 0.75)
    return 0.65 * area_score + 0.35 * fill_score


def clamp_rect(rect: Rect, frame_width: int, frame_height: int) -> Rect:
    x, y, w, h = rect
    x = max(0, min(frame_width - 1, x))
    y = max(0, min(frame_height - 1, y))
    w = max(1, min(frame_width - x, w))
    h = max(1, min(frame_height - y, h))
    return x, y, w, h


def parse_rect(value: Optional[str]) -> Optional[Rect]:
    if not value:
        return None

    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("ROI must use x,y,width,height")

    try:
        x, y, w, h = (int(part.strip()) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ROI values must be integers") from exc

    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("ROI width and height must be positive")

    return x, y, w, h


def show_preview(
    frame: np.ndarray,
    detection: Optional[ObjectDetection],
    config: VisionConfig,
) -> None:
    draw_roi(frame, config.pick_roi, (0, 255, 255), "pick ROI")
    draw_roi(frame, config.gripper_roi, (0, 255, 0), "gripper ROI")

    if detection is not None:
        x, y, w, h = detection.bbox
        color = DRAW_COLORS[detection.color]
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.circle(frame, detection.center, 5, color, -1)
        cv2.putText(
            frame,
            f"{detection.color} conf={detection.confidence:.2f} stable={detection.stable_count}",
            (x, max(20, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            color,
            2,
            cv2.LINE_AA,
        )

    if config.preview_scale != 1.0:
        frame = cv2.resize(
            frame,
            None,
            fx=config.preview_scale,
            fy=config.preview_scale,
            interpolation=cv2.INTER_AREA,
        )

    cv2.imshow("Automation Vision", frame)


def draw_roi(frame: np.ndarray, roi: Optional[Rect], color: Tuple[int, int, int], label: str) -> None:
    if roi is None:
        return

    frame_height, frame_width = frame.shape[:2]
    x, y, w, h = clamp_rect(roi, frame_width, frame_height)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    cv2.putText(
        frame,
        label,
        (x, max(20, y - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
        cv2.LINE_AA,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect stable red/blue objects and gripper feedback")
    parser.add_argument("--camera-index", type=int, default=CAMERA_INDEX)
    parser.add_argument("--pick-roi", type=parse_rect)
    parser.add_argument("--gripper-roi", type=parse_rect)
    parser.add_argument("--min-area", type=int, default=MIN_AREA)
    parser.add_argument("--stable-frames", type=int, default=STABLE_FRAMES)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--frame-width", type=int, default=FRAME_WIDTH)
    parser.add_argument("--frame-height", type=int, default=FRAME_HEIGHT)
    parser.add_argument("--process-every", type=int, default=PROCESS_EVERY)
    parser.add_argument("--preview-scale", type=float, default=PREVIEW_SCALE)
    parser.add_argument("--no-preview", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = VisionConfig(
        min_area=args.min_area,
        stable_frames=args.stable_frames,
        pick_roi=args.pick_roi,
        gripper_roi=args.gripper_roi,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        process_every=args.process_every,
        preview_scale=args.preview_scale,
    )
    vision = CameraVision(args.camera_index, config)

    try:
        detection = vision.wait_for_object(args.timeout, preview=not args.no_preview)
        print(detection if detection is not None else "No stable red/blue object detected")
    finally:
        vision.close()


if __name__ == "__main__":
    main()
