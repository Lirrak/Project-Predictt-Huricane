import os
import sys
import time
import datetime
import glob
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
STORMS_LIST_CSV = os.path.join(BASE_DIR, "data", "scs_all_storms_1999_to_present.csv")
TEMP_DIR = os.path.join(BASE_DIR, "data", "temp_yearly_data")

os.makedirs(TEMP_DIR, exist_ok=True)

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
    """Tải dữ liệu thời tiết thô cho tất cả 37 trạm cùng một lúc bằng cơ chế Multi-location Query của Open-Meteo."""
    lats = ",".join([str(STATIONS[name]["lat"]) for name in STATIONS])
    lons = ",".join([str(STATIONS[name]["lon"]) for name in STATIONS])
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m"
    try:
        r = requests.get(url, timeout=45)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def fetch_multi_location_marine(start_date, end_date):
    """Tải dữ liệu sóng biển và hải lưu cho tất cả 37 trạm cùng một lúc bằng cơ chế Multi-location Query của Open-Meteo."""
    lats = ",".join([str(STATIONS[name]["lat"]) for name in STATIONS])
    lons = ",".join([str(STATIONS[name]["lon"]) for name in STATIONS])
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature"
    try:
        r = requests.get(url, timeout=45)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def process_station_year_data(station_name, coords, hourly_w, hourly_m):
    """Đồng bộ hóa dữ liệu thời tiết & hải dương của một trạm cho 1 năm."""
    df_weather = pd.DataFrame({
        'timestamp': pd.to_datetime(hourly_w['time']),
        'temp_2m': hourly_w['temperature_2m'],
        'rh_2m': hourly_w['relative_humidity_2m'],
        'press_hpa': hourly_w['surface_pressure'],
        'precipitation': hourly_w['precipitation'],
        'wind_speed': hourly_w['wind_speed_10m'],
        'wind_dir': hourly_w['wind_direction_10m']
    })
    
    # Một số mốc cũ có thể bị thiếu marine (null)
    if hourly_m and 'wave_height' in hourly_m:
        df_marine = pd.DataFrame({
            'timestamp': pd.to_datetime(hourly_m['time']),
            'wave_height': hourly_m['wave_height'],
            'wave_direction': hourly_m['wave_direction'],
            'wave_period': hourly_m['wave_period'],
            'ocean_current_velocity': hourly_m['ocean_current_velocity'],
            'ocean_current_direction': hourly_m['ocean_current_direction'],
            'sea_surface_temperature': hourly_m['sea_surface_temperature']
        })
    else:
        df_marine = pd.DataFrame({
            'timestamp': df_weather['timestamp'],
            'wave_height': [0.0] * len(df_weather),
            'wave_direction': [0.0] * len(df_weather),
            'wave_period': [0.0] * len(df_weather),
            'ocean_current_velocity': [0.0] * len(df_weather),
            'ocean_current_direction': [0.0] * len(df_weather),
            'sea_surface_temperature': [0.0] * len(df_weather)
        })
    
    df = pd.merge(df_weather, df_marine, on='timestamp', how='inner')
    
    # Ép kiểu dữ liệu
    for col in df.columns:
        if col != 'timestamp':
            df[col] = pd.to_numeric(df[col], errors='coerce').ffill().bfill().fillna(0.0)
            
    # Quy đổi vật lý giống GFS
    df['TMP'] = df['temp_2m'] + 273.15
    df['RH'] = df['rh_2m']
    df['PRES'] = df['press_hpa'] * 100.0
    df['APCP'] = df['precipitation']
    
    speed_ms = df['wind_speed'] / 3.6
    dir_rad = np.radians(df['wind_dir'])
    df['UGRD'] = -speed_ms * np.sin(dir_rad)
    df['VGRD'] = -speed_ms * np.cos(dir_rad)
    
    df['WAVE_H'] = df['wave_height']
    df['WAVE_DIR'] = df['wave_direction']
    df['WAVE_P'] = df['wave_period']
    df['CURRENT_VEL'] = df['ocean_current_velocity']
    df['CURRENT_DIR'] = df['ocean_current_direction']
    df['SST'] = df['sea_surface_temperature']
    if (df['SST'] > 0.0).any():
        df['SST'] = df['SST'] + 273.15
        
    df['station_name'] = station_name
    df['latitude'] = coords['lat']
    df['longitude'] = coords['lon']
    
    final_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'PRES', 
                  'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'APCP']
    return df[final_cols]

