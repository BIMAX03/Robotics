# 🤖 Robotics — Robot Tay Phân Loại Vật Thể theo Màu Sắc

Dự án xây dựng hệ thống robot tay 6 bậc tự do (6-DOF) có khả năng **tự động nhận diện và phân loại vật thể** theo màu sắc (đỏ / xanh) bằng camera. Hệ thống gồm ba lớp độc lập: firmware Arduino điều khiển servo, backend Python cung cấp REST API, và giao diện web React để giám sát / điều khiển thủ công.

---

## Mục lục

- [Kiến trúc tổng quan](#kiến-trúc-tổng-quan)
- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt môi trường](#cài-đặt-môi-trường)
- [Hướng dẫn chạy dự án](#hướng-dẫn-chạy-dự-án)
  - [1. Nạp firmware Arduino](#1-nạp-firmware-arduino)
  - [2. Khởi động backend Python](#2-khởi-động-backend-python)
  - [3. Khởi động giao diện Web](#3-khởi-động-giao-diện-web)
  - [4. Chạy automation phân loại tự động](#4-chạy-automation-phân-loại-tự-động)
- [Pipeline toàn hệ thống](#pipeline-toàn-hệ-thống)
- [Chi tiết từng thành phần](#chi-tiết-từng-thành-phần)
  - [Firmware Arduino](#firmware-arduino-code_arduinomain-cpp)
  - [Backend Server](#backend-server-servermainpy)
  - [Vision Module](#vision-module-serverautomationvisionpy)
  - [Automation Runner](#automation-runner-serverautomationoperation_based_on_visionpy)
  - [Web Dashboard](#web-dashboard-web)
- [REST API Reference](#rest-api-reference)
- [Cấu hình nâng cao](#cấu-hình-nâng-cao)

---

## Kiến trúc tổng quan

```
┌──────────────────────────────────────────────────────────────┐
│                        Người dùng                            │
│           (Trình duyệt web hoặc lệnh CLI)                    │
└────────────────────┬─────────────────────────────────────────┘
                     │ HTTP (port 8000)
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                   Backend Python                             │
│              server/main.py  — REST API                      │
│   GET /api/state  POST /api/joints  POST /api/sort  ...      │
└──────────┬──────────────────────────────┬────────────────────┘
           │ Serial (USB)                 │ HTTP (localhost)
           ▼                             ▼
┌──────────────────┐          ┌──────────────────────────────┐
│  Arduino         │          │  Automation Runner            │
│  code_arduino/   │          │  server/automation/           │
│  main.cpp        │          │  operation_based_on_vision.py │
│  (6 servo PWM)   │          │  + vision.py (OpenCV)         │
└──────────────────┘          └──────────────────────────────┘
```

**Luồng dữ liệu chính:**
`Camera → vision.py phát hiện màu → operation_based_on_vision.py ra lệnh → server/main.py → Arduino → Servo vật lý`

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| **OS** | Linux (Ubuntu 20.04+) |
| **Python** | 3.10+ |
| **Node.js** | 18+ |
| **Arduino IDE** | 2.x hoặc arduino-cli |
| **Phần cứng** | Arduino Uno/Mega, 6 servo, camera USB |

---

## Cài đặt môi trường

### Python (backend + automation)

```bash
# Tạo và kích hoạt virtual environment
python3 -m venv venv
source venv/bin/activate

# Cài đặt các thư viện
pip install -r requirements.txt
```

> **Tại sao cần venv?**  
> `requirements.txt` chứa nhiều thư viện nặng (`torch`, `opencv-python`, `ultralytics`). Dùng venv để tránh xung đột với Python system-wide.

### Node.js (web dashboard)

```bash
cd web
npm install
```

---

## Hướng dẫn chạy dự án

> **Thứ tự khởi động quan trọng:**  
> Arduino → Backend Python → (Web Dashboard) → Automation Runner

---

### 1. Nạp firmware Arduino

**Mục đích:** Nạp chương trình điều khiển servo lên board Arduino.

```bash
# Dùng Arduino IDE: mở file code_arduino/main.cpp, chọn board và port rồi Upload
# Hoặc dùng arduino-cli:
arduino-cli compile --fqbn arduino:avr:uno code_arduino/
arduino-cli upload  --fqbn arduino:avr:uno --port /dev/ttyACM0 code_arduino/
```

Sau khi nạp xong, Arduino sẽ:
- Khởi động 6 servo ở vị trí home (S0=180°, S1=90°, S2=135°, S3=75°, S4=90°, S5=40°).
- Lắng nghe chuỗi góc qua serial với baudrate **9600**.

---

### 2. Khởi động backend Python

**Mục đích:** Cung cấp REST API để điều khiển robot tay từ web hoặc automation script.

```bash
# Kích hoạt venv (nếu chưa)
source venv/bin/activate

# Chạy với Arduino thật (port mặc định /dev/ttyACM0)
python server/main.py

# Chạy với port khác
python server/main.py --serial-port /dev/ttyUSB0 --baud-rate 9600

# Chạy ở chế độ mock (KHÔNG cần Arduino, dùng để test)
python server/main.py --mock

# Tùy chọn đầy đủ
python server/main.py --serial-port /dev/ttyACM0 \
                      --baud-rate 9600 \
                      --host 127.0.0.1 \
                      --http-port 8000 \
                      [--mock]
```

Server sẽ in ra:
```
API listening on http://127.0.0.1:8000
Connected to /dev/ttyACM0
```

**Kiểm tra server hoạt động:**
```bash
curl http://127.0.0.1:8000/api/state
```

---

### 3. Khởi động giao diện Web

**Mục đích:** Giao diện React để giám sát trạng thái và điều khiển robot thủ công từ trình duyệt.

```bash
cd web
npm run dev
```

Truy cập: **http://localhost:5173**

> Giao diện web giao tiếp trực tiếp với backend qua `http://127.0.0.1:8000`. Đảm bảo backend đã khởi động trước.

---

### 4. Chạy automation phân loại tự động

**Mục đích:** Robot tự động phát hiện màu qua camera và thực hiện chu trình pick-and-place.

```bash
# Kích hoạt venv
source venv/bin/activate

# Chạy automation (cần backend đang chạy + camera kết nối)
python server/automation/operation_based_on_vision.py

# Tùy chọn nâng cao
python server/automation/operation_based_on_vision.py \
    --api-base http://127.0.0.1:8000 \
    --camera-index 0 \
    --stable-frames 6 \
    --detect-timeout 60.0 \
    --no-preview         # tắt cửa sổ preview OpenCV (khi chạy headless)
```

Nhấn `Ctrl+C` để dừng — arm sẽ tự động về vị trí home.

---

### Chạy vision module độc lập (để test camera)

```bash
python server/automation/vision.py \
    --camera-index 0 \
    --stable-frames 6 \
    --timeout 30.0
```

---

## Pipeline toàn hệ thống

Dưới đây là luồng xử lý chi tiết từ khi nhìn thấy vật thể đến khi phân loại xong:

```
1. CAMERA CAPTURE
   └─ CameraVision.read_frame()
      Camera USB → frame BGR 640×480

2. OBJECT DETECTION (vision.py)
   └─ detect_colored_object()
      ├─ GaussianBlur (7×7) — khử nhiễu
      ├─ cvtColor BGR→HSV — không gian màu ổn định hơn với ánh sáng
      ├─ inRange() với HSV_RANGES
      │   ├─ blue: H=[95,135]  S=[80,255]  V=[50,255]
      │   └─ red:  H=[0,10] ∪ [170,180]  (đỏ nằm ở 2 đầu vòng Hue)
      ├─ morphologyEx OPEN+CLOSE — loại bỏ noise nhỏ, lấp đầy lỗ hổng
      ├─ findContours → lấy contour lớn nhất
      ├─ Lọc theo area, fill_ratio, confidence
      └─ Trả về ObjectDetection (color, confidence, center, bbox)

3. STABILITY CHECK
   └─ CameraVision.detect_object()
      ├─ Đếm stable_count qua các frame liên tiếp
      └─ Chỉ xác nhận khi stable_count >= stable_frames (mặc định: 6)
      WHY: tránh phản ứng với vật thể thoáng qua / nhiễu ánh sáng

4. PICK-AND-PLACE SEQUENCE (operation_based_on_vision.py)
   └─ VisionOperationRunner.run_for_detection()
      ├─ _wait_until_ready() — kiểm tra arm không bận / không emergency stop
      ├─ _home() → POST /api/home
      ├─ PICK SEQUENCE (3 bước):
      │   ├─ S1→15°  (hạ vai xuống)
      │   ├─ S5→65°  (đóng gripper, kẹp vật)
      │   └─ S1→60°  (nâng vai lên)
      ├─ PLACE SEQUENCE (theo màu):
      │   ├─ red  → S0→0°   (xoay base sang phải)
      │   └─ blue → S0→360° (xoay base sang trái)
      │   └─ S1→15° → S5→60° (nhả) → S1→60°
      └─ _home() — trở về vị trí home

5. MOTOR CONTROL (server/main.py)
   └─ RobotArmController._send_loop()
      ├─ Mỗi 50ms: đọc _target, format "S0,S1,S2,S3,S4,S5\n"
      ├─ Chỉ gửi khi giá trị thay đổi (tránh flood serial)
      └─ serial.write() → Arduino

6. ARDUINO FIRMWARE (code_arduino/main.cpp)
   └─ loop(): đọc từng byte từ Serial
      ├─ Tích lũy đến '\n'
      ├─ parseAngles() — xác thực từng góc trong range cho phép
      ├─ logicalAngleToPulse() — map góc [min,max] → pulse [500,2500] μs
      └─ servo.writeMicroseconds() → PWM vật lý → servo quay
```

---

## Chi tiết từng thành phần

### Firmware Arduino (`code_arduino/main.cpp`)

**What:** Chương trình C++ chạy trực tiếp trên Arduino, điều khiển 6 servo vật lý.

**Why:** Arduino xử lý thời gian thực PWM chính xác — điều mà Python chạy trên PC không thể làm trực tiếp do OS không phải real-time.

**How:**
- Nhận chuỗi `"180,90,135,75,90,40\n"` qua Serial 9600 baud
- Xác thực từng giá trị nằm trong `[minAngle, maxAngle]` của từng khớp
- Map góc sang pulse microseconds: `map(angle, min, max, 500, 2500)`
- Gọi `servo.writeMicroseconds()` để phát xung PWM

| Khớp | Key | Pin | Range | Home |
|------|-----|-----|-------|------|
| Base | S0 | 3 | 0–360° | 180° |
| Shoulder | S1 | 5 | 0–180° | 90° |
| Elbow | S2 | 6 | 0–270° | 135° |
| Wrist Pitch | S3 | 9 | 0–150° | 75° |
| Wrist Roll | S4 | 10 | 0–180° | 90° |
| Gripper | S5 | 11 | 25–70° | 40° |

---

### Backend Server (`server/main.py`)

**What:** HTTP server Python thuần (không dùng framework), expose REST API để điều khiển robot.

**Why:** Tách biệt logic điều khiển khỏi phần cứng và giao diện. Web dashboard và automation script đều giao tiếp qua một điểm duy nhất — dễ thêm tính năng mà không chạm vào firmware.

**How:**
- `RobotArmController` chạy thread gửi dữ liệu tới Arduino mỗi **50ms**
- Thread riêng biệt cho motion sequence (để không block API)
- Có **ramp interpolation**: di chuyển mượt từ góc hiện tại đến góc đích theo từng bước 3°
- Hỗ trợ `--mock` để chạy mà không cần phần cứng
- Tự động reconnect khi mất kết nối serial

**API endpoints:**

```
GET  /api/config          — danh sách cấu hình các khớp
GET  /api/state           — trạng thái hiện tại toàn bộ robot
POST /api/joints          — đặt góc thủ công cho các khớp
POST /api/home            — đưa tất cả khớp về vị trí home
POST /api/sort            — kích hoạt chuỗi phân loại tự động (color: "red"|"blue")
POST /api/emergency-stop  — dừng khẩn cấp
```

---

### Vision Module (`server/automation/vision.py`)

**What:** Module xử lý ảnh dùng OpenCV để phát hiện vật thể màu đỏ/xanh từ camera.

**Why:** Không gian màu HSV tách biệt màu sắc (Hue) khỏi độ sáng (Value), giúp nhận diện ổn định hơn RGB khi điều kiện ánh sáng thay đổi.

**How:**
1. **Gaussian Blur (7×7):** làm mờ nhẹ để loại nhiễu pixel
2. **BGR→HSV conversion:** chuyển không gian màu
3. **HSV thresholding:** lọc pixel theo dải Hue/Saturation/Value
   - *Lưu ý:* màu đỏ cần 2 dải vì Hue vòng tròn (0° và 360° là cùng màu)
4. **Morphological OPEN/CLOSE:** xóa nhiễu nhỏ và lấp lỗ hổng
5. **Contour detection:** tìm đường viền vật thể
6. **Scoring:** `confidence = 0.65 × area_score + 0.35 × fill_score`
7. **Stability filter:** chỉ chấp nhận detection khi màu ổn định qua ≥6 frame liên tiếp

---

### Automation Runner (`server/automation/operation_based_on_vision.py`)

**What:** Script điều phối toàn bộ chu trình pick-and-place tự động.

**Why:** Tách logic điều phối ra khỏi vision và server — mỗi module chỉ làm một việc, dễ test và thay thế.

**How:**
- Dùng `CameraVision.wait_for_object()` để chờ vật thể ổn định
- Thực hiện sequence pick → place → home qua `POST /api/joints` (ramp mượt)
- `_wait_until_ready()`: chờ robot không bận trước khi bắt đầu
- Vòng lặp vô hạn — tự động lặp lại sau mỗi chu kỳ
- Xử lý `KeyboardInterrupt` gracefully: gửi lệnh home trước khi thoát

---

### Web Dashboard (`web/`)

**What:** Giao diện web React + Vite để điều khiển robot từ trình duyệt.

**Why:** Cho phép điều khiển thủ công, kiểm tra trạng thái và trigger lệnh mà không cần CLI — tiện lợi cho demo và debug.

**How:**
- React 19 + Vite 7 (hot-reload trong dev)
- Poll `GET /api/state` định kỳ để cập nhật trạng thái real-time
- Gửi `POST /api/joints`, `POST /api/home`, `POST /api/sort` để điều khiển

---

## REST API Reference

### `GET /api/state`
```json
{
  "connected": true,
  "mock": false,
  "port": "/dev/ttyACM0",
  "baudRate": 9600,
  "busy": false,
  "emergencyStopped": false,
  "sequenceName": "",
  "joints": { "S0": 180, "S1": 90, "S2": 135, "S3": 75, "S4": 90, "S5": 40 },
  "frame": "180,90,135,75,90,40\n"
}
```

### `POST /api/joints`
```json
// Request
{ "joints": { "S0": 90, "S1": 45 } }

// Response
{ "ok": true, "joints": { "S0": 90, "S1": 45, "S2": 135, ... } }
```

### `POST /api/sort`
```json
// Request
{ "color": "red" }  // hoặc "blue"

// Response
{ "ok": true, "busy": true, "sequenceName": "sort-red" }
```

### `POST /api/emergency-stop`
```json
// Response
{ "ok": true, "state": { "emergencyStopped": true, ... } }
```

> **Lưu ý:** Sau emergency stop, phải gọi `POST /api/home` để reset trước khi tiếp tục.

---

## Cấu hình nâng cao

### Điều chỉnh vùng nhận diện (ROI)

```bash
python server/automation/operation_based_on_vision.py \
    --pick-roi "100,50,400,350"   # x,y,width,height — vùng chờ pick
```

### Tăng độ nhạy nhận diện

```bash
# Giảm số frame cần ổn định (nhanh hơn nhưng dễ false positive)
python server/automation/operation_based_on_vision.py --stable-frames 3

# Tăng diện tích tối thiểu của vật thể (bỏ qua vật quá nhỏ)
python server/automation/operation_based_on_vision.py --min-area 3000
```

### Chạy headless (không GUI)

```bash
python server/automation/operation_based_on_vision.py --no-preview
```

### Debug vision độc lập

```bash
# Xem camera với bounding box overlay, không điều khiển robot
python server/automation/vision.py --camera-index 0 --timeout 120
```
