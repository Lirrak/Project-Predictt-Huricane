#!/bin/bash

# Kiểm tra quyền root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Vui lòng chạy script này bằng quyền sudo: sudo bash setup_systemd.sh"
  exit 1
fi

# Đường dẫn thư mục dự án trên Raspberry Pi
PROJECT_DIR="/home/lirrak/Project-Predictt-Hurricane"
USER_NAME="lirrak"
SERVICE_NAME="streamlit-forecast"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "======================================================"
echo "⚙️  ĐANG CẤU HÌNH DỊCH VỤ CHẠY NGẦM TRÊN RASPBERRY PI..."
echo "======================================================"

# 1. Xác định đường dẫn Python / Streamlit thực thi
if [ -f "${PROJECT_DIR}/venv/bin/streamlit" ]; then
  echo "🟢 Phát hiện Môi trường ảo (venv)."
  EXEC_PATH="${PROJECT_DIR}/venv/bin/python3 -m streamlit run app.py"
else
  echo "🟢 Phát hiện cài đặt Global."
  EXEC_PATH="/usr/bin/python3 -m streamlit run app.py"
fi

# 2. Tạo file cấu hình dịch vụ Systemd
echo "📝 Đang tạo tệp dịch vụ tại ${SERVICE_FILE}..."

cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=Streamlit Bien Dong Hurricane Predictor Service
After=network.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${EXEC_PATH}
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=streamlit-forecast

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
echo "🎉 HOÀN THÀNH THIẾT LẬP DỊCH VỤ CHẠY NGẦM!"
echo "======================================================"
echo "👉 Ứng dụng Streamlit đang CHẠY NGẦM trong hệ thống."
echo "👉 Ứng dụng sẽ TỰ ĐỘNG BẬT mỗi khi Raspberry Pi khởi động lại."
echo ""
echo "💡 Một số câu lệnh hữu ích để quản lý dịch vụ:"
echo "   - Xem trạng thái hoạt động:  sudo systemctl status ${SERVICE_NAME}"
echo "   - Tạm dừng dịch vụ:          sudo systemctl stop ${SERVICE_NAME}"
echo "   - Bật lại dịch vụ:           sudo systemctl start ${SERVICE_NAME}"
echo "   - Xem nhật ký hoạt động:     sudo journalctl -u ${SERVICE_NAME} -f"
echo "======================================================"
