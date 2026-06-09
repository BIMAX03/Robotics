#!/usr/bin/env python3
import argparse
import json
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from server.automation.vision import CameraVision, ObjectDetection, VisionConfig, parse_rect
    from server.config import (
        DEFAULT_API_BASE,
        REQUEST_TIMEOUT,
        POSE_SETTLE_DELAY,
        POSE_SETTLE_PER_DEGREE,
        POSE_TIMEOUT,
        POSE_TOLERANCE_DEGREES,
        DETECT_TIMEOUT,
        CAMERA_INDEX,
        MIN_AREA,
        STABLE_FRAMES,
        FRAME_WIDTH,
        FRAME_HEIGHT,
        PROCESS_EVERY,
        PREVIEW_SCALE,
        PICK_SEQUENCE,
        PLACE_SEQUENCE,
    )
except ModuleNotFoundError:
    from vision import CameraVision, ObjectDetection, VisionConfig, parse_rect
    from config import (
        DEFAULT_API_BASE,
        REQUEST_TIMEOUT,
        POSE_SETTLE_DELAY,
        POSE_SETTLE_PER_DEGREE,
        POSE_TIMEOUT,
        POSE_TOLERANCE_DEGREES,
        DETECT_TIMEOUT,
        CAMERA_INDEX,
        MIN_AREA,
        STABLE_FRAMES,
        FRAME_WIDTH,
        FRAME_HEIGHT,
        PROCESS_EVERY,
        PREVIEW_SCALE,
        PICK_SEQUENCE,
        PLACE_SEQUENCE,
    )

# HOME_POSE được lấy từ danh sách khớp trong config — import riêng để tránh vòng
try:
    from server.config import JOINTS_CONFIG
except ModuleNotFoundError:
    from config import JOINTS_CONFIG

HOME_POSE = {cfg[0]: cfg[5] for cfg in JOINTS_CONFIG}  # {key: home_angle}



@dataclass(frozen=True)
class OperationConfig:
    pose_settle_delay: float
    pose_settle_per_degree: float
    pose_timeout: float
    pose_tolerance: int
    detect_timeout: float
    preview: bool


class ArmApi:
    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def state(self) -> Dict[str, object]:
        return self._request("GET", "/api/state")

    def set_joints(self, joints: Dict[str, int]) -> Dict[str, object]:
        return self._request("POST", "/api/joints", {"joints": joints})

    def home(self) -> Dict[str, object]:
        return self._request("POST", "/api/home")

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


