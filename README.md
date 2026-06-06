# 🌊 HỆ THỐNG DỰ BÁO KHÍ TƯỢNG HẢI DƯƠNG & BÃO BIỂN ĐÔNG (37 TRẠM)

[![Python Version](https://img.shields.io/badge/python-3.10-blue)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-v15+-black)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.100+-emerald)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compatible-blue)](https://www.docker.com/)
[![XGBoost](https://img.shields.io/badge/XGBoost-v1.6+-orange)](https://xgboost.readthedocs.io/)

Hệ thống Học máy Đa nhiệm (Multi-Task Learning) và Giám sát Thời gian thực quy mô **37 trạm khí tượng** bao phủ toàn bộ Biển Đông (32 trạm đất liền/ven biển và 5 trạm phao ảo vùng biển sâu). Dự án đã được nâng cấp lên kiến trúc decoupled hiện đại: **FastAPI Backend + Next.js Frontend** kết hợp bộ lưu trữ cơ sở dữ liệu PostgreSQL, Cache Redis, hệ thống quản lý tài khoản JWT và dịch vụ Cảnh báo bão tự động qua Email/Telegram.

---

## ✨ Kiến Trúc Hệ Thống Mới

Dự án sử dụng mô hình thiết kế Microservices và phân tách ứng dụng (Decoupled Architecture) được đóng gói hoàn chỉnh bằng Docker:

1.  **Next.js Frontend (Cổng 3000):**
    *   Sử dụng **TypeScript** và **Tailwind CSS** xây dựng giao diện Dashboard mượt mà.
    *   **Bản đồ SVG Biển Đông tương tác** (phạm vi tọa độ 5°N-25°N và 100°E-125°E) hiển thị 37 trạm trực quan đổi màu theo cấp bão thực tế.
    *   Hộp tìm kiếm, lọc cấp độ bão, biểu đồ Recharts phân tích xu hướng 24h và bảng quản lý **Watchlist (Danh sách theo dõi)** cá nhân của từng người dùng.
    *   Trang kiểm định Benchmark độc lập chống lại Naive Baseline và kiểm chứng các định luật vật lý hải dương.
2.  **FastAPI Backend (Cổng 8000):**
    *   Định tuyến API cung cấp dữ liệu khí quyển học, nạp và chạy dự báo bằng **3 mô hình XGBoost** từ thư mục `models/` gốc.
    *   Tích hợp hệ thống phân quyền an toàn **JWT (JSON Web Token)** hỗ trợ đăng ký, đăng nhập và lưu danh sách trạm theo dõi Watchlist.
    *   Tiến trình ngầm (Background Task) chạy **sau mỗi 3 giờ**, tải dữ liệu vệ tinh Open-Meteo, chạy dự báo XGBoost và cập nhật sẵn vào cơ sở dữ liệu.
3.  **PostgreSQL Database (Cổng 5432):**
    *   Lưu trữ dữ liệu trạm khí tượng, tài khoản người dùng, danh sách watchlist và kết quả dự báo thời tiết tính toán sẵn. Nhờ đó, tốc độ tải trang phía Frontend đạt tốc độ cực đại **dưới 5ms** (sub-50ms).
4.  **Redis Cache (Cổng 6379):**
    *   Đóng vai trò lớp cache hiệu năng cao, giảm tải lượng truy vấn lặp lại và đồng bộ hóa phiên hoạt động.

---

## 🌀 Bảng Phân Cấp Khí Tượng (Chuẩn Việt Nam/Biển Đông)

Phân loại cấp độ bão dựa trên **tốc độ gió duy trì cực đại gần tâm** ($V_{\max}$ - m/s):

| Cấp | Nhãn Khí Tượng | Ngưỡng Gió ($V_{\max}$) | Mô tả & Tương thích quốc tế |
| :---: | :--- | :---: | :--- |
| **0** | Bình thường / Vùng áp thấp yếu | $< 10.8\text{ m/s}$ | Gió dưới cấp 6 Beaufort |
| **1** | Áp thấp nhiệt đới | $10.8\text{ - }17.1\text{ m/s}$ | Gió cấp 6-7 Beaufort (Tropical Depression) |
| **2** | Bão thường | $17.2\text{ - }24.4\text{ m/s}$ | Gió cấp 8-9 Beaufort (Tropical Storm) |
| **3** | Bão mạnh | $24.5\text{ - }32.6\text{ m/s}$ | Gió cấp 10-11 Beaufort (Severe Tropical Storm) |
| **4** | Bão rất mạnh | $32.7\text{ - }50.9\text{ m/s}$ | Gió cấp 12-15 Beaufort (Typhoon / Hurricane Cat 1-2) |
| **5** | Siêu bão | $\ge 51.0\text{ m/s}$ | Gió cấp 16 trở lên (Super Typhoon / Major Hurricane) |

---

## 🚀 Hướng Dẫn Khởi Chạy Nhanh Bằng Docker (Khuyên Dùng)

Phương pháp đơn giản và nhanh nhất để khởi động toàn bộ hạ tầng (PostgreSQL, Redis, Backend, Frontend) chỉ bằng 1 câu lệnh duy nhất:

### Bước 1: Chuẩn bị tệp cấu hình bảo mật `.env`
Sao chép tệp cấu hình mẫu `.env.example` thành `.env` ở thư mục gốc của dự án:
```bash
cp .env.example .env
```
Mở tệp `.env` vừa tạo và chỉnh sửa các tham số bảo mật nhạy cảm (như mật khẩu PostgreSQL, JWT Secret, Token Telegram Bot nhận tin bão và cấu hình Gmail SMTP của bạn).

### Bước 2: Build và Khởi chạy bằng Docker Compose
Chạy câu lệnh dưới đây để tự động tải các Docker images, thiết lập mạng nội bộ, tạo phân vùng lưu trữ dữ liệu (volumes) và khởi động 4 container:
```bash
docker-compose up --build -d
```

### Bước 3: Truy cập và Kiểm tra hệ thống
Sau khi khởi động thành công, các dịch vụ sẽ hoạt động tại các địa chỉ:
*   **Giao diện Next.js Dashboard:** [http://localhost:3000](http://localhost:3000)
*   **Tài liệu tương tác FastAPI Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)

Để kiểm tra nhật ký hoạt động (logs) hoặc dừng hệ thống:
```bash
# Xem logs thời gian thực của backend
docker-compose logs -f backend

# Dừng và gỡ bỏ toàn bộ container
docker-compose down
```

---

## 🛠️ Hướng Dẫn Vận Hành Cục Bộ (Không Dùng Docker)

Nếu bạn muốn chạy phát triển thủ công trên máy tính cá nhân:

### 1. Khởi chạy FastAPI Backend
1. Cài đặt các thư viện dependencies từ tệp `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```
2. Khởi chạy server FastAPI sử dụng `uvicorn`:
   ```bash
   $env:PYTHONPATH="backend"; uvicorn app.main:app --reload
   ```
   *Mẹo:* Khi khởi chạy thủ công không cấu hình `DATABASE_URL` trong môi trường, Backend sẽ tự động sinh tệp SQLite cục bộ `weather.db`, tự động nạp Seed 37 trạm và kích hoạt bộ Worker chạy ngầm phục vụ dữ liệu.

### 2. Khởi chạy Next.js Frontend
1. Truy cập thư mục `frontend/` và cài đặt các gói NPM:
   ```bash
   cd frontend
   npm install
   ```
2. Khởi động môi trường phát triển (Development Server):
   ```bash
   npm run dev
   ```
3. Truy cập trình duyệt tại địa chỉ [http://localhost:3000](http://localhost:3000).

---

## 🚨 Dịch Vụ Cảnh Báo Tự Động & Thiết Bị IoT (Raspberry Pi)

1.  **Dịch vụ Cảnh Báo Tự Động (Auto-Alert Service):**
    *   Khi bộ Worker ngầm phát hiện một trạm khí tượng trong **Watchlist (Danh sách theo dõi)** của người dùng có dấu hiệu **nâng cấp bão khẩn cấp (Cấp 1 trở lên)**, hệ thống sẽ tự động kích hoạt gửi cảnh báo.
    *   **Kênh Email:** Soạn thư cảnh báo chính thức chứa chi tiết thông số sức gió, sóng biển, khí áp gửi tới Email người dùng đã đăng ký.
    *   **Kênh Telegram:** Gọi API của Telegram Bot để gửi thông điệp khẩn cấp (chữ đậm kèm biểu tượng cảnh báo 🚨) trực tiếp tới Telegram Chat ID của người dùng.
2.  **Thiết bị IoT (Raspberry Pi):**
    *   Để thiết bị Raspberry Pi gửi trực tiếp tín hiệu hoạt động, cập nhật script `src/heartbeat.py` của bạn để gửi yêu cầu POST định kỳ 15 giây trực tiếp tới endpoint mới của máy chủ:
        `POST http://<dia_chi_IP_may_chu>:8000/api/iot/heartbeat`
