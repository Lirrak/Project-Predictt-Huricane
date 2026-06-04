#!/bin/bash

# Kiểm tra quyền root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Vui lòng chạy script này bằng quyền sudo: sudo bash setup_systemd.sh"
  exit 1
fi

# TỰ ĐỘNG PHÁT HIỆN: Thư mục hiện tại và tên User đang đăng nhập
PROJECT_DIR="$(pwd)"
USER_NAME="$(logname)"
SERVICE_NAME="streamlit-forecast"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "======================================================"
echo "⚙️  ĐANG CẤU HÌNH DỊCH VỤ CHẠY NGẦM ĐỘNG TRÊN RASPBERRY PI..."
echo "======================================================"
echo "📁 Thư mục phát hiện: ${PROJECT_DIR}"
echo "👤 Người dùng phát hiện: ${USER_NAME}"

# Cấp quyền thực thi cho file chạy chính
chmod +x "${PROJECT_DIR}/run_app.sh"

# Đường dẫn ExecStart trỏ tới bash script chạy chính
EXEC_PATH="/bin/bash ${PROJECT_DIR}/run_app.sh"

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
echo "🎉 HOÀN THÀNH THIẾT LẬP DỊCH VỤ CHẠY NGẦM ĐỘNG CHUẨN XÁC!"
echo "======================================================"
echo "👉 Ứng dụng Streamlit đang CHẠY NGẦM trong hệ thống."
echo "👉 Dịch vụ tự động gửi nhịp đập ONLINE liên tục lên Cloud."
echo "👉 Ứng dụng sẽ TỰ ĐỘNG BẬT mỗi khi Raspberry Pi khởi động lại."
echo ""
echo "💡 Một số câu lệnh hữu ích để quản lý dịch vụ:"
echo "   - Xem trạng thái hoạt động:  sudo systemctl status ${SERVICE_NAME}"
echo "   - Tạm dừng dịch vụ:          sudo systemctl stop ${SERVICE_NAME}"
echo "   - Bật lại dịch vụ:           sudo systemctl start ${SERVICE_NAME}"
echo "   - Xem nhật ký hoạt động:     sudo journalctl -u ${SERVICE_NAME} -f"
echo "======================================================"
