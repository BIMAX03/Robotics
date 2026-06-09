"""
api.py — Lớp xử lý HTTP và toàn bộ phần networking của server.

File này chứa:
  - ApiHandler : lớp nhận request HTTP từ client (web dashboard, automation script,
                 hoặc bất kỳ HTTP client nào) và chuyển thành lời gọi vào controller.
  - build_http_server() : hàm khởi tạo ThreadingHTTPServer và gắn controller vào.

Tách ra file riêng để dễ:
  - Thêm route mới mà không đụng vào logic điều khiển phần cứng.
  - Swap sang framework khác (Flask, FastAPI...) nếu cần mà không sửa controller.
"""

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, TYPE_CHECKING

# Import kiểu tĩnh để type-checker hiểu, không gây vòng lặp import lúc runtime
if TYPE_CHECKING:
    from server.controller import RobotArmController, JOINTS


# ---------------------------------------------------------------------------
# CORS HEADERS
# ---------------------------------------------------------------------------
# Trình duyệt chặn request từ origin khác (ví dụ web chạy ở :5173 gọi API :8000).
# Ba header này báo cho trình duyệt biết server chấp nhận cross-origin requests.
CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",               # Cho phép mọi origin
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",  # Các HTTP method được phép
    "Access-Control-Allow-Headers": "Content-Type",    # Header được phép gửi kèm
}


class ApiHandler(BaseHTTPRequestHandler):
    """
    Lớp xử lý từng HTTP request đến từ client.

    Python's BaseHTTPRequestHandler gọi do_GET / do_POST / do_OPTIONS tương ứng
    với HTTP method. Mỗi method đọc request, gọi controller, rồi trả JSON về.

    Thuộc tính class `controller` được gắn từ bên ngoài (trong build_http_server)
    để tất cả instance của handler đều dùng chung một controller duy nhất.
    """

    # Thuộc tính class — được gắn bởi build_http_server() trước khi server chạy
    controller: "RobotArmController"
    joints:     list  # danh sách Joint objects, dùng cho GET /api/config

    # -----------------------------------------------------------------------
    # OPTIONS — preflight CORS
    # -----------------------------------------------------------------------
    def do_OPTIONS(self) -> None:
        """
        Trình duyệt gửi OPTIONS trước mỗi POST cross-origin để "hỏi thăm" server.
        Trả 204 No Content + CORS headers để trình duyệt biết được phép gọi tiếp.
        """
        self._send_empty(204)

    # -----------------------------------------------------------------------
    # GET — đọc trạng thái, không thay đổi phần cứng
    # -----------------------------------------------------------------------
    def do_GET(self) -> None:
        """
        Xử lý tất cả GET request. Phân nhánh theo self.path.
        """

        if self.path == "/api/config":
            # Trả về cấu hình tĩnh của các khớp (tên, pin, range, home).
            # Client dùng để render UI slider với đúng min/max cho mỗi khớp.
            self._send_json({"joints": [asdict(j) for j in self.joints]})

        elif self.path == "/api/state":
            # Trả về trạng thái thời gian thực: kết nối serial, góc hiện tại,
            # trạng thái busy/emergency, frame string gửi xuống Arduino.
            self._send_json(self.controller.get_state())

        else:
            # Bất kỳ path GET nào không khớp → 404
            self._send_json({"error": "Not found"}, status=404)

    # -----------------------------------------------------------------------
    # POST — ra lệnh, thay đổi trạng thái phần cứng
    # -----------------------------------------------------------------------
    def do_POST(self) -> None:
        """
        Xử lý tất cả POST request. Đọc JSON body, phân nhánh theo self.path,
        gọi controller tương ứng rồi trả kết quả.

        Bất kỳ ValueError nào từ controller (tham số sai, arm đang bận...) đều
        được bắt ở đây và trả về lỗi 400 Bad Request thay vì crash server.
        """
        try:
            body = self._read_json()  # Đọc và parse JSON body từ request

            if self.path == "/api/joints":
                # Đặt góc thủ công cho một hoặc nhiều khớp.
                # Body: {"joints": {"S0": 90, "S1": 45, ...}}
                values = body.get("joints", body)
                if not isinstance(values, dict):
                    # Validate: joints phải là object, không phải array hay string
                    raise ValueError("request body must contain a joints object")
                joints = self.controller.set_joints(values)
                # Trả về toàn bộ góc hiện tại sau khi áp dụng để client đồng bộ UI
                self._send_json({"ok": True, "joints": joints})

            elif self.path == "/api/home":
                # Đưa tất cả khớp về vị trí home, xoá trạng thái busy/emergency.
                # Không cần body — hành động không có tham số.
                joints = self.controller.home()
                self._send_json({"ok": True, "joints": joints})

            elif self.path == "/api/sort":
                # Kích hoạt chuỗi phân loại tự động theo màu.
                # Body: {"color": "red"} hoặc {"color": "blue"}
                color = body.get("color")
                if not isinstance(color, str):
                    raise ValueError("request body must contain color")
                # Controller chạy chuỗi trong thread riêng → trả về ngay lập tức
                self._send_json(self.controller.sort_item(color))

            elif self.path == "/api/emergency-stop":
                # Dừng khẩn cấp: huỷ sequence đang chạy, về home, đặt cờ emergency.
                # Sau lệnh này arm không nhận lệnh mới cho đến khi gọi /api/home.
                self._send_json({"ok": True, "state": self.controller.emergency_stop()})

            else:
                # Path POST không khớp bất kỳ route nào → 404
                self._send_json({"error": "Not found"}, status=404)

        except ValueError as exc:
            # Controller raise ValueError khi tham số không hợp lệ hoặc arm bận.
            # Bắt ở đây để server không crash, trả 400 với message lỗi rõ ràng.
            self._send_json({"error": str(exc)}, status=400)

    # -----------------------------------------------------------------------
    # Tắt log mặc định của BaseHTTPRequestHandler (spam terminal)
    # -----------------------------------------------------------------------
    def log_message(self, format, *args) -> None:  # noqa: A002
        """
        Ghi đè để tắt dòng log "GET /api/state HTTP/1.1 200 -" in ra mỗi request.
        Web dashboard poll liên tục → log này sẽ spam terminal nếu không tắt.
        """
        return

    # -----------------------------------------------------------------------
    # HELPER METHODS — đọc/ghi HTTP
    # -----------------------------------------------------------------------

    def _read_json(self) -> Dict[str, object]:
        """
        Đọc body của request và parse thành dict Python.

        Lấy Content-Length từ header để biết cần đọc bao nhiêu byte.
        Nếu không có body (Content-Length = 0) thì trả dict rỗng — tiện cho
        các POST không cần body như /api/home, /api/emergency-stop.
        """
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}  # POST không có body → coi như body rỗng, không lỗi

        # Đọc đúng số byte, decode UTF-8, parse JSON → dict
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send_empty(self, status: int) -> None:
        """
        Gửi response không có body, chỉ có status code và CORS headers.
        Dùng cho OPTIONS preflight — không cần trả dữ liệu gì, chỉ cần headers.
        """
        self.send_response(status)   # Ghi dòng "HTTP/1.1 204 No Content"
        self._send_headers()         # Gắn CORS headers
        self.end_headers()           # Kết thúc phần header, bắt đầu body (rỗng)

    def _send_json(self, payload: Dict[str, object], status: int = 200) -> None:
        """
        Serialize payload thành JSON rồi gửi về client.

        Luôn gắn Content-Type: application/json và Content-Length để client
        biết cách đọc và không phải đoán kích thước body.
        """
        data = json.dumps(payload).encode("utf-8")  # Dict → bytes JSON
        self.send_response(status)                   # Dòng status HTTP
        self._send_headers()                         # CORS headers
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))  # Bắt buộc để client đọc đúng
        self.end_headers()
        self.wfile.write(data)  # Ghi body JSON xuống socket

    def _send_headers(self) -> None:
        """
        Gắn các CORS header vào response hiện tại.

        Tách thành method riêng để cả _send_empty lẫn _send_json đều dùng chung,
        tránh lặp code và đảm bảo CORS header luôn nhất quán trên mọi response.
        """
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)


