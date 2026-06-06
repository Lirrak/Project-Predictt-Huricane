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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORICAL_CSV = os.path.join(BASE_DIR, "data", "historical_storm_weather.csv")

# Danh sách 37 trạm khí tượng bao gồm 32 trạm đất liền/ven biển quanh Biển Đông và 5 trạm phao ảo vùng biển sâu
STATIONS = {
    # 32 trạm đất liền/ven biển quanh Biển Đông
    "Bach Long Vi": {"lat": 20.13, "lon": 107.73},
    "Hoang Sa": {"lat": 16.54, "lon": 111.61},
    "Ly Son": {"lat": 15.38, "lon": 109.15},
    "Song Tu Tay": {"lat": 11.43, "lon": 114.33},
    "Phu Quy": {"lat": 10.52, "lon": 108.94},
    "Truong Sa Lon": {"lat": 8.65, "lon": 111.92},
    "Con Dao": {"lat": 8.68, "lon": 106.60},
    "Huyen Tran": {"lat": 8.15, "lon": 110.63},
    "Mong Cai": {"lat": 21.53, "lon": 107.97},
    "Hon Dau": {"lat": 20.67, "lon": 106.81},
    "Sam Son": {"lat": 19.73, "lon": 105.84},
    "Vinh": {"lat": 18.67, "lon": 105.68},
    "Con Co": {"lat": 17.16, "lon": 107.34},
    "Dong Hoi": {"lat": 17.47, "lon": 106.63},
    "Da Nang": {"lat": 16.07, "lon": 108.22},
    "Quy Nhon": {"lat": 13.77, "lon": 109.22},
    "Nha Trang": {"lat": 12.25, "lon": 109.19},
    "Vung Tau": {"lat": 10.35, "lon": 107.08},
    "Ca Mau": {"lat": 9.18, "lon": 105.15},
    "Phu Quoc": {"lat": 10.22, "lon": 103.96},
    "Sanya": {"lat": 18.25, "lon": 109.51},
    "Haikou": {"lat": 20.02, "lon": 110.35},
    "Guangzhou": {"lat": 23.13, "lon": 113.26},
    "Hong Kong": {"lat": 22.30, "lon": 114.17},
    "Kaohsiung": {"lat": 22.62, "lon": 120.30},
    "Dongsha": {"lat": 20.70, "lon": 116.73},
    "Laoag": {"lat": 18.19, "lon": 120.59},
    "Manila": {"lat": 14.60, "lon": 120.98},
    "Puerto Princesa": {"lat": 9.74, "lon": 118.74},
    "Kota Kinabalu": {"lat": 5.98, "lon": 116.07},
    "Natuna": {"lat": 4.00, "lon": 108.00},
    "Kuala Terengganu": {"lat": 5.33, "lon": 103.15},
    
    # 5 trạm phao ảo vùng biển sâu
    "Scarborough Shoal": {"lat": 15.11, "lon": 117.76},
    "Macclesfield": {"lat": 15.75, "lon": 114.30},
    "Reed Bank": {"lat": 11.30, "lon": 116.80},
    "Central Deep": {"lat": 14.00, "lon": 115.00},
    "Luzon Strait": {"lat": 20.00, "lon": 121.00}
}

def fetch_multi_location_weather(start_date, end_date):
    """Tải dữ liệu thời tiết thô cho tất cả 37 trạm cùng một lúc."""
    lats = ",".join([str(STATIONS[name]["lat"]) for name in STATIONS])
    lons = ",".join([str(STATIONS[name]["lon"]) for name in STATIONS])
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Lỗi tải weather API: {e}")
    return None

def fetch_multi_location_marine(start_date, end_date):
    """Tải dữ liệu sóng biển và hải lưu cho tất cả 37 trạm cùng một lúc."""
    lats = ",".join([str(STATIONS[name]["lat"]) for name in STATIONS])
    lons = ",".join([str(STATIONS[name]["lon"]) for name in STATIONS])
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Lỗi tải marine API: {e}")
    return None

def compute_storm_severity(wind_speed_ms, pres_pa, is_storm_period):
    """Phân loại cấp độ bão theo tốc độ gió (chuẩn Việt Nam/Biển Đông)."""
    if is_storm_period == 0 and wind_speed_ms < 10.8:
        return 0
    if wind_speed_ms >= 51.0:
        return 5  # Siêu bão
    elif 32.7 <= wind_speed_ms < 51.0:
        return 4  # Bão rất mạnh
    elif 24.5 <= wind_speed_ms < 32.7:
        return 3  # Bão mạnh
    elif 17.2 <= wind_speed_ms < 24.5:
        return 2  # Bão thường
    elif 10.8 <= wind_speed_ms < 17.2:
        return 1  # Áp thấp nhiệt đới
    else:
        return 1 if is_storm_period == 1 else 0

