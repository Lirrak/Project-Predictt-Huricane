#!/bin/bash

# Kiểm tra quyền root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Vui lòng chạy script này bằng quyền sudo: sudo bash setup_mlops_service.sh"
  exit 1
fi

# TỰ ĐỘNG PHÁT HIỆN: Thư mục hiện tại và tên User đang đăng nhập
PROJECT_DIR="$(pwd)"
USER_NAME="$(logname)"
SERVICE_NAME="hurricane-mlops"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "======================================================"
echo "⚙️  ĐANG CẤU HÌNH DỊCH VỤ MLOPS CHẠY NGẦM ĐỘNG TRÊN PI..."
echo "======================================================"
echo "📁 Thư mục phát hiện: ${PROJECT_DIR}"
echo "👤 Người dùng phát hiện: ${USER_NAME}"

# Cấu hình python trong môi trường ảo
PYTHON_PATH="${PROJECT_DIR}/venv/bin/python"
if [ ! -f "$PYTHON_PATH" ]; then
    # Thử tìm venv ở thư mục hiện tại
    PYTHON_PATH="$(which python3)"
fi

echo "🐍 Đường dẫn Python sử dụng: ${PYTHON_PATH}"

# 2. Tạo file cấu hình dịch vụ Systemd
echo "📝 Đang tạo tệp dịch vụ tại ${SERVICE_FILE}..."

cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=Hurricane Predictor MLOps Daily Training Service
After=network.target hurricane-backend.service
Requires=hurricane-backend.service

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PYTHON_PATH} src/realtime_mlops.py
Restart=always
RestartSec=15
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=hurricane-mlops

# Giới hạn tài nguyên cứng chuẩn xác (Nice & IO Scheduling)
Nice=19
IOSchedulingClass=idle

[Install]
WantedBy=multi-user.target
EOF

# 3. Nạp lại systemd, kích hoạt dịch vụ chạy cùng hệ thống và khởi động dịch vụ
echo "🔄 Đang tải cấu hình và kích hoạt chạy ngầm..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service
systemctl restart ${SERVICE_NAME}.service

echo ""
echo "======================================================"
echo "🎉 HOÀN THÀNH THIẾT LẬP DỊCH VỤ MLOPS CHẠY NGẦM!"
echo "======================================================"
echo "👉 Dịch vụ MLOps đang CHẠY NGẦM và tự động hóa 100%."
echo "👉 Tiến trình sẽ quét tải dữ liệu GFS 6 tiếng/lần và tự động train lúc 3:00 AM."
echo "👉 Được gán độ ưu tiên CPU & I/O thấp nhất (Nice=19, Idle I/O) nên cực kỳ an toàn cho Pi 3 B+."
echo ""
echo "💡 Một số câu lệnh hữu ích để quản lý dịch vụ:"
echo "   - Xem trạng thái hoạt động:  sudo systemctl status ${SERVICE_NAME}"
echo "   - Tạm dừng dịch vụ:          sudo systemctl stop ${SERVICE_NAME}"
echo "   - Bật lại dịch vụ:           sudo systemctl start ${SERVICE_NAME}"
echo "   - Xem nhật ký hoạt động:     sudo journalctl -u ${SERVICE_NAME} -f"
echo "======================================================"