# ---------------------------------------------------------------------------
# FACTORY — tạo và cấu hình HTTP server
# ---------------------------------------------------------------------------

def build_http_server(
    host: str,
    port: int,
    controller: "RobotArmController",
    joints: list,
) -> ThreadingHTTPServer:
    """
    Tạo ThreadingHTTPServer và gắn controller + joints vào ApiHandler.

    Tại sao dùng ThreadingHTTPServer thay vì HTTPServer thường?
    → Mỗi request được xử lý trong thread riêng, nên các lệnh POST dài
      (ví dụ /api/sort) không block các GET /api/state poll từ web dashboard.

    Tại sao gắn controller vào class attribute thay vì instance?
    → BaseHTTPRequestHandler tạo instance mới cho mỗi request, nên không thể
      truyền controller qua __init__. Gắn vào class attribute là cách chuẩn.

    Args:
        host       : địa chỉ IP server lắng nghe (vd: "127.0.0.1")
        port       : cổng HTTP (vd: 8000)
        controller : instance RobotArmController đã khởi tạo
        joints     : danh sách Joint objects để trả về trong GET /api/config

    Returns:
        ThreadingHTTPServer đã cấu hình, chưa bắt đầu serve.
    """
    # Gắn controller và joints vào class — tất cả instance handler đều truy cập được
    ApiHandler.controller = controller
    ApiHandler.joints     = joints

    # Tạo server: (host, port) là địa chỉ lắng nghe, ApiHandler là handler class
    server = ThreadingHTTPServer((host, port), ApiHandler)
    return server
