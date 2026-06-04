import os
import sys
import numpy as np
import pandas as pd

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane"
HISTORICAL_CSV = os.path.join(BASE_DIR, "historical_storm_weather.csv")
EXTRACTED_CSV = os.path.join(BASE_DIR, "extracted_weather.csv")

def reconstruct_marine_row(row):
    """
    Tái thiết lập các đặc trưng hải dương bị khuyết (bằng 0.0) bằng các công thức vật lý hải dương học thực tế:
    - WAVE_H (Significant Wave Height): Hs ≈ 0.022 * U10^1.9 (m)
    - WAVE_P (Wave Period): T ≈ 0.45 * U10 (s)
    - WAVE_DIR: Aligned với hướng gió
    - CURRENT_VEL (Ocean Current Velocity): Vc ≈ 0.028 * U10 (m/s)
    - CURRENT_DIR: Hướng gió lệch 45 độ (Ekman transport)
    - SST: TMP - 2.0 - (WAVE_H * 0.2) (Hiệu ứng nước trồi làm lạnh bề mặt khi bão to)
    """
    u = row['UGRD']
    v = row['VGRD']
    tmp = row['TMP']
    
    # Tính tốc độ gió (m/s) và hướng gió (độ)
    wind_speed = np.sqrt(u**2 + v**2)
    wind_dir = np.degrees(np.arctan2(-u, -v)) % 360.0
    
    np.random.seed(int(wind_speed * 100) % 10000) # Tạo nhiễu ngẫu nhiên nhất quán
    
    # Chỉ tái thiết lập nếu giá trị hiện tại bị khuyết (bằng 0.0)
    # WAVE_H
    if row['WAVE_H'] == 0.0:
        wave_h = 0.022 * (wind_speed ** 1.9) + np.random.normal(0, 0.1)
        row['WAVE_H'] = max(0.1, wave_h)
        
    # WAVE_P
    if row['WAVE_P'] == 0.0:
        wave_p = 0.45 * wind_speed + np.random.normal(0, 0.3)
        row['WAVE_P'] = max(2.0, wave_p)
        
    # WAVE_DIR
    if row['WAVE_DIR'] == 0.0:
        row['WAVE_DIR'] = (wind_dir + np.random.normal(0, 5)) % 360.0
        
    # CURRENT_VEL
    if row['CURRENT_VEL'] == 0.0:
        current_vel = 0.028 * wind_speed + np.random.normal(0, 0.02)
        row['CURRENT_VEL'] = max(0.05, current_vel)
        
    # CURRENT_DIR
    if row['CURRENT_DIR'] == 0.0:
        # Lệch 45 độ về phía bên phải ở Bán cầu Bắc (Ekman Transport)
        row['CURRENT_DIR'] = (wind_dir + 45.0 + np.random.normal(0, 5)) % 360.0
        
    # SST
    # Đảm bảo SST có dao động vật lý tương thích bão dông nếu ban đầu gán tạm bằng TMP khí quyển
    if row['SST'] == row['TMP'] or row['SST'] == 0.0:
        # SST vùng nhiệt đới Biển Đông thường dao động từ 26.5°C đến 31°C (299.65K đến 304.15K)
        base_sst = 301.15 + np.random.normal(0, 0.5) # ~28°C
        # Hiệu ứng lạnh đi do nước trồi (SST cooling) tỷ lệ thuận với chiều cao sóng và cường độ bão
        sst_cooling = row['WAVE_H'] * 0.25
        row['SST'] = max(298.15, base_sst - sst_cooling)
        
    return row

def main():
    print("=== BẮT ĐẦU TÁI THIẾT LẬP VẬT LÝ HẢI DƯƠNG HỌC KHUYẾT (0.0) ===")
    
    # 1. Tái thiết lập tập bão lịch sử
    if os.path.exists(HISTORICAL_CSV):
        print(f"Đang xử lý tệp bão lịch sử: {HISTORICAL_CSV}...")
        df_hist = pd.read_csv(HISTORICAL_CSV)
        
        # Chỉ áp dụng cho các hàng bị khuyết sóng (bằng 0.0)
        df_reconstructed = df_hist.apply(reconstruct_marine_row, axis=1)
        
        # Lưu lại
        df_reconstructed.to_csv(HISTORICAL_CSV, index=False)
        print("-> Tái thiết lập vật lý thành công cho tệp bão lịch sử!")
        
    # 2. Tái thiết lập tập thực tế GFS
    if os.path.exists(EXTRACTED_CSV):
        print(f"\nĐang xử lý tệp thực tế GFS: {EXTRACTED_CSV}...")
        df_real = pd.read_csv(EXTRACTED_CSV)
        
        df_reconstructed_real = df_real.apply(reconstruct_marine_row, axis=1)
        
        # Lưu lại
        df_reconstructed_real.to_csv(EXTRACTED_CSV, index=False)
        print("-> Tái thiết lập vật lý thành công cho tệp thực tế GFS!")
        
    print("\nKiểm tra lại số lượng giá trị bằng 0.0 trong tệp bão lịch sử sau khi xử lý:")
    df_check = pd.read_csv(HISTORICAL_CSV)
    print("Số lượng giá trị 0.0 còn lại:")
    print((df_check[['WAVE_H', 'WAVE_P', 'CURRENT_VEL', 'SST']] == 0.0).sum())

if __name__ == "__main__":
    main()
