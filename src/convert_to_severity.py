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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED_CSV = os.path.join(BASE_DIR, "data", "extracted_weather.csv")
HISTORICAL_CSV = os.path.join(BASE_DIR, "data", "historical_storm_weather.csv")

def calculate_storm_severity(row):
    """
    Phân loại cấp độ bão nhiệt đới dựa trên tốc độ gió (m/s) theo quy chuẩn Việt Nam/Biển Đông:
    Cấp 0: Bình thường / Vùng áp thấp yếu - Gió dưới cấp 6 (< 10.8 m/s).
    Cấp 1: Áp thấp nhiệt đới - Gió cấp 6-7 (10.8 - 17.1 m/s).
    Cấp 2: Bão / Tropical storm - Gió cấp 8-9 (17.2 - 24.4 m/s).
    Cấp 3: Bão mạnh - Gió cấp 10-11 (24.5 - 32.6 m/s).
    Cấp 4: Bão rất mạnh - Gió cấp 12-15 (32.7 - 50.9 m/s).
    Cấp 5: Siêu bão - Gió cấp 16 trở lên (>= 51.0 m/s).
    """
    u = row['UGRD']
    v = row['VGRD']
    is_storm_period = row.get('is_storm', 0)
    
    # Tính tốc độ gió (m/s)
    wind_speed = np.sqrt(u**2 + v**2)
    
    # Phân cấp
    if wind_speed >= 51.0:
        return 5  # Siêu bão
    elif 32.7 <= wind_speed < 51.0:
        return 4  # Bão rất mạnh
    elif 24.5 <= wind_speed < 32.7:
        return 3  # Bão mạnh
    elif 17.2 <= wind_speed < 24.5:
        return 2  # Bão thường / Tropical storm
    elif 10.8 <= wind_speed < 17.2:
        return 1  # Áp thấp nhiệt đới
    else:
        # Nếu trong thời kỳ bão nhưng ở vùng rìa gió nhẹ
        return 1 if is_storm_period == 1 else 0

def main():
    print("=== NÂNG CẤP BỘ DỮ LIỆU SANG THANG PHÂN LOẠI CẤP ĐỘ BÃO MULTI-LEVEL ===")
    
    # 1. Nâng cấp dữ liệu bão lịch sử
    if os.path.exists(HISTORICAL_CSV):
        print(f"Đang đọc dữ liệu lịch sử bão từ {HISTORICAL_CSV}...")
        df_hist = pd.read_csv(HISTORICAL_CSV)
        
        # Áp dụng hàm phân loại cấp độ bão
        df_hist['storm_severity'] = df_hist.apply(calculate_storm_severity, axis=1)
        
        print("\nThống kê số lượng mẫu theo cấp độ bão trong tập lịch sử:")
        severity_names = {
            0: "Cấp 0: Bình thường (Normal)",
            1: "Cấp 1: Áp thấp nhiệt đới (Tropical Depression)",
            2: "Cấp 2: Bão thường (Tropical Storm)",
            3: "Cấp 3: Bão mạnh (Strong Storm)",
            4: "Cấp 4: Bão rất mạnh (Very Strong Storm)",
            5: "Cấp 5: Siêu bão (Super Typhoon)"
        }
        for level, count in df_hist['storm_severity'].value_counts().sort_index().items():
            print(f"  - {severity_names[level]:<50}: {count} mẫu")
            
        # Lưu đè lại tệp lịch sử đã nâng cấp
        df_hist.to_csv(HISTORICAL_CSV, index=False)
        print("Đã cập nhật thành công tệp bão lịch sử đa trạm!")
        
    # 2. Nâng cấp dữ liệu thực tế GFS hiện tại
    if os.path.exists(EXTRACTED_CSV):
        print(f"\nĐang đọc dữ liệu thực tế hiện tại từ {EXTRACTED_CSV}...")
        df_real = pd.read_csv(EXTRACTED_CSV)
        
        # Áp dụng phân loại cấp độ bão
        df_real['storm_severity'] = df_real.apply(calculate_storm_severity, axis=1)
        
        print("Thống kê số lượng mẫu theo cấp độ bão trong tập thực tế:")
        for level, count in df_real['storm_severity'].value_counts().sort_index().items():
            print(f"  - {severity_names[level]:<50}: {count} mẫu")
            
        # Lưu đè lại tệp thực tế đã nâng cấp
        df_real.to_csv(EXTRACTED_CSV, index=False)
        print("Đã cập nhật thành công tệp thời tiết đa trạm thực tế!")

if __name__ == "__main__":
    main()
