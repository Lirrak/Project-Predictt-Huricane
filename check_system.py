#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import sqlite3
import subprocess
import urllib.request
from datetime import datetime

# Định nghĩa bảng màu sắc hiển thị trên Terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

def print_section(title):
    print(f"\n{BOLD}{BLUE}--- {title} ---{RESET}")

def check_service(service_name):
    """Kiểm tra dịch vụ Systemd có đang active hay không"""
    try:
        res = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=3
        )
        status = res.stdout.strip()
        if status == "active":
            print(f"  ✅ {service_name:<30} : {GREEN}{status.upper()}{RESET}")
            return True
        else:
            print(f"  ❌ {service_name:<30} : {RED}{status.upper() or 'INACTIVE'}{RESET}")
            return False
    except Exception:
        print(f"  ⚠️ {service_name:<30} : {YELLOW}KHÔNG THỂ TRUY VẤN (Có thể không chạy trên Linux/Pi){RESET}")
        return None

def check_url(url, label):
    """Kiểm tra phản hồi HTTP từ các cổng kết nối"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                print(f"  ✅ {label:<30} : {GREEN}KẾT NỐI TỐT (200 OK){RESET}")
                return True
            else:
                print(f"  ❌ {label:<30} : {RED}LỖI HTTP ({response.status}){RESET} -> {url}")
                return False
    except Exception as e:
        print(f"  ❌ {label:<30} : {RED}KHÔNG THỂ KẾT NỐI ({type(e).__name__}){RESET} -> {url}")
        return False

def check_database():
    """Kiểm tra tính toàn vẹn và mức độ cập nhật của Cơ sở dữ liệu SQLite"""
    # Tìm kiếm cơ sở dữ liệu thông minh qua nhiều đường dẫn dự phòng
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "weather.db"),
        os.path.join(script_dir, "Project-Predictt-Huricane", "weather.db"),
        "/home/lirrak/Project-Predictt-Huricane/weather.db",
        "weather.db"
    ]
    
    db_path = None
    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                # Kiểm tra tính hợp lệ bằng cách truy vấn thử danh sách trạm
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM stations;")
                conn.close()
                db_path = path
                break
            except Exception:
                continue
                
    if not db_path:
        tried_paths = ", ".join([f"'{p}'" for p in candidates])
        print(f"  ❌ Cơ sở dữ liệu SQLite         : {RED}KHÔNG TÌM THẤY weather.db (Đã thử: {tried_paths}){RESET}")
        return False
    
    print(f"  ✅ File Cơ sở dữ liệu           : {GREEN}ĐÃ TÌM THẤY TẠI '{db_path}'{RESET} ({os.path.getsize(db_path)/1024:.1f} KB)")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Đếm số lượng trạm đã khởi tạo
        cursor.execute("SELECT COUNT(*) FROM stations;")
        stations_count = cursor.fetchone()[0]
        
        # Đếm số lượng trạm đã có dự báo
        cursor.execute("SELECT COUNT(*) FROM station_forecasts;")
        forecasts_count = cursor.fetchone()[0]
        
        # Lấy mốc cập nhật gần nhất
        cursor.execute("SELECT MAX(updated_at) FROM station_forecasts;")
        last_update = cursor.fetchone()[0]
        
        conn.close()
        
        # Đánh giá số lượng trạm
        if stations_count == 37:
            print(f"  ✅ Khởi tạo danh sách trạm      : {GREEN}ĐẦY ĐỦ ({stations_count}/37 trạm){RESET}")
        else:
            print(f"  ⚠️ Khởi tạo danh sách trạm      : {YELLOW}THIẾU ({stations_count}/37 trạm){RESET}")

        if forecasts_count == 37:
            print(f"  ✅ Số lượng dự báo trạm hiện tại: {GREEN}HOÀN THÀNH ({forecasts_count}/37 trạm){RESET}")
        else:
            print(f"  ❌ Số lượng dự báo trạm hiện tại: {RED}THIẾU HỤT ({forecasts_count}/37 trạm){RESET}")
            
        if last_update:
            print(f"  ✅ Thời gian cập nhật gần nhất  : {CYAN}{last_update} UTC{RESET}")
            
            # Tính toán độ trễ thời gian thực
            try:
                dt_last = datetime.strptime(last_update.split(".")[0], "%Y-%m-%d %H:%M:%S")
                dt_now = datetime.utcnow()
                diff_hours = (dt_now - dt_last).total_seconds() / 3600
                if diff_hours < 3.5:
                    print(f"  🔥 Tiến trình cập nhật ngầm     : {GREEN}HOẠT ĐỘNG LIÊN TỤC (Trễ {diff_hours:.2f} giờ < 3.5 giờ){RESET}")
                else:
                    print(f"  ⚠️ Tiến trình cập nhật ngầm     : {YELLOW}CÓ THỂ ĐÃ BỊ ĐƠ (Trễ {diff_hours:.2f} giờ > 3.5 giờ){RESET}")
            except Exception:
                pass
        else:
            print(f"  ❌ Thời gian cập nhật gần nhất  : {RED}CHƯA CÓ DỮ LIỆU CẬP NHẬT{RESET}")
            
        return True
    except Exception as e:
        print(f"  ❌ Lỗi đọc Cơ sở dữ liệu SQLite : {RED}{e}{RESET}")
        return False

def get_cloudflare_url():
    """Lấy link truy cập công khai gần nhất từ nhật ký Cloudflare Quick Tunnel"""
    try:
        cmd = "sudo journalctl -u cloudflared-quick.service -n 50 --no-pager | grep -o 'https://[a-zA-Z0-9-]*\\.trycloudflare\\.com' | tail -n 1"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
        url = res.stdout.strip()
        if url:
            print(f"  🔗 Link Cloudflare Quick Tunnel : {BOLD}{CYAN}{url}{RESET}")
            return url
        else:
            print(f"  ⚠️ Link Cloudflare Quick Tunnel : {YELLOW}Không tìm thấy link trong nhật ký log.{RESET}")
            return None
    except Exception:
        return None

def main():
    print(f"\n{BOLD}{CYAN}========================================================{RESET}")
    print(f"{BOLD}{CYAN}🛰️  CHƯƠNG TRÌNH CHẨN ĐOÁN & KIỂM TRA TOÀN DIỆN RASPBERRY PI{RESET}")
    print(f"{BOLD}{CYAN}========================================================{RESET}")
    print(f"Thời gian chẩn đoán: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Giờ địa phương)")
    
    # 1. Kiểm tra dịch vụ hệ thống
    print_section("1. KIỂM TRA TRẠNG THÁI CÁC DỊCH VỤ CHẠY NGẦM")
    services = [
        "hurricane-backend.service",
        "hurricane-frontend.service",
        "hurricane-mlops.service",
        "nginx.service",
        "cloudflared-quick.service"
    ]
    all_services_ok = True
    for s in services:
        status = check_service(s)
        if not status:
            all_services_ok = False
            
    # 2. Kiểm tra đường truyền nội bộ (Local Endpoints)
    print_section("2. KIỂM TRA CỔNG KẾT NỐI NỘI BỘ (LOCAL PORTS)")
    ports_ok = True
    ports_ok &= check_url("http://localhost:8000/", "FastAPI Backend (Port 8000)")
    ports_ok &= check_url("http://localhost:3000/", "Next.js Frontend (Port 3000)")
    ports_ok &= check_url("http://localhost:8080/", "Nginx Reverse Proxy (Port 8080)")
    
    # 3. Kiểm tra cơ sở dữ liệu
    print_section("3. KIỂM TRA TOÀN VẸN CƠ SỞ DỮ LIỆU SQLITE")
    db_ok = check_database()
    
    # 4. Kiểm tra liên kết từ xa
    print_section("4. KIỂM TRA ĐƯỜNG TRUYỀN RA NGOÀI INTERNET")
    cf_url = get_cloudflare_url()
    tunnel_ok = False
    if cf_url:
        tunnel_ok = check_url(cf_url, "Kiểm tra Link Cloudflare")
        
    # Kết luận tổng quan
    print(f"\n{BOLD}{CYAN}========================================================{RESET}")
    if all_services_ok and ports_ok and db_ok and tunnel_ok:
        print(f"🏆 {GREEN}{BOLD}KẾT LUẬN: HỆ THỐNG ĐANG HOẠT ĐỘNG HOÀN HẢO 100%!{RESET}")
    elif all_services_ok and ports_ok and db_ok:
        print(f"⚠️ {YELLOW}{BOLD}KẾT LUẬN: NỘI BỘ TỐT NHƯNG LINK NGOÀI ĐANG GẶP SỰ CỐ!{RESET}")
    else:
        print(f"🚨 {RED}{BOLD}KẾT LUẬN: PHÁT HIỆN LỖI! VUI LÒNG KIỂM TRA CÁC DÒNG (❌) TRÊN!{RESET}")
    print(f"{BOLD}{CYAN}========================================================{RESET}\n")

if __name__ == "__main__":
    main()