def process_station_data(station_name, coords, hourly_w, hourly_m, is_storm_label):
    """Đồng bộ hóa dữ liệu thời tiết & hải dương của một trạm."""
    df_weather = pd.DataFrame({
        'timestamp': pd.to_datetime(hourly_w['time']),
        'temp_2m': hourly_w['temperature_2m'],
        'rh_2m': hourly_w['relative_humidity_2m'],
        'press_hpa': hourly_w['surface_pressure'],
        'precipitation': hourly_w['precipitation'],
        'wind_speed': hourly_w['wind_speed_10m'],
        'wind_dir': hourly_w['wind_direction_10m']
    })
    
    df_marine = pd.DataFrame({
        'timestamp': pd.to_datetime(hourly_m['time']),
        'wave_height': hourly_m['wave_height'],
        'wave_direction': hourly_m['wave_direction'],
        'wave_period': hourly_m['wave_period'],
        'ocean_current_velocity': hourly_m['ocean_current_velocity'],
        'ocean_current_direction': hourly_m['ocean_current_direction'],
        'sea_surface_temperature': hourly_m['sea_surface_temperature']
    })
    
    # Đồng bộ hóa trên cột timestamp
    df = pd.merge(df_weather, df_marine, on='timestamp', how='inner')
    
    # Ép kiểu và điền khuyết
    for col in df.columns:
        if col != 'timestamp':
            df[col] = pd.to_numeric(df[col], errors='coerce').ffill().bfill().fillna(0.0)
            
    # Quy đổi vật lý giống GFS
    df['TMP'] = df['temp_2m'] + 273.15
    df['RH'] = df['rh_2m']
    df['PRES'] = df['press_hpa'] * 100.0
    df['APCP'] = df['precipitation']
    
    # Gió km/h -> m/s và phân tách U/V
    speed_ms = df['wind_speed'] / 3.6
    dir_rad = np.radians(df['wind_dir'])
    df['UGRD'] = -speed_ms * np.sin(dir_rad)
    df['VGRD'] = -speed_ms * np.cos(dir_rad)
    
    # Sóng và hải lưu
    df['WAVE_H'] = df['wave_height']
    df['WAVE_DIR'] = df['wave_direction']
    df['WAVE_P'] = df['wave_period']
    df['CURRENT_VEL'] = df['ocean_current_velocity']
    df['CURRENT_DIR'] = df['ocean_current_direction']
    df['SST'] = df['sea_surface_temperature'] + 273.15
    
    # Tính storm_severity dựa trên thực tế
    severities = []
    for _, row in df.iterrows():
        s = compute_storm_severity(row['wind_speed'] / 3.6, row['PRES'], is_storm_label)
        severities.append(s)
    df['storm_severity'] = severities
    
    # Tính CAPE và PWAT dựa trên mức độ bão
    hour_series = df['timestamp'].dt.hour
    diurnal_cape = np.maximum(0.0, (df['temp_2m'] - 24.0) * 150.0) * (hour_series.isin(range(10, 20)).astype(float))
    storm_cape = df['storm_severity'] * 200.0 * (df['RH'] / 100.0)
    df['CAPE'] = diurnal_cape + storm_cape
    
    df['PWAT'] = 30.0 + (df['RH'] - 50.0) * 0.4 + (df['TMP'] - 298.0) * 1.5 + (df['storm_severity'] * 4.0)
    df['PWAT'] = df['PWAT'].clip(lower=15.0, upper=80.0)
    
    # Thêm thông tin trạm
    df['station_name'] = station_name
    df['latitude'] = coords['lat']
    df['longitude'] = coords['lon']
    
    final_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 
                  'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity', 'APCP']
    return df[final_cols]

