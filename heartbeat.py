import os
import time
import requests

HEARTBEAT_TOPIC = "lirrak_project_hurricane_heartbeat_6fd7a"
url = f"https://ntfy.sh/{HEARTBEAT_TOPIC}"

# Chạy vô hạn để gửi tín hiệu lên mây cứ mỗi 15 giây
while True:
    try:
        response = requests.post(url, data="ping", timeout=5)
    except Exception:
        pass
    time.sleep(15)
