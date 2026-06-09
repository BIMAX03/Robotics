#!/usr/bin/env python3
import argparse
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import serial

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import lớp HTTP handler và factory tạo server từ file networking riêng
from server.api import build_http_server

from server.config import (
    DEFAULT_SERIAL_PORT,
    DEFAULT_BAUD_RATE,
    DEFAULT_HOST,
    DEFAULT_HTTP_PORT,
    SEND_INTERVAL,
    MOTION_STEP_DEGREES,
    RECONNECT_INTERVAL,
    SORT_SETTLE_DELAY,
    JOINTS_CONFIG,
    SORT_DROPOFFS,
)


@dataclass(frozen=True)
class Joint:
    key: str
    label: str
    pin: int
    min: int
    max: int
    home: int


JOINTS = [Joint(*cfg) for cfg in JOINTS_CONFIG]
JOINT_BY_KEY = {joint.key: joint for joint in JOINTS}


def build_sort_sequence(color: str) -> List[Dict[str, int]]:
    return [
        {"S1": 15},
        {"S5": 65},
        {"S1": 60},
        {"S0": SORT_DROPOFFS[color]},
        {"S1": 15},
        {"S5": 60},
        {"S1": 60},
        {joint.key: joint.home for joint in JOINTS},
    ]


class RobotArmController:
    def __init__(self, port: str, baud_rate: int, mock: bool):
        self.port = port
        self.baud_rate = baud_rate
        self.mock = mock
        self.serial_port: Optional[serial.Serial] = None
        self.connected = False
        self.last_error = ""
        self.busy = False
        self.emergency_stopped = False
        self.sequence_name = ""

        self._lock = threading.Lock()
        self._motion_lock = threading.Lock()
        self._target = {joint.key: joint.home for joint in JOINTS}
        self._current = {joint.key: float(joint.home) for joint in JOINTS}
        self._last_sent = None
        self._stop_event = threading.Event()
        self._sequence_thread: Optional[threading.Thread] = None
        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()

    def get_state(self) -> Dict[str, object]:
        with self._lock:
            joints = dict(self._target)
            current = {key: int(round(value)) for key, value in self._current.items()}

        return {
            "connected": self.connected or self.mock,
            "mock": self.mock,
            "port": self.port,
            "baudRate": self.baud_rate,
            "lastError": self.last_error,
            "busy": self.busy,
            "emergencyStopped": self.emergency_stopped,
            "sequenceName": self.sequence_name,
            "joints": joints,
            "currentJoints": current,
            "frame": self._format_frame(current.values()),
        }

    def set_joints(self, values: Dict[str, object]) -> Dict[str, int]:
        if self.emergency_stopped:
            raise ValueError("emergency stop is active; send home before manual movement")
        if self.busy:
            raise ValueError("arm is busy running an automated sequence")

        with self._lock:
            for joint in JOINTS:
                if joint.key not in values:
                    continue

                angle = self._parse_angle(values[joint.key], joint)
                self._target[joint.key] = angle

            return dict(self._target)

    def home(self) -> Dict[str, int]:
        self._stop_event.set()
        with self._motion_lock:
            with self._lock:
                self._target = {joint.key: joint.home for joint in JOINTS}
                self.emergency_stopped = False
                self.busy = False
                self.sequence_name = ""
                return dict(self._target)

    def emergency_stop(self, reason: str = "Emergency stop requested") -> Dict[str, object]:
        self._stop_event.set()
        with self._lock:
            self._target = {joint.key: joint.home for joint in JOINTS}
            self.busy = False
            self.emergency_stopped = True
            self.sequence_name = ""
            self.last_error = reason

        return self.get_state()

    def sort_item(self, color: str) -> Dict[str, object]:
        normalized = color.strip().lower()
        if normalized not in SORT_DROPOFFS:
            raise ValueError("color must be blue or red")
        if self.emergency_stopped:
            raise ValueError("emergency stop is active; send home before sorting")
        if self.busy:
            raise ValueError("arm is already running an automated sequence")

        self._stop_event.clear()
        self.busy = True
        self.sequence_name = f"sort-{normalized}"
        self._sequence_thread = threading.Thread(
            target=self._run_sort_sequence,
            args=(normalized,),
            daemon=True,
        )
        self._sequence_thread.start()
        return {"ok": True, "busy": True, "sequenceName": self.sequence_name}

    def close(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._sequence_thread is not None:
            self._sequence_thread.join(timeout=1)
        self._thread.join(timeout=1)
        self._disconnect()

    def _run_sort_sequence(self, color: str) -> None:
        try:
            with self._motion_lock:
                for step in build_sort_sequence(color):
                    if self._stop_event.is_set():
                        return
                    if self._apply_sequence_step(step):
                        return
                    if self._stop_event.wait(SORT_SETTLE_DELAY):
                        return

                with self._lock:
                    self.busy = False
                    self.sequence_name = ""
        except Exception as exc:
            print(f"Sort sequence failed: {exc}")
            self.emergency_stop(f"Automated sequence failed: {exc}")

    def _apply_sequence_step(self, values: Dict[str, int]) -> bool:
        with self._lock:
            if self.emergency_stopped:
                raise RuntimeError("emergency stop is active")
            for key, value in values.items():
                joint = JOINT_BY_KEY[key]
                self._target[key] = self._parse_angle(value, joint)
        return False

    def _parse_angle(self, value: object, joint: Joint) -> int:
        try:
            angle = int(round(float(value)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{joint.key} must be a number") from exc

        if angle < joint.min or angle > joint.max:
            raise ValueError(f"{joint.key} must be between {joint.min} and {joint.max}")

        return angle

    def _send_loop(self) -> None:
        while self._running:
            if not self.mock and not self._ensure_connected():
                time.sleep(RECONNECT_INTERVAL)
                continue

            with self._lock:
                values = tuple(self._advance_motion_locked(joint.key) for joint in JOINTS)

            if values != self._last_sent:
                frame = self._format_frame(values)
                if self.mock:
                    print(f"[mock] {frame.strip()}")
                    self._last_sent = values
                else:
                    self._send_frame(frame, values)

            time.sleep(SEND_INTERVAL)

    def _advance_motion_locked(self, key: str) -> int:
        target = float(self._target[key])
        current = self._current[key]
        delta = target - current

        if abs(delta) <= MOTION_STEP_DEGREES:
            current = target
        else:
            current += MOTION_STEP_DEGREES if delta > 0 else -MOTION_STEP_DEGREES

        self._current[key] = current
        return int(round(current))

    def _send_frame(self, frame: str, values: Iterable[int]) -> None:
        try:
            self._drain_input()
            self.serial_port.write(frame.encode("ascii"))
            self.serial_port.flush()
            self._last_sent = values
            self.last_error = ""
        except (serial.SerialException, OSError) as exc:
            self.last_error = str(exc)
            print(f"Serial disconnected: {exc}")
            self.emergency_stop(f"Serial disconnected: {exc}")
            self._disconnect()

    def _format_frame(self, values: Iterable[int]) -> str:
        return ",".join(str(value) for value in values) + "\n"

    def _ensure_connected(self) -> bool:
        if self.serial_port is not None and self.serial_port.is_open:
            self.connected = True
            return True

        try:
            self.serial_port = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=0,
                write_timeout=1,
                dsrdtr=False,
                rtscts=False,
            )
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            time.sleep(2)
            self.connected = True
            self._last_sent = None
            self.last_error = ""
            print(f"Connected to {self.port}")
            return True
        except serial.SerialException as exc:
            self.connected = False
            self.last_error = str(exc)
            print(f"Waiting for {self.port}: {exc}")
            self._disconnect()
            return False

    def _disconnect(self) -> None:
        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except serial.SerialException:
                pass
        self.serial_port = None
        self.connected = False

    def _drain_input(self) -> None:
        if self.serial_port is None:
            return

        try:
            waiting = self.serial_port.in_waiting
            if waiting:
                self.serial_port.read(waiting)
        except (OSError, serial.SerialException):
            # Port might have been disconnected
            pass



def parse_args():
    parser = argparse.ArgumentParser(description="Manual robot arm control API")
    parser.add_argument("--serial-port", default=DEFAULT_SERIAL_PORT)
    parser.add_argument("--baud-rate", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--mock", action="store_true", help="run without Arduino hardware")
    return parser.parse_args()


def main():
    args = parse_args()

    # Khởi tạo controller — bắt đầu thread gửi serial và (nếu không mock) kết nối Arduino
    controller = RobotArmController(args.serial_port, args.baud_rate, args.mock)

    # Tạo HTTP server từ api.py, gắn controller và danh sách khớp vào handler
    server = build_http_server(args.host, args.http_port, controller, JOINTS)
    print(f"API listening on http://{args.host}:{args.http_port}")

    try:
        # Vòng lặp serve vô hạn — xử lý mỗi request trong thread riêng
        server.serve_forever()
    except KeyboardInterrupt:
        # Ctrl+C → thoát sạch, không để serial port bị treo
        pass
    finally:
        # Đảm bảo luôn đóng serial port và giải phóng socket dù có crash hay không
        controller.close()
        server.server_close()


if __name__ == "__main__":
    main()