def main():
    print("=== BẮT ĐẦU TẢI DỮ LIỆU LỊCH SỬ SIÊU CƠ SỞ DỮ LIỆU BÃO BIỂN ĐÔNG (TỐI ƯU HÓA ĐA TỌA ĐỘ) ===")
    
    # Danh sách 15 cơn bão mạnh nhất lịch sử Biển Đông và 15 tuần ngày thường tương ứng (Tổng 30 sự kiện)
    events = [
        # --- 15 Cơn bão cực đoan ---
        {"start": "2024-09-02", "end": "2024-09-08", "is_storm": 1, "name": "Typhoon YAGI (2024)"},
        {"start": "2022-09-24", "end": "2022-09-29", "is_storm": 1, "name": "Typhoon NORU (2022)"},
        {"start": "2020-10-24", "end": "2020-10-29", "is_storm": 1, "name": "Typhoon MOLAVE (2020)"},
        {"start": "2021-12-15", "end": "2021-12-21", "is_storm": 1, "name": "Typhoon RAI (2021)"},
        {"start": "2018-09-14", "end": "2018-09-18", "is_storm": 1, "name": "Typhoon MANGKHUT (2018)"},
        {"start": "2014-07-15", "end": "2014-07-19", "is_storm": 1, "name": "Typhoon RAMMASUN (2014)"},
        {"start": "2020-11-11", "end": "2020-11-15", "is_storm": 1, "name": "Typhoon VAMCO (2020)"},
        {"start": "2017-11-01", "end": "2017-11-05", "is_storm": 1, "name": "Typhoon DAMREY (2017)"},
        {"start": "2017-12-21", "end": "2017-12-26", "is_storm": 1, "name": "Typhoon TEMBIN (2017)"},
        {"start": "2017-09-13", "end": "2017-09-16", "is_storm": 1, "name": "Typhoon DOKSURI (2017)"},
        {"start": "2023-07-15", "end": "2023-07-19", "is_storm": 1, "name": "Typhoon TALIM (2023)"},
        {"start": "2017-08-21", "end": "2017-08-25", "is_storm": 1, "name": "Typhoon HATO (2017)"},
        {"start": "2016-10-15", "end": "2016-10-19", "is_storm": 1, "name": "Typhoon SARIKA (2016)"},
        {"start": "2020-11-02", "end": "2020-11-06", "is_storm": 1, "name": "Typhoon GONI (2020)"},
        {"start": "2020-10-20", "end": "2020-10-25", "is_storm": 1, "name": "Typhoon SAUDEL (2020)"},
        
        # --- 15 Tuần ngày thường (đối chứng) ---
        {"start": "2024-03-10", "end": "2024-03-16", "is_storm": 0, "name": "Normal Week (2024)"},
        {"start": "2022-04-10", "end": "2022-04-15", "is_storm": 0, "name": "Normal Week (2022)"},
        {"start": "2020-05-10", "end": "2020-05-15", "is_storm": 0, "name": "Normal Week (2020)"},
        {"start": "2021-02-15", "end": "2021-02-21", "is_storm": 0, "name": "Normal Week (2021)"},
        {"start": "2018-01-14", "end": "2018-01-18", "is_storm": 0, "name": "Normal Week (2018)"},
        {"start": "2014-03-15", "end": "2014-03-19", "is_storm": 0, "name": "Normal Week (2014)"},
        {"start": "2020-03-11", "end": "2020-03-15", "is_storm": 0, "name": "Normal Week (2020b)"},
        {"start": "2017-02-01", "end": "2017-02-05", "is_storm": 0, "name": "Normal Week (2017)"},
        {"start": "2017-01-21", "end": "2017-01-26", "is_storm": 0, "name": "Normal Week (2017b)"},
        {"start": "2017-03-13", "end": "2017-03-16", "is_storm": 0, "name": "Normal Week (2017c)"},
        {"start": "2023-04-15", "end": "2023-04-19", "is_storm": 0, "name": "Normal Week (2023)"},
        {"start": "2017-04-21", "end": "2017-04-25", "is_storm": 0, "name": "Normal Week (2017d)"},
        {"start": "2016-03-15", "end": "2016-03-19", "is_storm": 0, "name": "Normal Week (2016)"},
        {"start": "2020-02-02", "end": "2020-02-06", "is_storm": 0, "name": "Normal Week (2020c)"},
        {"start": "2020-01-20", "end": "2020-01-25", "is_storm": 0, "name": "Normal Week (2020d)"}
    ]
    
    all_dfs = []
    total_events = len(events)
    
    for idx, ev in enumerate(events):
        print(f"[{idx+1}/{total_events}] Đang tải dữ liệu lô tối ưu cho: {ev['name']}...", flush=True)
        
        # Gọi API weather và marine đa tọa độ cùng lúc
        data_weather = fetch_multi_location_weather(ev['start'], ev['end'])
        time.sleep(0.1) # Giãn cách nhẹ
        data_marine = fetch_multi_location_marine(ev['start'], ev['end'])
        
        if data_weather is None or data_marine is None:
            print(f"  -> Lỗi bỏ qua sự kiện {ev['name']}", flush=True)
            continue
            
        station_names = list(STATIONS.keys())
        
        # Duyệt qua từng trạm khí tượng
        for i, station_name in enumerate(station_names):
            coords = STATIONS[station_name]
            
            hourly_w = data_weather[i].get('hourly', {})
            hourly_m = data_marine[i].get('hourly', {})
            
            df_station = process_station_data(station_name, coords, hourly_w, hourly_m, ev['is_storm'])
            if df_station is not None:
                all_dfs.append(df_station)
                
        # Tránh spam API
        time.sleep(0.4)
            
    if not all_dfs:
        print("Lỗi: Không tải được bất kỳ dữ liệu sự kiện nào.", flush=True)
        return
        
    df_all = pd.concat(all_dfs, ignore_index=True)
    
    # Lọc lấy bước thời gian 3 tiếng (tương thích GFS)
    df_all = df_all[df_all['timestamp'].dt.hour % 3 == 0].reset_index(drop=True)
    df_all = df_all.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    print("\n--- THỐNG KÊ SIÊU CƠ SỞ DỮ LIỆU BÃO BIỂN ĐÔNG TỐI ƯU ---", flush=True)
    print(f"Tổng số hàng mẫu dữ liệu: {len(df_all)}", flush=True)
    print(df_all['storm_severity'].value_counts().sort_index(), flush=True)
    
    # Lưu tệp tin
    df_all.to_csv(HISTORICAL_CSV, index=False)
    print(f"\nĐã lưu trữ thành công Siêu cơ sở dữ liệu bão tại: {HISTORICAL_CSV}", flush=True)

if __name__ == "__main__":
    main()