def process_reconstruction_vectorized(df):
    """
    Tái thiết lập cực nhanh bằng Vectorization trên NumPy/Pandas (nhanh gấp 1000 lần so với iterrows).
    """
    u = df['UGRD'].values
    v = df['VGRD'].values
    tmp = df['TMP'].values
    pres = df['PRES'].values
    is_storm = df['is_storm_period'].values
    
    wind_speed = np.sqrt(u**2 + v**2)
    wind_dir = np.degrees(np.arctan2(-u, -v)) % 360.0
    
    np.random.seed(42)
    noise_h = np.random.normal(0, 0.1, len(df))
    noise_p = np.random.normal(0, 0.3, len(df))
    noise_dir = np.random.normal(0, 5, len(df))
    noise_vel = np.random.normal(0, 0.02, len(df))
    noise_sst = np.random.normal(0, 0.5, len(df))
    
    # 1. WAVE_H
    wave_h_calc = 0.022 * (wind_speed ** 1.9) + noise_h
    wave_h_calc = np.clip(wave_h_calc, 0.1, None)
    df['WAVE_H'] = np.where(df['WAVE_H'] == 0.0, wave_h_calc, df['WAVE_H'])
    
    # 2. WAVE_P
    wave_p_calc = 0.45 * wind_speed + noise_p
    wave_p_calc = np.clip(wave_p_calc, 2.0, None)
    df['WAVE_P'] = np.where(df['WAVE_P'] == 0.0, wave_p_calc, df['WAVE_P'])
    
    # 3. WAVE_DIR
    wave_dir_calc = (wind_dir + noise_dir) % 360.0
    df['WAVE_DIR'] = np.where(df['WAVE_DIR'] == 0.0, wave_dir_calc, df['WAVE_DIR'])
    
    # 4. CURRENT_VEL
    curr_vel_calc = 0.028 * wind_speed + noise_vel
    curr_vel_calc = np.clip(curr_vel_calc, 0.05, None)
    df['CURRENT_VEL'] = np.where(df['CURRENT_VEL'] == 0.0, curr_vel_calc, df['CURRENT_VEL'])
    
    # 5. CURRENT_DIR
    curr_dir_calc = (wind_dir + 45.0 + noise_dir) % 360.0
    df['CURRENT_DIR'] = np.where(df['CURRENT_DIR'] == 0.0, curr_dir_calc, df['CURRENT_DIR'])
    
    # 6. SST
    sst_calc = 301.15 + noise_sst - df['WAVE_H'].values * 0.25
    sst_calc = np.clip(sst_calc, 298.15, None)
    mask_sst = (df['SST'] == df['TMP']) | (df['SST'] == 0.0)
    df['SST'] = np.where(mask_sst, sst_calc, df['SST'])
    
    # 7. storm_severity (chuẩn Việt Nam/Biển Đông theo tốc độ gió)
    sev = np.zeros(len(df), dtype=int)
    
    # Cấp 1: Áp thấp nhiệt đới
    mask_1 = (wind_speed >= 10.8) & (wind_speed < 17.2)
    sev[mask_1] = 1
    # Cấp 2: Bão thường
    mask_2 = (wind_speed >= 17.2) & (wind_speed < 24.5)
    sev[mask_2] = 2
    # Cấp 3: Bão mạnh
    mask_3 = (wind_speed >= 24.5) & (wind_speed < 32.7)
    sev[mask_3] = 3
    # Cấp 4: Bão rất mạnh
    mask_4 = (wind_speed >= 32.7) & (wind_speed < 51.0)
    sev[mask_4] = 4
    # Cấp 5: Siêu bão
    mask_5 = (wind_speed >= 51.0)
    sev[mask_5] = 5
    
    # Áp thấp vùng rìa bão
    mask_rest = (sev == 0) & (is_storm == 1)
    sev[mask_rest] = 1
    
    df['storm_severity'] = sev
    
    # CAPE & PWAT
    hour_series = df['timestamp'].dt.hour.values
    diurnal_cape = np.maximum(0.0, (tmp - 273.15 - 24.0) * 150.0) * np.isin(hour_series, range(10, 20)).astype(float)
    storm_cape = df['storm_severity'].values * 200.0 * (df['RH'].values / 100.0)
    df['CAPE'] = diurnal_cape + storm_cape
    
    pwat_calc = 30.0 + (df['RH'].values - 50.0) * 0.4 + (tmp - 298.0) * 1.5 + (df['storm_severity'].values * 4.0)
    df['PWAT'] = np.clip(pwat_calc, 15.0, 80.0)
    
    return df

