#!/usr/bin/env python3
import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2
import numpy as np


DEFAULT_API_BASE = "http://127.0.0.1:8000"

HSV_RANGES = {
    "blue": [
        ((95, 70, 45), (135, 255, 255)),
    ],
    "red": [
        ((0, 80, 45), (10, 255, 255)),
        ((170, 80, 45), (180, 255, 255)),
    ],
}


@dataclass
class Detection:
    color: str
    area: float
    center: Tuple[int, int]
    bbox: Tuple[int, int, int, int]


class ArmApi:
    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_state(self) -> Dict[str, object]:
        return self._request("GET", "/api/state")

    def sort(self, color: str) -> Dict[str, object]:
        return self._request("POST", "/api/sort", {"color": color})

    def emergency_stop(self) -> Dict[str, object]:
        return self._request("POST", "/api/emergency-stop")

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


class ColorSorter:
    def __init__(
        self,
        arm_api: ArmApi,
        camera_index: int,
        min_area: int,
        stable_frames: int,
        cooldown: float,
        preview: bool,
        emergency_failures: int,
    ):
        self.arm_api = arm_api
        self.camera_index = camera_index
        self.min_area = min_area
        self.stable_frames = stable_frames
        self.cooldown = cooldown
        self.preview = preview
        self.emergency_failures = emergency_failures

        self._candidate_color: Optional[str] = None
        self._candidate_count = 0
        self._last_sort_at = 0.0
        self._read_failures = 0

    def run(self) -> None:
        camera = cv2.VideoCapture(self.camera_index)
        if not camera.isOpened():
            raise RuntimeError(f"cannot open camera index {self.camera_index}")

        print("Vision sorter running. Press q in the preview window or Ctrl+C to stop.")

        try:
            while True:
                ok, frame = camera.read()
                if not ok:
                    self._handle_camera_failure()
                    continue

                self._read_failures = 0
                detection = detect_color(frame, self.min_area)
                self._process_detection(detection)

                if self.preview:
                    show_preview(frame, detection)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        finally:
            camera.release()
            if self.preview:
                cv2.destroyAllWindows()

    def _handle_camera_failure(self) -> None:
        self._read_failures += 1
        print(f"Camera read failed ({self._read_failures}/{self.emergency_failures})")
        if self._read_failures >= self.emergency_failures:
            try:
                self.arm_api.emergency_stop()
            finally:
                raise RuntimeError("camera stream failed repeatedly; emergency stop sent")
        time.sleep(0.1)

    def _process_detection(self, detection: Optional[Detection]) -> None:
        if detection is None:
            self._candidate_color = None
            self._candidate_count = 0
            return

        if detection.color == self._candidate_color:
            self._candidate_count += 1
        else:
            self._candidate_color = detection.color
            self._candidate_count = 1

        if self._candidate_count < self.stable_frames:
            return

        now = time.monotonic()
        if now - self._last_sort_at < self.cooldown:
            return

        try:
            state = self.arm_api.get_state()
            if state.get("busy") or state.get("emergencyStopped"):
                return

            self.arm_api.sort(detection.color)
            self._last_sort_at = now
            self._candidate_color = None
            self._candidate_count = 0
            print(f"Detected {detection.color}; sent sort command")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"Arm API request failed: {exc}")


def detect_color(frame: np.ndarray, min_area: int) -> Optional[Detection]:
    blurred = cv2.GaussianBlur(frame, (7, 7), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    best_detection = None
    best_area = 0.0

    for color, ranges in HSV_RANGES.items():
        mask = None
        for lower, upper in ranges:
            current = cv2.inRange(hsv, np.array(lower), np.array(upper))
            mask = current if mask is None else cv2.bitwise_or(mask, current)

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        if area < min_area or area <= best_area:
            continue

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        best_area = area
        best_detection = Detection(
            color=color,
            area=area,
            center=(int(moments["m10"] / moments["m00"]), int(moments["m01"] / moments["m00"])),
            bbox=(x, y, w, h),
        )

    return best_detection


def show_preview(frame: np.ndarray, detection: Optional[Detection]) -> None:
    if detection is not None:
        x, y, w, h = detection.bbox
        color = (255, 0, 0) if detection.color == "blue" else (0, 0, 255)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.circle(frame, detection.center, 5, color, -1)
        cv2.putText(
            frame,
            f"{detection.color} area={int(detection.area)}",
            (x, max(20, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )

    cv2.imshow("Robot Arm Vision Sorter", frame)


def parse_args():
    parser = argparse.ArgumentParser(description="Detect red/blue objects from a USB camera and sort them with the robot arm")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="manual_control.py API base URL")
    parser.add_argument("--camera-index", type=int, default=0, help="USB camera index used by OpenCV")
    parser.add_argument("--min-area", type=int, default=1800, help="minimum contour area required for a valid object")
    parser.add_argument("--stable-frames", type=int, default=8, help="frames of the same color required before sorting")
    parser.add_argument("--cooldown", type=float, default=9.0, help="seconds to wait before another sort command")
    parser.add_argument("--request-timeout", type=float, default=2.0, help="seconds before API calls time out")
    parser.add_argument("--emergency-failures", type=int, default=20, help="camera read failures before emergency stop")
    parser.add_argument("--no-preview", action="store_true", help="run without showing the camera preview window")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sorter = ColorSorter(
        arm_api=ArmApi(args.api_base, args.request_timeout),
        camera_index=args.camera_index,
        min_area=args.min_area,
        stable_frames=args.stable_frames,
        cooldown=args.cooldown,
        preview=not args.no_preview,
        emergency_failures=args.emergency_failures,
    )
    sorter.run()


if __name__ == "__main__":
    main()
