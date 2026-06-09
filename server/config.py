"""
config.py — Toàn bộ thông số cấu hình của hệ thống robot tay.

Chỉnh sửa file này để thay đổi hành vi của server và automation
mà không cần đụng vào logic nghiệp vụ bên trong các module khác.
"""

# =============================================================================
# CẤU HÌNH SERIAL (kết nối Arduino)
# =============================================================================

# Cổng serial mà Arduino kết nối vào (trên Linux thường là /dev/ttyACM0 hoặc /dev/ttyUSB0)
DEFAULT_SERIAL_PORT = "/dev/ttyACM0"

# Tốc độ truyền dữ liệu serial — phải khớp với Serial.begin() trong firmware Arduino
DEFAULT_BAUD_RATE = 9600

# =============================================================================
# CẤU HÌNH HTTP SERVER
# =============================================================================

# Địa chỉ IP mà server lắng nghe (127.0.0.1 = chỉ local; 0.0.0.0 = cho phép truy cập từ mạng ngoài)
DEFAULT_HOST = "127.0.0.1"

# Cổng HTTP của REST API
DEFAULT_HTTP_PORT = 8000

# =============================================================================
# CẤU HÌNH VÒNG LẶP GỬI LỆNH
# =============================================================================

# Khoảng thời gian (giây) giữa hai lần gửi góc servo xuống Arduino.
# Nhỏ hơn → phản hồi nhanh hơn, nhưng tốn băng thông serial hơn.
# Khuyến nghị: 0.05 (20 lần/giây)
SEND_INTERVAL = 0.04

# Số độ tối đa server được phép thay đổi mỗi lần gửi frame xuống Arduino.
# Đây là lớp smoothing trung tâm cho mọi lệnh /api/joints và /api/sort.
# Nhỏ hơn → mượt hơn nhưng chậm hơn. 1.5–2.5 thường là vùng dễ dùng.
MOTION_STEP_DEGREES = 3.0

# Thời gian chờ (giây) trước kh0i thử kết nối lại sau khi mất kết nối serial.
RECONNECT_INTERVAL = 2.0

# =============================================================================
# CẤU HÌNH CHUỖI PHÂN LOẠI TỰ ĐỘNG (SORT SEQUENCE)
# =============================================================================

# Thời gian chờ (giây) sau mỗi bước động tác trong chuỗi sort,
# cho servo kịp ổn định trước khi chuyển sang bước tiếp theo.
SORT_SETTLE_DELAY = 0.8

# =============================================================================
# CẤU HÌNH CÁC KHỚP (JOINTS)
# =============================================================================
# Mỗi khớp gồm: key (định danh), label (tên hiển thị), pin (chân PWM Arduino),
#               min (góc tối thiểu), max (góc tối đa), home (góc vị trí gốc).

JOINTS_CONFIG = [
    # (key,  label,         pin,  min,  max,  home)
    ("S0", "Base",          3,    0,    360,  180),  # Đế xoay — toàn vòng 360°
    ("S1", "Shoulder",      5,    0,    180,   90),  # Vai — nâng/hạ cánh tay
    ("S2", "Elbow",         6,    0,    270,  135),  # Khuỷu tay
    ("S3", "Wrist Pitch",   9,    0,    150,   75),  # Cổ tay — nghiêng lên/xuống
    ("S4", "Wrist Roll",   10,    0,    180,   90),  # Cổ tay — xoay
    ("S5", "Gripper",      11,   25,     70,   40),  # Kẹp — 25°=mở rộng, 70°=kẹp chặt
]

# =============================================================================
# CẤU HÌNH VỊ TRÍ THẢ VẬT (DROP-OFF) THEO MÀU
# =============================================================================
# Góc của khớp S0 (Base) khi thả vật xuống vị trí tương ứng với màu.
# Điều chỉnh giá trị này nếu vị trí thùng phân loại thay đổi.

SORT_DROPOFFS = {
    "blue": 360,  # Thùng màu xanh ở góc 360° (bên trái)
    "red":    0,  # Thùng màu đỏ  ở góc 0°   (bên phải)
}

# =============================================================================
# CẤU HÌNH AUTOMATION (operation_based_on_vision.py)
# =============================================================================

# Địa chỉ REST API của server để automation gọi lệnh
DEFAULT_API_BASE = "http://127.0.0.1:8000"

# Thời gian tối đa (giây) chờ phản hồi từ một HTTP request tới server
REQUEST_TIMEOUT = 2.0

