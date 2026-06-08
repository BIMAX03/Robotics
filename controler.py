import threading
import time
import tkinter as tk

import serial

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600
SEND_INTERVAL = 0.05  # 20 Hz avoids flooding the Arduino serial buffer.
RECONNECT_INTERVAL = 2
KEY_UPDATE_INTERVAL_MS = 20
KEY_SPEED_DEGREES_PER_SECOND = 90


class ServoSerialWriter:
    def __init__(self, port, baud_rate):
        self.port = port
        self.baud_rate = baud_rate
        self.arduino = None

        self._lock = threading.Lock()
        self._target_angles = [90, 90, 90]
        self._last_sent_angles = None
        self._running = True
        self._thread = threading.Thread(target=self._write_loop, daemon=True)
        self._thread.start()

    def set_angle(self, servo_index, value):
        angle = max(0, min(180, int(float(value))))
        with self._lock:
            self._target_angles[servo_index] = angle

    def close(self):
        self._running = False
        self._thread.join(timeout=1)
        if self.arduino is not None and self.arduino.is_open:
            self.arduino.close()

    def _write_loop(self):
        while self._running:
            if not self._ensure_connected():
                time.sleep(RECONNECT_INTERVAL)
                continue

            self._drain_input()

            with self._lock:
                angles = tuple(self._target_angles)

            if angles != self._last_sent_angles:
                try:
                    self.arduino.write(
                        f"{angles[0]},{angles[1]},{angles[2]}\n".encode("ascii")
                    )
                    self.arduino.flush()
                    self._last_sent_angles = angles
                except serial.SerialException as exc:
                    print(f"Serial disconnected: {exc}")
                    self._disconnect()

            time.sleep(SEND_INTERVAL)

    def _ensure_connected(self):
        if self.arduino is not None and self.arduino.is_open:
            return True

        try:
            self.arduino = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=0,
                write_timeout=1,
                dsrdtr=False,
                rtscts=False,
            )
            self.arduino.reset_input_buffer()
            self.arduino.reset_output_buffer()
            time.sleep(2)  # Let Arduino reset after opening the serial port.
            self._last_sent_angles = None
            print(f"Connected to {self.port}")
            return True
        except serial.SerialException as exc:
            print(f"Waiting for {self.port}: {exc}")
            self._disconnect()
            return False

    def _disconnect(self):
        if self.arduino is not None:
            try:
                self.arduino.close()
            except serial.SerialException:
                pass
            self.arduino = None

    def _drain_input(self):
        try:
            waiting = self.arduino.in_waiting
            if waiting:
                self.arduino.read(waiting)
        except serial.SerialException as exc:
            print(f"Serial disconnected: {exc}")
            self._disconnect()


servo = ServoSerialWriter(SERIAL_PORT, BAUD_RATE)

root = tk.Tk()
root.title("Servo Controller")
pressed_keys = set()
last_key_update = time.monotonic()


def update_servo_9(value):
    servo.set_angle(0, value)


def update_servo_10(value):
    servo.set_angle(1, value)


def update_servo_11(value):
    servo.set_angle(2, value)


def on_close():
    servo.close()
    root.destroy()


def clamp_angle(value):
    return max(0, min(180, int(round(value))))


def on_key_press(event):
    pressed_keys.add(event.keysym.lower())


def on_key_release(event):
    pressed_keys.discard(event.keysym.lower())


def get_axis(negative_keys, positive_keys):
    negative = any(key in pressed_keys for key in negative_keys)
    positive = any(key in pressed_keys for key in positive_keys)
    return int(positive) - int(negative)


def update_from_keyboard():
    global last_key_update

    now = time.monotonic()
    elapsed = now - last_key_update
    last_key_update = now

    step = KEY_SPEED_DEGREES_PER_SECOND * elapsed
    servo_9_axis = get_axis(("a", "left"), ("d", "right"))
    servo_10_axis = get_axis(("s", "down"), ("w", "up"))
    servo_11_axis = get_axis(("q",), ("e",))

    if servo_9_axis:
        servo_9_slider.set(clamp_angle(servo_9_slider.get() + servo_9_axis * step))

    if servo_10_axis:
        servo_10_slider.set(clamp_angle(servo_10_slider.get() + servo_10_axis * step))

    if servo_11_axis:
        servo_11_slider.set(clamp_angle(servo_11_slider.get() + servo_11_axis * step))

    root.after(KEY_UPDATE_INTERVAL_MS, update_from_keyboard)


servo_9_slider = tk.Scale(
    root,
    from_=0,
    to=180,
    orient="horizontal",
    length=400,
    label="Servo D9",
    command=update_servo_9,
)

servo_10_slider = tk.Scale(
    root,
    from_=0,
    to=180,
    orient="horizontal",
    length=400,
    label="Servo D10",
    command=update_servo_10,
)

servo_11_slider = tk.Scale(
    root,
    from_=0,
    to=180,
    orient="horizontal",
    length=400,
    label="Servo D11",
    command=update_servo_11,
)

servo_9_slider.set(90)
servo_10_slider.set(90)
servo_11_slider.set(90)
servo_9_slider.pack(padx=20, pady=(20, 10))
servo_10_slider.pack(padx=20, pady=10)
servo_11_slider.pack(padx=20, pady=(10, 20))
root.bind_all("<KeyPress>", on_key_press)
root.bind_all("<KeyRelease>", on_key_release)
root.focus_set()
root.after(KEY_UPDATE_INTERVAL_MS, update_from_keyboard)
root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