class VisionOperationRunner:
    def __init__(self, arm: ArmApi, vision: CameraVision, config: OperationConfig):
        self.arm = arm
        self.vision = vision
        self.config = config

    def run_forever(self) -> None:
        print("Automation running. Press Ctrl+C to stop.")
        while True:
            detection = self.vision.wait_for_object(
                timeout=self.config.detect_timeout,
                preview=self.config.preview,
            )
            if detection is None:
                print("No stable red/blue object found; scanning again")
                continue

            print(
                f"Detected {detection.color}: center={detection.center}, "
                f"confidence={detection.confidence:.2f}, stable={detection.stable_count}"
            )
            self.run_for_detection(detection)

    def run_for_detection(self, detection: ObjectDetection) -> bool:
        self._wait_until_ready()
        self._home()
        self._run_steps("pick", PICK_SEQUENCE)
        self._run_steps(f"place {detection.color}", PLACE_SEQUENCE[detection.color])
        self._home()
        print(f"Completed {detection.color} operation")
        return True

    def _run_steps(self, label: str, steps: Iterable[Dict[str, int]]) -> None:
        for index, step in enumerate(steps, start=1):
            print(f"{label} step {index}: {step}", flush=True)
            max_delta = self._target_delta(step)
            self.arm.set_joints(step)
            self._wait_until_pose(step)
            self._settle_after_move(max_delta)

    def _target_delta(self, target: Dict[str, int]) -> float:
        state = self.arm.state()
        current = state.get("currentJoints", state.get("joints", {}))
        if not isinstance(current, dict):
            return 0.0

        deltas = []
        for key, value in target.items():
            try:
                deltas.append(abs(float(current[key]) - value))
            except (KeyError, TypeError, ValueError):
                pass
        return max(deltas, default=0.0)

    def _settle_after_move(self, max_delta: float) -> None:
        settle_time = self.config.pose_settle_delay + max_delta * self.config.pose_settle_per_degree
        self._sleep_with_preview(settle_time)

    def _wait_until_pose(self, target: Dict[str, int]) -> None:
        deadline = time.monotonic() + self.config.pose_timeout
        while time.monotonic() < deadline:
            state = self.arm.state()
            current = state.get("currentJoints", state.get("joints", {}))
            if isinstance(current, dict) and self._pose_reached(current, target):
                return
            self._sleep_with_preview(0.06)

        print(f"Warning: pose timeout while waiting for {target}", flush=True)

    def _pose_reached(self, current: Dict[str, object], target: Dict[str, int]) -> bool:
        for key, value in target.items():
            try:
                current_value = float(current[key])
            except (KeyError, TypeError, ValueError):
                return False
            if abs(current_value - value) > self.config.pose_tolerance:
                return False
        return True

    def _home(self) -> None:
        print("home", flush=True)
        max_delta = self._target_delta(HOME_POSE)
        try:
            self.arm.home()
        except Exception:
            self.arm.set_joints(HOME_POSE)
        self._wait_until_pose(HOME_POSE)
        self._settle_after_move(max_delta)

    def _wait_until_ready(self) -> None:
        while True:
            state = self.arm.state()
            if state.get("emergencyStopped"):
                raise RuntimeError("arm is emergency stopped; clear with /api/home before automation")
            if not state.get("busy"):
                return
            self._sleep_with_preview(0.25)

    def _sleep_with_preview(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.config.preview and not self.vision.pump_preview():
                raise KeyboardInterrupt
            time.sleep(0.03 if self.config.preview else min(0.2, seconds))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run robot operation based on red/blue vision detection")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--request-timeout", type=float, default=REQUEST_TIMEOUT)
    parser.add_argument("--camera-index", type=int, default=CAMERA_INDEX)
    parser.add_argument("--pick-roi", type=parse_rect)
    parser.add_argument("--min-area", type=int, default=MIN_AREA)
    parser.add_argument("--stable-frames", type=int, default=STABLE_FRAMES)
    parser.add_argument("--frame-width", type=int, default=FRAME_WIDTH)
    parser.add_argument("--frame-height", type=int, default=FRAME_HEIGHT)
    parser.add_argument("--process-every", type=int, default=PROCESS_EVERY)
    parser.add_argument("--preview-scale", type=float, default=PREVIEW_SCALE)
    parser.add_argument("--detect-timeout", type=float, default=DETECT_TIMEOUT)
    parser.add_argument("--pose-settle-delay", type=float, default=POSE_SETTLE_DELAY)
    parser.add_argument("--pose-settle-per-degree", type=float, default=POSE_SETTLE_PER_DEGREE)
    parser.add_argument("--pose-timeout", type=float, default=POSE_TIMEOUT)
    parser.add_argument("--pose-tolerance", type=int, default=POSE_TOLERANCE_DEGREES)
    parser.add_argument("--no-preview", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vision_config = VisionConfig(
        min_area=args.min_area,
        stable_frames=args.stable_frames,
        pick_roi=args.pick_roi,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        process_every=args.process_every,
        preview_scale=args.preview_scale,
    )
    vision = CameraVision(args.camera_index, vision_config)
    arm = ArmApi(args.api_base, args.request_timeout)
    runner = VisionOperationRunner(
        arm=arm,
        vision=vision,
        config=OperationConfig(
            pose_settle_delay=args.pose_settle_delay,
            pose_settle_per_degree=args.pose_settle_per_degree,
            pose_timeout=args.pose_timeout,
            pose_tolerance=args.pose_tolerance,
            detect_timeout=args.detect_timeout,
            preview=not args.no_preview,
        ),
    )

    try:
        runner.run_forever()
    except KeyboardInterrupt:
        print("Stopping automation")
        arm.home()
    finally:
        vision.close()


if __name__ == "__main__":
    main()
