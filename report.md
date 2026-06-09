# Tiểu Luận Kết Thúc Môn Robotics và Ứng Dụng

## 1. Giới thiệu

Tiểu luận này trình bày một hệ thống robot tay ứng dụng trong phân loại vật thể theo màu sắc. Dự án tập trung vào việc kết hợp điều khiển servo với xử lý ảnh, nhằm xây dựng một giải pháp robot có thể tự động nhận diện và phân loại vật thể.

## 2. Mục tiêu nghiên cứu

Tiểu luận đặt ra các mục tiêu sau:

- Thiết kế hệ thống điều khiển robot tay sử dụng servo và Arduino.
- Xây dựng API điều khiển robot tay theo mô hình client-server.
- Triển khai thuật toán nhận diện màu sắc bằng OpenCV.
- Tự động hoá quá trình phân loại vật thể dựa trên màu đỏ và xanh.
- Đánh giá tính hiệu quả của hệ thống trong các thử nghiệm.

## 3. Cơ sở lý thuyết

Hệ thống được xây dựng dựa trên các khái niệm chính sau:

- Servo và điều khiển góc quay.
- Truyền thông serial giữa máy tính và Arduino.
- API RESTful cho điều khiển robot.
- Xử lý ảnh với không gian màu HSV.
- Phân tích contour và lọc nhiễu để nhận diện đối tượng.

## 4. Phương pháp nghiên cứu

Phương pháp nghiên cứu được thực hiện theo các bước:

1. Nghiên cứu tài liệu về điều khiển servo và giao thức serial.
2. Thiết kế firmware Arduino xử lý dữ liệu nhập từ cổng serial.
3. Phát triển backend Python cung cấp API điều khiển robot tay.
4. Xây dựng module xử lý ảnh để phát hiện màu và ra lệnh phân loại.
5. Kiểm thử từng phần và tích hợp hệ thống.

## 5. Thiết kế hệ thống

### 5.1 Kiến trúc tổng quát

Hệ thống gồm ba lớp chính:

- Lớp điều khiển phần cứng: `servo/main.cpp` chạy trên Arduino, nhận dữ liệu góc và điều khiển 6 servo.
- Lớp backend: `server/main.py` cung cấp API HTTP, quản lý trạng thái robot và kịch bản động.
- Lớp xử lý ảnh: `server/vision_sorter.py` đọc camera, nhận diện màu và gọi API để phân loại.

### 5.2 Thành phần chính

- `controler.py`: ứng dụng desktop điều khiển 3 servo qua giao diện kéo thả và phím nóng.
- `web/`: ứng dụng web React hiển thị trạng thái robot và điều khiển qua trình duyệt.
- `mobile/`: ứng dụng Expo React Native cho điều khiển điện thoại.

### 5.3 Thiết kế giao tiếp

- Firmware Arduino đọc chuỗi `S0,S1,S2,S3,S4,S5\n` từ serial.
- Backend Python gửi các góc servo tới Arduino và nhận trạng thái.
- Module phân loại gửi yêu cầu `POST /api/sort` khi phát hiện màu hợp lệ.

## 6. Triển khai chi tiết

### 6.1 Firmware Arduino

Firmware xác thực dữ liệu đầu vào, ánh xạ góc hợp lệ sang xung servo và cập nhật góc hiện tại. Thiết kế này đảm bảo robot không hoạt động ngoài biên độ an toàn.

### 6.2 Backend Python

`server/main.py` định nghĩa cấu hình khớp, API trạng thái và lệnh. Hệ thống hỗ trợ:

- `GET /api/state`
- `POST /api/joints`
- `POST /api/sort`
- `POST /api/emergency-stop`

### 6.3 Xử lý ảnh

`server/vision_sorter.py` sử dụng OpenCV để:

- Chuyển ảnh sang không gian HSV.
- Áp dụng ngưỡng màu cho xanh và đỏ.
- Tìm contour lớn nhất thỏa điều kiện diện tích.
- Gửi lệnh phân loại khi màu được xác nhận ổn định.

### 6.4 Giao diện người dùng

- `web/` cung cấp điều khiển robot trên trình duyệt.
- `mobile/` cung cấp điều khiển trên điện thoại di động.

## 7. Thử nghiệm và đánh giá

### 7.1 Môi trường thử nghiệm

- Phần cứng: Arduino, servo, camera USB.
- Phần mềm: Python, OpenCV, Flask, React, Expo.

### 7.2 Quy trình thử nghiệm

- Kiểm tra kết nối serial và truyền dữ liệu tới Arduino.
- Đánh giá phản hồi robot tay với lệnh điều khiển thủ công.
- Kiểm tra nhận diện màu đỏ và xanh trên camera.
- Quan sát quá trình gọi lệnh phân loại tự động.

### 7.3 Kết quả thực nghiệm

- Thời gian phản hồi của hệ thống: `[thêm dữ liệu thực tế]`
- Tỷ lệ phân loại đúng: `[thêm dữ liệu thực tế]`
- Số lần thất bại trong thử nghiệm: `[thêm dữ liệu thực tế]`

## 8. Thảo luận

- Hệ thống hoạt động theo mô hình client-server, dễ mở rộng.
- Nhận diện màu hiện tại phụ thuộc vào điều kiện ánh sáng và cần hiệu chỉnh.
- Việc điều khiển servo qua serial giúp tách biệt phần mềm điều khiển và phần cứng.
- Giao diện web/mobile là hướng mở rộng phù hợp cho ứng dụng thực tế.

## 9. Kết luận

Tiểu luận chứng minh khả năng xây dựng một hệ thống robot tay phân loại vật thể cơ bản. Dự án đã kết hợp thành công điều khiển servo, xử lý ảnh và API điều khiển.

### 9.1 Kiến nghị

- Nâng cấp thuật toán nhận diện để xử lý nhiều màu và nhiều loại vật thể.
- Thêm cơ chế hiệu chỉnh tự động cho điều kiện ánh sáng khác nhau.
- Tích hợp cơ chế học máy để cải thiện độ chính xác phân loại.

## 10. Tài liệu tham khảo

- [OpenCV documentation](https://opencv.org/)
- Tài liệu Arduino về thư viện Servo.
- Tài liệu Flask và Python REST API.

## 11. Phụ lục

- Mã nguồn `servo/main.cpp`.
- Mã nguồn `server/main.py`.
- Mã nguồn `server/vision_sorter.py`.
- Mã nguồn `controler.py`.
- Hướng dẫn cài đặt `requirements.txt`.
