# 🌊 HỆ THỐNG DỰ BÁO KHÍ TƯỢNG HẢI DƯƠNG & BÃO BIỂN ĐÔNG (37 TRẠM)
### Kiến trúc Tách biệt (Decoupled): FastAPI Backend + Next.js Frontend tối ưu hóa cho Raspberry Pi 3 Model B+ (1GB RAM)

---

## 📌 1. Giới Thiệu Hệ Thống

Dự án là một hệ thống học máy dự báo và giám sát thời gian thực quy mô **37 trạm khí tượng** bao phủ khu vực Biển Đông (bao gồm 32 trạm đất liền/ven biển và 5 trạm phao biển sâu). Hệ thống được tái cấu trúc từ kịch bản Streamlit cũ sang kiến trúc phân tách hiện đại: **FastAPI** làm máy chủ cung cấp API dữ liệu và chạy mô hình học máy, kết hợp **Next.js** xây dựng giao diện Dashboard tương tác hiển thị.

Đặc biệt, toàn bộ giải pháp phần mềm được nghiên cứu cấu hình và tối ưu hóa cực hạn để có thể vận hành ổn định, tự hành khép kín (Self-hosted) trên các thiết bị máy tính nhúng giới hạn tài nguyên như **Raspberry Pi 3 Model B+ (1 GB RAM)** mà không bị tràn bộ nhớ hay quá tải CPU.

---

## 🛠️ 2. Các Công Việc Đã Thực Hiện (Tóm tắt Kỹ thuật)

Trong quá trình triển khai hệ thống trên Raspberry Pi, các giải pháp kỹ thuật sau đã được thực hiện thành công:

1.  **Chuyển đổi sang SQLite cục bộ:** Thay vì sử dụng PostgreSQL và Redis tốn kém hàng trăm MB bộ nhớ tĩnh (RAM), hệ thống được cấu hình tự động chuyển sang cơ sở dữ liệu SQLite (`weather.db`) cục bộ khi không có chuỗi kết nối PostgreSQL. SQLite chỉ tiêu tốn dưới 10MB RAM và đảm bảo tốc độ truy xuất cực nhanh.
2.  **Khắc phục giới hạn RAM 1GB bằng Swap 2GB:** Cấu hình thành công phân vùng bộ nhớ ảo (Swap file) 2GB hoạt động song song với ZRAM mặc định của Pi, nâng tổng dung lượng bộ nhớ ảo lên gần 3GB, giải quyết triệt để lỗi Out-Of-Memory (OOM) khi cài đặt thư viện và biên dịch (build) Next.js.
3.  **Khắc phục lỗi bộ nhớ đệm `pip` trên RAM (`tmpfs`):** Hệ điều hành Raspberry Pi OS giới hạn thư mục tạm `/tmp` trên RAM chỉ có 453MB, gây ra lỗi `No space left on device` khi cài đặt các gói thư viện Python lớn. Vấn đề đã được khắc phục triệt để bằng cách chuyển hướng thư mục tạm của `pip` về thẻ nhớ chính (`export TMPDIR=~/pip_tmp`).
4.  **Tái cấu hình Bản đồ GIS 2D độ chính xác cao (Vector Map):** Thiết kế lại sơ đồ SVG bản đồ tương tác tỷ lệ 500x500. Bổ sung chi tiết mảng lục địa Đông Nam Á, đảo Hải Nam, đảo Đài Loan, quần đảo Philippines, đảo Borneo và hai quần đảo thiêng liêng **Hoàng Sa (VN)**, **Trường Sa (VN)** kèm nhãn chủ quyền và các vector chỉ hướng hải lưu vật lý.
5.  **Tinh giản hóa hệ thống (Tối ưu hóa hiệu năng):** Loại bỏ hoàn toàn các mô-đun không cốt lõi bao gồm: hệ thống Đăng nhập/Đăng ký tài khoản, Đăng ký thông báo qua Email/Telegram, và Widget kiểm tra trạng thái thiết bị ngoại vi. Việc này giúp giảm tải hơn 40% lượng truy vấn API không cần thiết, tối giản hóa giao diện và tăng tốc độ kết xuất dữ liệu của trình duyệt máy khách.

---

## 🏗️ 3. Kiến Trúc Mã Nguồn Hiện Tại

Hệ thống được tổ chức theo cấu trúc dạng mô-đun hóa độc lập:

```text
Project-Predictt-Huricane/
├── backend/                   # FastAPI Backend Application
│   ├── app/
│   │   ├── models/            # Định nghĩa cơ sở dữ liệu SQLAlchemy
│   │   ├── services/          # Xử lý Logic thời tiết và gọi mô hình AI
│   │   ├── database.py        # Cấu hình SQLite Connection
│   │   └── main.py            # Khởi tạo API Router & Background Worker 3h/lần
│   └── requirements.txt       # Danh sách thư viện Python
├── frontend/                  # Next.js Frontend Application (Turbopack)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx       # Giao diện chính Dashboard GIS và Recharts
│   │   │   └── layout.tsx
│   └── package.json           # Danh sách thư viện Node.js và Scripts
├── models/                    # Thư mục lưu trữ 3 mô hình XGBoost dạng JSON
│   ├── xgboost_wind_model.json# Mô hình dự báo tốc độ gió
│   ├── xgboost_rain_model.json# Mô hình dự báo lượng mưa
│   └── xgboost_pres_model.json# Mô hình dự báo khí áp mặt biển
├── data/                      # Lưu trữ tệp dữ liệu thời tiết lịch sử (.csv)
└── weather.db                 # Cơ sở dữ liệu SQLite tự động sinh
```

