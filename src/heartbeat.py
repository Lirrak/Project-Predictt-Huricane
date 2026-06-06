import os
import time
import sys
import requests

# Ensure UTF-8 output encoding for Vietnamese characters on terminal
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Configure the target URL
# The Raspberry Pi will read the BACKEND_URL environment variable.
# For Cloud deployment, set BACKEND_URL to 'http://<YOUR-CLOUD-VPS-IP>:8000'
BACKEND_HOST = os.environ.get("BACKEND_URL", "http://localhost:8000")
url = f"{BACKEND_HOST.rstrip('/')}/api/iot/heartbeat"

print("==========================================================")
print("🛰️ RASPBERRY PI IOT HEARTBEAT DAEMON")
print(f"Target Server URL: {url}")
print("Status: RUNNING (Sending 'ping' heartbeat every 15 seconds)")
print("==========================================================")

# Infinite loop sending active signals to backend
while True:
    start_time = time.time()
    try:
        response = requests.post(url, data="ping", timeout=5)
        if response.status_code == 200:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Heartbeat SENT successfully! (Response: {response.json()})")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Server responded with code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Connection failed: Unable to reach target backend server.")
        
    time.sleep(15)
