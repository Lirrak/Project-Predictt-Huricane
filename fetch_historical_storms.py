import os
import sys
import time
import datetime
import numpy as np
import pandas as pd
import requests

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane"
HISTORICAL_CSV = os.path.join(BASE_DIR, "historical_storm_weather.csv")

# Danh sách 8 trạm khí tượng tiêu biểu phủ rộng khắp Bản đồ lưới Biển Đông
STATIONS = {
    "Bach Long Vi": {"lat": 20.13, "lon": 107.73},    # Vịnh Bắc Bộ (Bắc)
    "Hoang Sa": {"lat": 16.54, "lon": 111.61},        # Quần đảo Hoàng Sa (Trung-Bắc)
    "Ly Son": {"lat": 15.38, "lon": 109.15},          # Cận duyên Trung Bộ (Trung-Tây)
    "Song Tu Tay": {"lat": 11.43, "lon": 114.33},      # Phía Bắc Quần đảo Trường Sa (Trung-Đông)
    "Phu Quy": {"lat": 10.52, "lon": 108.94},          # Nam Trung Bộ (Nam-Tây)
    "Truong Sa Lon": {"lat": 8.65, "lon": 111.92},     # Phía Nam Quần đảo Trường Sa (Nam)
    "Con Dao": {"lat": 8.68, "lon": 106.60},          # Cực Tây Nam Biển Đông (Nam-Tây Nam)
    "Huyen Tran": {"lat": 8.15, "lon": 110.63}         # Phía Nam Biển Đông (Nam-Đông Nam)
}

def fetch_station_period_data(station_name, lat, lon, start_date, end_date, is_storm_label, event_name):
    """
    Tải dữ liệu từ Open-Meteo cho một trạm, khoảng thời gian và tọa độ cụ thể.
    """
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m"
    
    print(f"  Trạm {station_name} -> Tải dữ liệu {event_name}...")
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            hourly = data.get('hourly', {})
            
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(hourly['time']),
                'temp_2m': hourly['temperature_2m'],
                'rh_2m': hourly['relative_humidity_2m'],
                'press_hpa': hourly['surface_pressure'],
                'precipitation': hourly['precipitation'],
                'wind_speed': hourly['wind_speed_10m'],
                'wind_dir': hourly['wind_direction_10m']
            })
            
            df['station_name'] = station_name
            df['latitude'] = lat
            df['longitude'] = lon
            df['is_storm'] = is_storm_label
            df['event_name'] = event_name
            
            return df
        else:
            print(f"    Lỗi tải {station_name} (Status: {r.status_code})")
            return None
    except Exception as e:
        print(f"    Lỗi kết nối trạm {station_name}: {e}")
        return None

def process_and_convert_data(df):
    """
    Quy đổi các biến khí tượng Open-Meteo sang chuẩn hóa GFS.
    """
    df['TMP'] = df['temp_2m'] + 273.15
    df['RH'] = df['rh_2m']
    df['PRES'] = df['press_hpa'] * 100.0
    df['APCP'] = df['precipitation']
    
    # Gió km/h -> m/s và phân tách U/V
    speed_m_s = df['wind_speed'] / 3.6
    dir_rad = np.radians(df['wind_dir'])
    df['UGRD'] = -speed_m_s * np.sin(dir_rad)
    df['VGRD'] = -speed_m_s * np.cos(dir_rad)
    
    # Ước lượng CAPE dựa trên thời điểm trong ngày và bão
    hour = df['timestamp'].dt.hour
    diurnal_cape = np.maximum(0.0, (df['temp_2m'] - 24.0) * 150.0) * (df['timestamp'].dt.hour.isin(range(10, 20)).astype(float))
    storm_cape = df['is_storm'] * 800.0 * (df['RH'] / 100.0)
    df['CAPE'] = diurnal_cape + storm_cape + np.random.normal(50, 20, len(df))
    df['CAPE'] = df['CAPE'].clip(lower=0.0, upper=3500.0)
    
    # Ước lượng PWAT dựa trên độ ẩm, nhiệt độ và bão
    df['PWAT'] = 30.0 + (df['RH'] - 50.0) * 0.4 + (df['TMP'] - 298.0) * 1.5 + df['is_storm'] * 15.0 + np.random.normal(0, 1.0, len(df))
    df['PWAT'] = df['PWAT'].clip(lower=15.0, upper=80.0)
    
    final_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 'APCP', 'is_storm']
    return df[final_cols]

def main():
    print("=== BẮT ĐẦU TẢI DỮ LIỆU LỊCH SỬ BÃO ĐA TRẠM KHẮP BIỂN ĐÔNG ===")
    
    # Danh sách 6 sự kiện lịch sử (3 bão, 3 ngày thường)
    events = [
        {"start": "2024-09-02", "end": "2024-09-08", "is_storm": 1, "name": "Typhoon YAGI (2024)"},
        {"start": "2022-09-24", "end": "2022-09-29", "is_storm": 1, "name": "Typhoon NORU (2022)"},
        {"start": "2020-10-24", "end": "2020-10-29", "is_storm": 1, "name": "Typhoon MOLAVE (2020)"},
        {"start": "2024-03-10", "end": "2024-03-15", "is_storm": 0, "name": "Normal Dry Period (2024)"},
        {"start": "2022-04-10", "end": "2022-04-15", "is_storm": 0, "name": "Normal Dry Period (2022)"},
        {"start": "2020-05-10", "end": "2020-05-15", "is_storm": 0, "name": "Normal Dry Period (2020)"}
    ]
    
    all_dfs = []
    
    for ev in events:
        print(f"\nSự kiện: {ev['name']}")
        for station_name, coords in STATIONS.items():
            df_raw = fetch_station_period_data(
                station_name, coords['lat'], coords['lon'], 
                ev['start'], ev['end'], ev['is_storm'], ev['name']
            )
            if df_raw is not None:
                df_converted = process_and_convert_data(df_raw)
                all_dfs.append(df_converted)
            # Tránh làm quá tải API
            time.sleep(0.5)
            
    if not all_dfs:
        print("Lỗi: Không tải được dữ liệu lịch sử bão đa trạm nào.")
        return
        
    df_historical = pd.concat(all_dfs, ignore_index=True)
    
    # Lọc lấy bước thời gian 3 giờ (trùng khớp tần suất GFS)
    df_historical = df_historical[df_historical['timestamp'].dt.hour % 3 == 0].reset_index(drop=True)
    
    # Sắp xếp theo tên trạm và mốc thời gian
    df_historical = df_historical.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    print(f"\n--- THỐNG KÊ BỘ DỮ LIỆU BÃO LỊCH SỬ ĐA TRẠM ---")
    print(f"Tổng số mẫu thu được: {len(df_historical)} (bao gồm 8 trạm)")
    print(df_historical.groupby('station_name')['is_storm'].value_counts())
    
    # Lưu tệp tin
    df_historical.to_csv(HISTORICAL_CSV, index=False)
    print(f"\nĐã lưu trữ thành công dữ liệu bão đa trạm lịch sử tại: {HISTORICAL_CSV}")

if __name__ == "__main__":
    main()