---

## 🚀 4. Hướng Dẫn Cài Đặt Chi Tiết Từ Đầu Đến Cuối

### Bước 4.1: Cấu hình RAM ảo (Swap File) trên Raspberry Pi
Chạy các lệnh sau trên Pi để tạo thêm 2GB bộ nhớ đệm:
```bash
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Bước 4.2: Cài đặt và cấu hình FastAPI Backend
1.  Di chuyển vào thư mục dự án và tạo môi trường ảo Python:
    ```bash
    cd /home/lirrak/Project-Predictt-Huricane
    python3 -m venv venv
    source venv/bin/activate
    ```
2.  Chuyển hướng thư mục tạm của `pip` về thẻ nhớ chính:
    ```bash
    mkdir -p ~/pip_tmp
    export TMPDIR=~/pip_tmp
    ```
3.  Cài đặt các thư viện phụ thuộc (Không lưu cache để tiết kiệm RAM):
    ```bash
    pip install --no-cache-dir -r requirements.txt
    ```

### Bước 4.3: Cài đặt Node.js và biên dịch Frontend
1.  Cài đặt NVM (Node Version Manager) và Node.js v20:
    ```bash
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    source ~/.bashrc
    nvm install 20
    nvm use 20
    ```
2.  Di chuyển vào thư mục frontend và cài đặt thư viện:
    ```bash
    cd /home/lirrak/Project-Predictt-Huricane/frontend
    npm install
    ```
3.  Biên dịch ứng dụng với giới hạn RAM của trình biên dịch Node là 512MB:
    ```bash
    NODE_OPTIONS="--max-old-space-size=512" npm run build
    ```

---

## ⚙️ 5. Vận Hành Dự Án Chạy Ngầm Bằng Systemd

Để hệ thống hoạt động tự động khi cắm điện cho Raspberry Pi, ta đăng ký 2 dịch vụ chạy ngầm độc lập:

### 1. Tạo tệp dịch vụ Backend:
```bash
sudo nano /etc/systemd/system/hurricane-backend.service
```
Dán nội dung sau vào và lưu lại:
```ini
[Unit]
Description=Hurricane Predictor FastAPI Backend
After=network.target

[Service]
Type=simple
User=lirrak
WorkingDirectory=/home/lirrak/Project-Predictt-Huricane
ExecStart=/home/lirrak/Project-Predictt-Huricane/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Environment=PYTHONPATH=backend
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Tạo tệp dịch vụ Frontend:
```bash
sudo nano /etc/systemd/system/hurricane-frontend.service
```
Dán nội dung sau vào và lưu lại *(Kiểm tra kĩ đường dẫn node qua lệnh `which node`)*:
```ini
[Unit]
Description=Hurricane Predictor Next.js Frontend
After=network.target

[Service]
Type=simple
User=lirrak
WorkingDirectory=/home/lirrak/Project-Predictt-Huricane/frontend
Environment=PATH=/home/lirrak/.nvm/versions/node/v20.20.2/bin:/usr/bin:/usr/local/bin
ExecStart=/home/lirrak/.nvm/versions/node/v20.20.2/bin/npm run start -- --port 3000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Kích hoạt dịch vụ:
```bash
sudo systemctl daemon-reload
sudo systemctl enable hurricane-backend.service hurricane-frontend.service
sudo systemctl start hurricane-backend.service hurricane-frontend.service
```

---

## 📈 6. Hướng Phát Triển Tương Lai (Future Development)

Để hệ thống ngày càng hoàn thiện và mang tính thực tế cao hơn trong nghiên cứu khí quyển học, các định hướng phát triển sau được đề xuất:

1.  **Nâng cấp mô hình Học máy (Machine Learning Optimization):**
    *   Nghiên cứu áp dụng các kiến trúc mạng nơ-ron học sâu chuỗi thời gian như **LSTM**, **GRU** hoặc các mạng đồ thị nơ-ron chuyên biệt (**Graph Neural Networks - GNN**) để nắm bắt chính xác hơn mối quan hệ không gian - thời gian giữa 37 trạm khí quyển.
    *   Thực hiện tối ưu hóa siêu tham số (Hyperparameter Tuning) định kỳ và lưu vết bằng MLflow.
2.  **Tích hợp Thiết bị IoT Thực địa (Edge IoT Integration):**
    *   Phát triển các node cảm biến khí quyển vật lý (sử dụng vi điều khiển ESP32 kết hợp cảm biến sức gió Anemometer, khí áp kế BMP280 và cảm biến mưa) đặt tại các vùng địa hình ven biển thực tế.
    *   Các node này sẽ định kỳ gửi dữ liệu đo đạc thực địa trực tiếp về cổng API máy chủ thông qua giao thức siêu nhẹ **MQTT** hoặc **HTTP POST**, làm giàu thêm dữ liệu huấn luyện cho mô hình.
3.  **Tích hợp bản đồ ngoại tuyến (Offline GIS Map):**
    *   Để chuẩn bị cho kịch bản mất kết nối mạng Internet hoàn toàn trong thiên tai cực đoan, hệ thống cần tích hợp các gói bản đồ vector ngoại tuyến thông qua công nghệ Mapbox Offline hoặc Leaflet lưu trữ ngay trên thẻ nhớ của Pi.
4.  **Thiết lập Reverse Proxy và Bảo mật SSL:**
    *   Cấu hình thêm **Nginx Reverse Proxy** và mã hóa SSL Let's Encrypt ở cổng 80/443 để cho phép truy cập hệ thống từ internet công cộng một cách an toàn nhất nếu có nhu cầu chia sẻ dữ liệu với cộng đồng.
