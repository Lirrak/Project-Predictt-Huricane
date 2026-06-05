#!/bin/bash

# Lấy thư mục hiện tại của tệp script này
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Xác định trình biên dịch Python phù hợp (venv hoặc global)
if [ -f "./venv/bin/python3" ]; then
  PYTHON_BIN="./venv/bin/python3"
  echo "🟢 Khởi động ứng dụng bằng Môi trường ảo (venv)..."
else
  PYTHON_BIN="python3"
  echo "🟢 Khởi động ứng dụng bằng Python hệ thống..."
fi

# 1. Chạy tiến trình gửi tín hiệu ONLINE ở chế độ nền
$PYTHON_BIN src/heartbeat.py &
HEARTBEAT_PID=$!

# 2. Chạy máy chủ giao diện Streamlit chính
$PYTHON_BIN -m streamlit run app.py

# 3. Khi Streamlit bị dừng, tự động tắt tiến trình heartbeat đi kèm
kill $HEARTBEAT_PID