def main():
    if not os.path.exists(STORMS_LIST_CSV):
        print(f"Lỗi: Không tìm thấy danh sách bão tại {STORMS_LIST_CSV}. Hãy chạy build_historical_typhoon_list.py trước.")
        return
        
    df_storms_list = pd.read_csv(STORMS_LIST_CSV)
    df_storms_list['START_DATE'] = pd.to_datetime(df_storms_list['START_DATE'])
    df_storms_list['END_DATE'] = pd.to_datetime(df_storms_list['END_DATE'])
    
    current_year = datetime.datetime.now().year
    years_to_download = list(range(1999, current_year + 1))
    
    print(f"=== BẮT ĐẦU TẢI DỮ LIỆU ĐA TRẠM BIỂN ĐÔNG TỪ {years_to_download[0]} ĐẾN {years_to_download[-1]} ===")
    
    for yr in years_to_download:
        temp_file = os.path.join(TEMP_DIR, f"data_{yr}.csv")
        
        if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
            continue
            
        print(f"  [Năm {yr}] Đang tải weather & marine từ Open-Meteo...", flush=True)
        start_date = f"{yr}-01-01"
        end_date = f"{yr}-12-31" if yr < current_year else datetime.datetime.now().strftime("%Y-%m-%d")
        
        data_w = fetch_multi_location_weather(start_date, end_date)
        time.sleep(1.0)
        data_m = fetch_multi_location_marine(start_date, end_date)
        
        if data_w is None:
            print(f"    Lỗi: Không thể tải weather cho năm {yr}. Thử lại ở lần sau.")
            continue
            
        station_names = list(STATIONS.keys())
        yearly_station_dfs = []
        
        for i, st_name in enumerate(station_names):
            coords = STATIONS[st_name]
            
            hourly_w = data_w[i].get('hourly', {})
            hourly_m = data_m[i].get('hourly', {}) if data_m else None
            
            df_st = process_station_year_data(st_name, coords, hourly_w, hourly_m)
            yearly_station_dfs.append(df_st)
            
        df_year = pd.concat(yearly_station_dfs, ignore_index=True)
        df_year = df_year[df_year['timestamp'].dt.hour % 3 == 0].reset_index(drop=True)
        df_year.to_csv(temp_file, index=False)
        print(f"    [Năm {yr}] Tải thành công! Đã lưu cục bộ: {len(df_year)} dòng.")
        time.sleep(1.0)
        
    print("\n=== ĐANG ĐỒNG BỘ HỢP NHẤT TOÀN BỘ 28 NĂM VÀ LỌC BÃO ===")
    
    all_year_files = sorted(glob.glob(os.path.join(TEMP_DIR, "data_*.csv")))
    if not all_year_files:
        print("Lỗi: Không tìm thấy tệp dữ liệu năm nào để gộp.")
        return
        
    print(f"Tìm thấy {len(all_year_files)} tệp năm. Đang tiến hành gộp dữ liệu...")
    df_all_years = pd.concat([pd.read_csv(f) for f in all_year_files], ignore_index=True)
    df_all_years['timestamp'] = pd.to_datetime(df_all_years['timestamp'])
    
    print(f"Tổng số dòng sau khi gộp: {len(df_all_years)}")
    
    # 1. Đánh nhãn bão bằng NumPy vectorization
    print("Đang thực hiện gán nhãn bão cho tất cả 452 cơn bão lịch sử bằng NumPy...")
    storm_intervals = list(zip(df_storms_list['START_DATE'], df_storms_list['END_DATE']))
    
    is_storm_vector = np.zeros(len(df_all_years), dtype=int)
    for start, end in storm_intervals:
        mask = (df_all_years['timestamp'] >= start) & (df_all_years['timestamp'] <= end)
        is_storm_vector[mask] = 1
        
    df_all_years['is_storm_period'] = is_storm_vector
    
    # 2. Lấy toàn bộ các dòng thuộc thời kỳ bão và tạo tập đối chứng cân bằng
    df_storms_only = df_all_years[df_all_years['is_storm_period'] == 1].copy()
    df_normal_only = df_all_years[df_all_years['is_storm_period'] == 0].copy()
    
    # Lấy mẫu ngẫu nhiên cân bằng tỷ lệ 50/50
    df_normal_sampled = df_normal_only.sample(n=min(len(df_storms_only), len(df_normal_only)), random_state=42)
    df_balanced = pd.concat([df_storms_only, df_normal_sampled], ignore_index=True)
    df_balanced = df_balanced.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    print(f"\nTổng số mẫu bão & ngày thường cân bằng: {len(df_balanced)}")
    
    # 3. Tái thiết lập đặc trưng hải dương bằng hàm Vectorized cực nhanh
    print("Đang chạy tái thiết lập vật lý hải dương học Vectorized nâng cao...")
    df_final = process_reconstruction_vectorized(df_balanced)
    
    # Giữ các cột chuẩn hóa cốt lõi
    final_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 
                  'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity', 'APCP']
    df_final = df_final[final_cols]
    
    print("\n--- THỐNG KÊ SIÊU CƠ SỞ DỮ LIỆU BÃO 28 NĂM BIỂN ĐÔNG HOÀN THIỆN ---")
    print(df_final['storm_severity'].value_counts().sort_index())
    
    df_final.to_csv(HISTORICAL_CSV, index=False)
    print(f"\nĐã ghi đè Siêu cơ sở dữ liệu bão 28 năm thành công tại: {HISTORICAL_CSV}")

if __name__ == "__main__":
    main()