# Thời gian chờ ổn định sau khi server báo đã tới pose.
POSE_SETTLE_DELAY = 0.45

# Thêm thời gian chờ theo quãng đường servo vừa đi.
# Ví dụ delta 60° và hệ số 0.01 → chờ thêm 0.6 giây sau khi tới target nội bộ.
POSE_SETTLE_PER_DEGREE = 0.01

# Sai số chấp nhận được khi kiểm tra currentJoints đã tới pose.
POSE_TOLERANCE_DEGREES = 0

# Timeout tối đa khi chờ một pose hoàn thành.
POSE_TIMEOUT = 8.0

# Thời gian tối đa (giây) chờ phát hiện vật thể trước khi thử lại.
DETECT_TIMEOUT = 60.0

# =============================================================================
# CẤU HÌNH CÁC CHUỖI ĐỘNG TÁC (SEQUENCES)
# =============================================================================
# Mỗi bước là một dict {joint_key: angle}.
# Automation sẽ ramp mượt từ góc hiện tại đến góc đích.

# Chuỗi nhặt vật (pick): hạ tay → kẹp → nâng tay
PICK_SEQUENCE = [
    {"S1": 15},   # Bước 1: Hạ vai xuống để tay chạm vật
    {"S5": 65},   # Bước 2: Đóng gripper để kẹp vật
    {"S1": 60},   # Bước 3: Nâng vai lên, giữ nguyên vật
]

# Chuỗi thả vật (place) theo màu: xoay base → hạ tay → nhả → nâng tay
PLACE_SEQUENCE = {
    "blue": [
        {"S0": 360},  # Xoay base sang vị trí thùng màu xanh
        {"S1": 15},   # Hạ vai xuống trên thùng
        {"S5": 60},   # Mở gripper, thả vật
        {"S1": 60},   # Nâng vai lên
    ],
    "red": [
        {"S0": 0},    # Xoay base sang vị trí thùng màu đỏ
        {"S1": 15},   # Hạ vai xuống trên thùng
        {"S5": 60},   # Mở gripper, thả vật
        {"S1": 60},   # Nâng vai lên
    ],
}

# =============================================================================
# CẤU HÌNH VISION (vision.py)
# =============================================================================

# Index camera (0 = camera USB đầu tiên, 1 = camera thứ hai, ...)
CAMERA_INDEX = 0

# Độ phân giải frame camera
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480

# Diện tích pixel tối thiểu của contour để được tính là vật thể hợp lệ.
# Tăng nếu bị nhận diện nhầm nhiễu nhỏ; giảm nếu vật thể ở xa và nhỏ.
MIN_AREA = 1800

# Tỉ lệ diện tích tối đa so với toàn khung hình (tránh nhận cả background).
MAX_AREA_RATIO = 0.65

# Tỉ lệ lấp đầy tối thiểu (area / bounding_box_area).
# Thấp → chấp nhận hình dạng không đều; cao → chỉ nhận vật gần hình chữ nhật.
MIN_FILL_RATIO = 0.22

# Ngưỡng confidence tối thiểu để xác nhận detection (0.0–1.0).
MIN_CONFIDENCE = 0.55

# Số frame liên tiếp cùng màu trước khi xác nhận vật thể ổn định.
# Tăng → ổn định hơn, chậm hơn; giảm → phản ứng nhanh hơn, dễ false positive.
STABLE_FRAMES = 6

# Số frame bỏ qua khi camera mới khởi động (để ổn định phơi sáng)
CAMERA_WARMUP_FRAMES = 8

# Chỉ xử lý 1 trong mỗi N frame (1 = xử lý tất cả, 2 = bỏ qua 1 frame/lần, ...)
PROCESS_EVERY = 1

# Tỉ lệ thu nhỏ cửa sổ preview (1.0 = nguyên kích thước, 0.7 = thu 70%)
PREVIEW_SCALE = 0.7

# Dải màu HSV để nhận diện vật thể
# Định dạng: {"màu": [(lower_HSV, upper_HSV), ...]}
# Màu đỏ cần 2 dải vì Hue đỏ nằm ở cả đầu (0°) và cuối (180°) vòng tròn HSV
HSV_RANGES = {
    "blue": [
        ((95, 80, 50), (135, 255, 255)),
    ],
    "red": [
        ((0,   90, 50), (10,  255, 255)),  # Đỏ phía dưới vòng tròn Hue
        ((170, 90, 50), (180, 255, 255)),  # Đỏ phía trên vòng tròn Hue
    ],
}
