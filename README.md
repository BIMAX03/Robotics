# Robotics và Ứng Dụng

Dự án này phát triển một hệ thống robot tay điều khiển và phân loại, gồm cả phần mềm điều khiển, xử lý ảnh và giao diện người dùng web/mobile.

## Tổng quan

Hệ thống bao gồm các thành phần chính:

- `servo/main.cpp`: chương trình Arduino nhận giá trị góc từ USB serial và điều khiển 6 servo tương ứng.
- `server/manual_control.py`: API HTTP điều khiển robot tay, hỗ trợ điều khiển thủ công, về home, dừng khẩn cấp và chạy kịch bản phân loại tự động.
- `server/vision_sorter.py`: mô-đun nhận diện màu với OpenCV và gửi lệnh phân loại đến API robot tay.
- `controler.py`: giao diện điều khiển trực tiếp servo bằng slider và phím nóng.
- `web/`: ứng dụng React/Vite cho giao diện điều khiển robot tay từ trình duyệt.
- `mobile/`: ứng dụng Expo/React Native cho giao diện điều khiển trên điện thoại.

## Cấu trúc thư mục

- `controler.py`: GUI desktop điều khiển 3 servo.
- `requirements.txt`: thư viện Python cần cài đặt.
- `server/manual_control.py`: API backend điều khiển robot tay.
- `server/vision_sorter.py`: xử lý hình ảnh, phát hiện màu và gọi API để phân loại.
- `servo/main.cpp`: firmware Arduino cho robot tay.
- `web/`: front-end React cho điều khiển qua trình duyệt.
- `mobile/`: front-end Expo cho điều khiển trên thiết bị di động.

## Yêu cầu hệ thống

- Python 3.11+ với thư viện trong `requirements.txt`
- Arduino hoặc board tương thích với thư viện Servo
- OpenCV và camera USB
- Trình duyệt web hiện đại để chạy `web/`
- Node.js và npm để chạy `web/` và `mobile/`

## Cài đặt

1. Cài Python và thư viện:

```bash
python -m pip install -r requirements.txt
```

2. Nạp `servo/main.cpp` vào Arduino để điều khiển servo qua cổng serial.

3. Nếu dùng giao diện web:

```bash
cd web
npm install
npm run dev
```

4. Nếu dùng giao diện mobile:

```bash
cd mobile
npm install
npm run start
```

## Chạy hệ thống

### Khởi động API robot tay

```bash
python server/manual_control.py --host 0.0.0.0 --http-port 8000
```

### Chạy điều khiển trực tiếp qua GUI desktop

```bash
python controler.py
```

### Chạy phân loại bằng camera

```bash
python server/vision_sorter.py --api-base http://127.0.0.1:8000 --camera-index 0
```

## Giao diện web

- `web/` chứa ứng dụng React dùng API `/api/state`, `/api/joints` và `/api/sort`.
- Môi trường sử dụng Vite và React 19.

## Giao diện mobile

- `mobile/` là ứng dụng Expo React Native để điều khiển robot qua thiết bị di động.

## Tính năng chính

- Điều khiển servo thủ công và theo phím nóng.
- API HTTP cho trạng thái robot và lệnh điều khiển.
- Chạy kịch bản phân loại tự động theo màu đỏ/xanh.
- Firmware Arduino xử lý chuỗi góc và xuất xung servo.

## Ghi chú

- Các thông số như cổng serial, baud rate, camera index có thể điều chỉnh trong mã nguồn.
- Nếu cần mở rộng, có thể thêm chế độ điều khiển bằng joystick hoặc cải tiến nhận diện hình ảnh.
