#!/usr/bin/env python3
import argparse
import json
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Iterable, List, Optional

import serial


SEND_INTERVAL = 0.05
RECONNECT_INTERVAL = 2.0
SORT_SETTLE_DELAY = 1.0
SORT_RAMP_INTERVAL = 0.08
SORT_RAMP_STEP_DEGREES = 3


@dataclass(frozen=True)
class Joint:
    key: str
    label: str
    pin: int
    min: int
    max: int
    home: int


JOINTS = [
    Joint("S0", "Base", 3, 0, 360, 180),
    Joint("S1", "Shoulder", 5, 0, 180, 90),
    Joint("S2", "Elbow", 6, 0, 270, 135),
    Joint("S3", "Wrist Pitch", 9, 0, 150, 75),
    Joint("S4", "Wrist Roll", 10, 0, 180, 90),
    Joint("S5", "Gripper", 11, 25, 70, 40),
]
JOINT_BY_KEY = {joint.key: joint for joint in JOINTS}

SORT_DROPOFFS = {
    "blue": 360,
    "red": 0,
}


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
        self._last_sent = None
        self._stop_event = threading.Event()
        self._sequence_thread: Optional[threading.Thread] = None
        self._running = True
        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()

    def get_state(self) -> Dict[str, object]:
        with self._lock:
            joints = dict(self._target)

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
            "frame": self._format_frame(joints.values()),
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
        targets = {}
        with self._lock:
            if self.emergency_stopped:
                raise RuntimeError("emergency stop is active")
            for key, value in values.items():
                joint = JOINT_BY_KEY[key]
                targets[key] = self._parse_angle(value, joint)

            start = {key: self._target[key] for key in targets}

        max_delta = max((abs(targets[key] - start[key]) for key in targets), default=0)
        ramp_steps = max(1, (max_delta + SORT_RAMP_STEP_DEGREES - 1) // SORT_RAMP_STEP_DEGREES)

        for step_index in range(1, ramp_steps + 1):
            if self._stop_event.is_set():
                return True

            progress = step_index / ramp_steps
            with self._lock:
                if self.emergency_stopped:
                    raise RuntimeError("emergency stop is active")
                for key, target in targets.items():
                    current = start[key] + (target - start[key]) * progress
                    self._target[key] = int(round(current))

            if step_index < ramp_steps and self._stop_event.wait(SORT_RAMP_INTERVAL):
                return True

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
                values = tuple(self._target[joint.key] for joint in JOINTS)

            if values != self._last_sent:
                frame = self._format_frame(values)
                if self.mock:
                    print(f"[mock] {frame.strip()}")
                    self._last_sent = values
                else:
                    self._send_frame(frame, values)

            time.sleep(SEND_INTERVAL)

    def _send_frame(self, frame: str, values: Iterable[int]) -> None:
        try:
            self._drain_input()
            self.serial_port.write(frame.encode("ascii"))
            self.serial_port.flush()
            self._last_sent = values
            self.last_error = ""
        except serial.SerialException as exc:
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

        waiting = self.serial_port.in_waiting
        if waiting:
            self.serial_port.read(waiting)


class ApiHandler(BaseHTTPRequestHandler):
    controller: RobotArmController

    def do_OPTIONS(self):
        self._send_empty(204)

    def do_GET(self):
        if self.path == "/api/config":
            self._send_json({"joints": [asdict(joint) for joint in JOINTS]})
        elif self.path == "/api/state":
            self._send_json(self.controller.get_state())
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        try:
            body = self._read_json()

            if self.path == "/api/joints":
                values = body.get("joints", body)
                if not isinstance(values, dict):
                    raise ValueError("request body must contain a joints object")
                joints = self.controller.set_joints(values)
                self._send_json({"ok": True, "joints": joints})
            elif self.path == "/api/home":
                joints = self.controller.home()
                self._send_json({"ok": True, "joints": joints})
            elif self.path == "/api/sort":
                color = body.get("color")
                if not isinstance(color, str):
                    raise ValueError("request body must contain color")
                self._send_json(self.controller.sort_item(color))
            elif self.path == "/api/emergency-stop":
                self._send_json({"ok": True, "state": self.controller.emergency_stop()})
            else:
                self._send_json({"error": "Not found"}, status=404)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format, *args):
        return

    def _read_json(self) -> Dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}

        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self._send_headers()
        self.end_headers()

    def _send_json(self, payload: Dict[str, object], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._send_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def parse_args():
    parser = argparse.ArgumentParser(description="Manual robot arm control API")
    parser.add_argument("--serial-port", default="/dev/ttyACM0")
    parser.add_argument("--baud-rate", type=int, default=9600)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8000)
    parser.add_argument("--mock", action="store_true", help="run without Arduino hardware")
    return parser.parse_args()


def main():
    args = parse_args()
    controller = RobotArmController(args.serial_port, args.baud_rate, args.mock)
    ApiHandler.controller = controller

    server = ThreadingHTTPServer((args.host, args.http_port), ApiHandler)
    print(f"API listening on http://{args.host}:{args.http_port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        controller.close()
        server.server_close()


if __name__ == "__main__":
    main()
