import os
import sys
import time
import argparse
import datetime
import numpy as np
import pandas as pd
import requests
from xgboost import XGBRegressor

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị bảng điều khiển tiếng Việt đẹp mắt
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_JSON_RAIN = os.path.join(BASE_DIR, "models", "xgboost_rain_model.json")
MODEL_JSON_WIND = os.path.join(BASE_DIR, "models", "xgboost_wind_model.json")
MODEL_JSON_PRES = os.path.join(BASE_DIR, "models", "xgboost_pres_model.json")

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

# Các đặc trưng đầu vào theo đúng thứ tự huấn luyện của mô hình XGBoost (45 đặc trưng)
FEATURE_COLS_54 = [
    'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'WAVE_H', 'WAVE_DIR', 'WAVE_P',
    'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity',
    'TMP_lag1', 'TMP_lag2', 'RH_lag1', 'RH_lag2', 'UGRD_lag1', 'UGRD_lag2', 
    'VGRD_lag1', 'VGRD_lag2', 'CAPE_lag1', 'CAPE_lag2', 'PWAT_lag1', 'PWAT_lag2', 
    'APCP_lag1', 'APCP_lag2', 'WAVE_H_lag1', 'WAVE_H_lag2', 'CURRENT_VEL_lag1', 'CURRENT_VEL_lag2',
    'SST_lag1', 'SST_lag2', 'PRES_lag1', 'PRES_lag2', 'RH_rolling_mean_12h', 'TMP_rolling_mean_12h',
    'PRES_rolling_mean_12h', 'WIND_SPEED_lag1', 'WIND_SPEED_lag2', 'WIND_rolling_mean_12h', 'WIND_rolling_max_12h',
    'PRES_change_6h', 'WIND_change_6h', 'hour', 'month',
    'MPI', 'wind_shear_mag_lag1', 'wind_shear_mag_lag2', 'wind_shear_vec_lag1', 'wind_shear_vec_lag2', 'climatology_prior'
]

# Tên tương ứng của 6 cấp độ bão khí tượng
SEVERITY_NAMES = {
    0: "Bình thường",
    1: "Áp thấp n.đới",
    2: "Bão thường",
    3: "Bão mạnh",
    4: "Bão rất mạnh",
    5: "Siêu bão"
}

is_fallback_active = False

def load_climatology_priors():
    hist_path = os.path.join(BASE_DIR, "data", "historical_storm_weather.csv")
    if os.path.exists(hist_path):
        try:
            df_hist = pd.read_csv(hist_path, usecols=['latitude', 'longitude', 'storm_severity', 'timestamp'])
            df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
            df_hist['month'] = df_hist['timestamp'].dt.month
            df_hist['lat_round'] = df_hist['latitude'].round(1)
            df_hist['lon_round'] = df_hist['longitude'].round(1)
            
            prior_dict = df_hist.groupby(['lat_round', 'lon_round', 'month'])['storm_severity'].apply(
                lambda s: (s > 0).mean()
            ).to_dict()
            return prior_dict
        except Exception:
            pass
    return {}

priors_dict = load_climatology_priors()

def fetch_all_stations_raw_data():
    lats = ",".join([str(coords['lat']) for coords in STATIONS.values()])
    lons = ",".join([str(coords['lon']) for coords in STATIONS.values()])
    
    url_w = f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m&past_hours=12&forecast_days=1&timezone=GMT"
    url_m = f"https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature&past_hours=12&forecast_days=1&timezone=GMT"
    
    data_w, data_m = None, None
    try:
        r_w = requests.get(url_w, timeout=10)
        if r_w.status_code == 200:
            data_w = r_w.json()
    except Exception:
        pass
        
    try:
        r_m = requests.get(url_m, timeout=10)
        if r_m.status_code == 200:
            data_m = r_m.json()
    except Exception:
        pass
        
    return data_w, data_m

def compute_wind_components(speed_kmh, direction_deg):
    """Quy đổi hướng và tốc độ gió thành thành phần UGRD, VGRD (m/s)."""
    try:
        if pd.isna(speed_kmh) or pd.isna(direction_deg):
            return 0.0, 0.0
        speed_ms = float(speed_kmh) / 3.6
        rad = np.radians(float(direction_deg))
        return -speed_ms * np.sin(rad), -speed_ms * np.cos(rad)
    except Exception:
        return 0.0, 0.0

def make_prediction_for_station(models, station_name, coords, station_w, station_m, simulated_storm_level=None):
    """
    Thu thập thời tiết khí quyển và hải dương để đưa ra dự đoán lượng mưa, gió, và khí áp.
    Tự động áp dụng failover ngoại tuyến nếu API lỗi.
    """
    global is_fallback_active
    model_rain, model_wind, model_pres = models
    
    err_w = station_w is None
    err_m = station_m is None
    
    # 1. Cơ chế dự phòng ngoại tuyến nếu lỗi bất kỳ API nào
    if err_w or err_m:
        is_fallback_active = True
        now_utc = datetime.datetime.utcnow()
        times = [now_utc - datetime.timedelta(hours=h) for h in range(12, -13, -1)]
        times = sorted(times)
        
        np.random.seed(hash(station_name) % 1000)
        
        temp_base = 29.0 if "Sa" in station_name or "Tay" in station_name else 28.0
        temp_noise = np.random.normal(0, 0.5, len(times))
        rh_noise = np.random.normal(0, 2, len(times))
        
        hourly_w = {
            'time': [t.strftime("%Y-%m-%dT%H:00") for t in times],
            'temperature_2m': [temp_base + np.sin(2*np.pi*t.hour/24)*2.0 + n for t, n in zip(times, temp_noise)],
            'relative_humidity_2m': [80.0 - np.sin(2*np.pi*t.hour/24)*8.0 + n for t, n in zip(times, rh_noise)],
            'surface_pressure': [1008.0 + np.sin(4*np.pi*t.hour/24)*1.0 for t in times],
            'precipitation': [0.0] * len(times),
            'wind_speed_10m': [15.0 + np.random.uniform(0, 10.0) for _ in times],
            'wind_direction_10m': [180.0 + np.random.uniform(-30, 30) for _ in times]
        }
        
        # Mặc định biển lặng ngoại tuyến
        hourly_m = {
            'wave_height': [1.0 + np.random.uniform(-0.2, 0.2) for _ in times],
            'wave_direction': [180.0 + np.random.uniform(-10, 10) for _ in times],
            'wave_period': [5.0 + np.random.uniform(-0.5, 0.5) for _ in times],
            'ocean_current_velocity': [0.15 + np.random.uniform(-0.05, 0.05) for _ in times],
            'ocean_current_direction': [180.0 + np.random.uniform(-10, 10) for _ in times],
            'sea_surface_temperature': [28.5 + np.sin(2*np.pi*t.hour/24)*0.5 for t in times]
        }
        
        # Mô phỏng các mức độ bão khí tượng hải dương tương thích vật lý bão cực đoan
        if simulated_storm_level is not None and simulated_storm_level > 0:
            sev = simulated_storm_level
            hourly_w['wind_speed_10m'] = [20.0 + sev * 15.0 + np.random.uniform(0, 5.0) for _ in times]
            hourly_w['surface_pressure'] = [1005.0 - sev * 12.0 + np.sin(4*np.pi*t.hour/24)*1.0 for t in times]
            
            # Càng bão to sóng càng cao, dòng hải lưu càng chảy siết và nhiệt độ nước biển sụt giảm (Upwelling)
            hourly_m['wave_height'] = [1.2 + sev * 2.1 + np.random.uniform(0, 0.5) for _ in times]
            hourly_m['wave_period'] = [5.0 + sev * 1.5 for _ in times]
            hourly_m['ocean_current_velocity'] = [0.2 + sev * 0.28 for _ in times]
            hourly_m['sea_surface_temperature'] = [28.5 - sev * 0.9 for _ in times]
    else:
        hourly_w = station_w.get('hourly', {})
        hourly_m = station_m.get('hourly', {})
        
    # Ép kiểu dữ liệu
    df_raw = pd.DataFrame({
        'time': pd.to_datetime(hourly_w['time']),
        'temp_2m': pd.to_numeric(hourly_w['temperature_2m'], errors='coerce'),
        'rh_2m': pd.to_numeric(hourly_w['relative_humidity_2m'], errors='coerce'),
        'press_hpa': pd.to_numeric(hourly_w['surface_pressure'], errors='coerce'),
        'precipitation': pd.to_numeric(hourly_w['precipitation'], errors='coerce'),
        'wind_speed': pd.to_numeric(hourly_w['wind_speed_10m'], errors='coerce'),
        'wind_dir': pd.to_numeric(hourly_w['wind_direction_10m'], errors='coerce'),
        'wave_height': pd.to_numeric(hourly_m['wave_height'], errors='coerce'),
        'wave_direction': pd.to_numeric(hourly_m['wave_direction'], errors='coerce'),
        'wave_period': pd.to_numeric(hourly_m['wave_period'], errors='coerce'),
        'ocean_current_velocity': pd.to_numeric(hourly_m['ocean_current_velocity'], errors='coerce'),
        'ocean_current_direction': pd.to_numeric(hourly_m['ocean_current_direction'], errors='coerce'),
        'sea_surface_temperature': pd.to_numeric(hourly_m['sea_surface_temperature'], errors='coerce')
    })
    
    # Điền khuyết
    for col in df_raw.columns:
        if col != 'time':
            df_raw[col] = df_raw[col].ffill().bfill().fillna(0.0)
            
    # 2. Quy đổi vật lý giống GFS
    df_raw['TMP'] = df_raw['temp_2m'] + 273.15
    df_raw['RH'] = df_raw['rh_2m']
    df_raw['PRES'] = df_raw['press_hpa'] * 100.0
    df_raw['APCP'] = df_raw['precipitation']
    
    # Quy đổi sóng và hải lưu
    df_raw['WAVE_H'] = df_raw['wave_height']
    df_raw['WAVE_DIR'] = df_raw['wave_direction']
    df_raw['WAVE_P'] = df_raw['wave_period']
    df_raw['CURRENT_VEL'] = df_raw['ocean_current_velocity']
    df_raw['CURRENT_DIR'] = df_raw['ocean_current_direction']
    df_raw['SST'] = df_raw['sea_surface_temperature'] + 273.15
    
    u_vals, v_vals = [], []
    for _, row in df_raw.iterrows():
        u, v = compute_wind_components(row['wind_speed'], row['wind_dir'])
        u_vals.append(u)
        v_vals.append(v)
    df_raw['UGRD'] = u_vals
    df_raw['VGRD'] = v_vals
    
    # Định vị hàng hiện tại ( naive UTC )
    now_utc_naive = datetime.datetime.utcnow()
    df_raw['time_diff'] = np.abs((df_raw['time'] - now_utc_naive).dt.total_seconds())
    current_idx = df_raw['time_diff'].idxmin()
    
    # Xác định mốc thời gian lùi
    idx_now = current_idx
    idx_lag1 = current_idx - 3
    idx_lag2 = current_idx - 6
    idx_lag3 = current_idx - 9
    
    if idx_lag2 < 0 or idx_lag3 < 0:
        idx_lag1 = max(0, current_idx - 1)
        idx_lag2 = max(0, current_idx - 2)
        idx_lag3 = max(0, current_idx - 3)
        
    row_now = df_raw.iloc[idx_now]
    row_lag1 = df_raw.iloc[idx_lag1]
    row_lag2 = df_raw.iloc[idx_lag2]
    row_lag3 = df_raw.iloc[idx_lag3]
    
    # 3. Tính toán Cấp độ bão (storm_severity)
    if simulated_storm_level is not None:
        storm_severity = int(simulated_storm_level)
    else:
        wind_speed_ms = row_now['wind_speed'] / 3.6
        if wind_speed_ms >= 51.0:
            storm_severity = 5  # Siêu bão
        elif 32.7 <= wind_speed_ms < 51.0:
            storm_severity = 4  # Bão rất mạnh
        elif 24.5 <= wind_speed_ms < 32.7:
            storm_severity = 3  # Bão mạnh
        elif 17.2 <= wind_speed_ms < 24.5:
            storm_severity = 2  # Bão thường
        elif 10.8 <= wind_speed_ms < 17.2:
            storm_severity = 1  # Áp thấp nhiệt đới
        else:
            storm_severity = 0  # Bình thường

    # Ước lượng CAPE và PWAT dựa trên cấp độ bão
    hour_series = df_raw['time'].dt.hour
    diurnal_cape = np.maximum(0.0, (df_raw['temp_2m'] - 24.0) * 150.0) * (hour_series.isin(range(10, 20)).astype(float))
    storm_cape = (storm_severity * 200.0) * (df_raw['RH'] / 100.0)
    df_raw['CAPE'] = diurnal_cape + storm_cape
    
    df_raw['PWAT'] = 30.0 + (df_raw['RH'] - 50.0) * 0.4 + (df_raw['TMP'] - 298.0) * 1.5 + (storm_severity * 4.0)
    df_raw['PWAT'] = df_raw['PWAT'].clip(lower=15.0, upper=80.0)
    
    # Cập nhật lại sau khi tính CAPE/PWAT
    row_now = df_raw.iloc[idx_now]
    row_lag1 = df_raw.iloc[idx_lag1]
    row_lag2 = df_raw.iloc[idx_lag2]
    row_lag3 = df_raw.iloc[idx_lag3]
    
    # Tính toán các biến Rolling Mean 12h
    rh_rolling = np.mean([row_now['RH'], row_lag1['RH'], row_lag2['RH'], row_lag3['RH']])
    tmp_rolling = np.mean([row_now['TMP'], row_lag1['TMP'], row_lag2['TMP'], row_lag3['TMP']])
    pres_rolling = np.mean([row_now['PRES'], row_lag1['PRES'], row_lag2['PRES'], row_lag3['PRES']])
    
    # 1. Tính toán Maximum Potential Intensity (MPI)
    sst_c = row_now['SST'] - 273.15
    e_s = 6.112 * np.exp(17.67 * sst_c / (sst_c + 243.5))
    temp_diff_ratio = max(0.0, row_now['SST'] - row_now['TMP']) / max(200.0, row_now['TMP'])
    mpi = 70.0 * np.sqrt(temp_diff_ratio * e_s)
    
    # 2. Tính toán Wind Shear
    WS_now = np.sqrt(row_now['UGRD']**2 + row_now['VGRD']**2)
    WS_lag1 = np.sqrt(row_lag1['UGRD']**2 + row_lag1['VGRD']**2)
    WS_lag2 = np.sqrt(row_lag2['UGRD']**2 + row_lag2['VGRD']**2)
    WS_lag3 = np.sqrt(row_lag3['UGRD']**2 + row_lag3['VGRD']**2)
    
    wind_shear_mag_lag1 = np.abs(WS_now - WS_lag1)
    wind_shear_mag_lag2 = np.abs(WS_now - WS_lag2)
    
    wind_shear_vec_lag1 = np.sqrt((row_now['UGRD'] - row_lag1['UGRD'])**2 + (row_now['VGRD'] - row_lag1['VGRD'])**2)
    wind_shear_vec_lag2 = np.sqrt((row_now['UGRD'] - row_lag2['UGRD'])**2 + (row_now['VGRD'] - row_lag2['VGRD'])**2)
    
    # 3. Wind rolling features and changes
    wind_rolling_mean = np.mean([WS_now, WS_lag1, WS_lag2, WS_lag3])
    wind_rolling_max = np.max([WS_now, WS_lag1, WS_lag2, WS_lag3])
    pres_change = row_now['PRES'] - row_lag2['PRES']
    wind_change = WS_now - WS_lag2
    
    # 4. Tính toán Climatological Prior
    current_month = row_now['time'].month
    lat_round = round(coords['lat'], 1)
    lon_round = round(coords['lon'], 1)
    climatology_prior = 0.2
    if priors_dict and (lat_round, lon_round, current_month) in priors_dict:
        climatology_prior = priors_dict[(lat_round, lon_round, current_month)]
    else:
        default_priors = {1: 0.05, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.1, 6: 0.2, 
                          7: 0.4, 8: 0.5, 9: 0.6, 10: 0.5, 11: 0.3, 12: 0.1}
        climatology_prior = default_priors.get(current_month, 0.2)

    # 5. Tạo vector đặc trưng đầu vào (54 đặc trưng)
    feat_dict = {
        'latitude': coords['lat'], 'longitude': coords['lon'],
        'TMP': row_now['TMP'], 'RH': row_now['RH'], 'UGRD': row_now['UGRD'], 'VGRD': row_now['VGRD'],
        'CAPE': row_now['CAPE'], 'PWAT': row_now['PWAT'],
        'WAVE_H': row_now['WAVE_H'], 'WAVE_DIR': row_now['WAVE_DIR'], 'WAVE_P': row_now['WAVE_P'],
        'CURRENT_VEL': row_now['CURRENT_VEL'], 'CURRENT_DIR': row_now['CURRENT_DIR'], 'SST': row_now['SST'],
        'storm_severity': int(storm_severity),
        'TMP_lag1': row_lag1['TMP'], 'TMP_lag2': row_lag2['TMP'],
        'RH_lag1': row_lag1['RH'], 'RH_lag2': row_lag2['RH'],
        'UGRD_lag1': row_lag1['UGRD'], 'UGRD_lag2': row_lag2['UGRD'],
        'VGRD_lag1': row_lag1['VGRD'], 'VGRD_lag2': row_lag2['VGRD'],
        'CAPE_lag1': row_lag1['CAPE'], 'CAPE_lag2': row_lag2['CAPE'],
        'PWAT_lag1': row_lag1['PWAT'], 'PWAT_lag2': row_lag2['PWAT'],
        'APCP_lag1': row_lag1['APCP'], 'APCP_lag2': row_lag2['APCP'],
        'WAVE_H_lag1': row_lag1['WAVE_H'], 'WAVE_H_lag2': row_lag2['WAVE_H'],
        'CURRENT_VEL_lag1': row_lag1['CURRENT_VEL'], 'CURRENT_VEL_lag2': row_lag2['CURRENT_VEL'],
        'SST_lag1': row_lag1['SST'], 'SST_lag2': row_lag2['SST'],
        'PRES_lag1': row_lag1['PRES'], 'PRES_lag2': row_lag2['PRES'],
        'RH_rolling_mean_12h': rh_rolling, 'TMP_rolling_mean_12h': tmp_rolling,
        'PRES_rolling_mean_12h': pres_rolling,
        'WIND_SPEED_lag1': WS_lag1, 'WIND_SPEED_lag2': WS_lag2,
        'WIND_rolling_mean_12h': wind_rolling_mean, 'WIND_rolling_max_12h': wind_rolling_max,
        'PRES_change_6h': pres_change, 'WIND_change_6h': wind_change,
        'hour': row_now['time'].hour, 'month': current_month,
        'MPI': mpi,
        'wind_shear_mag_lag1': wind_shear_mag_lag1, 'wind_shear_mag_lag2': wind_shear_mag_lag2,
        'wind_shear_vec_lag1': wind_shear_vec_lag1, 'wind_shear_vec_lag2': wind_shear_vec_lag2,
        'climatology_prior': climatology_prior
    }
    
    df_input = pd.DataFrame([feat_dict])[FEATURE_COLS_54]
    
    # Dự đoán bằng các mô hình đa nhiệm
    try:
        pred_rain = max(0.0, float(model_rain.predict(df_input)[0]))
        pred_wind_ms = max(0.0, float(model_wind.predict(df_input)[0]))
        pred_wind = pred_wind_ms * 3.6  # m/s -> km/h
        pred_pres_pa = float(model_pres.predict(df_input)[0])
        pred_pres = pred_pres_pa / 100.0  # Pa -> hPa
    except Exception:
        pred_rain = max(0.0, float(row_now['precipitation']))
        pred_wind = float(row_now['wind_speed'])
        pred_pres = float(row_now['press_hpa'])
    
    return {
        'station_name': station_name,
        'time': (row_now['time'] + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M"),
        'temp': row_now['temp_2m'],
        'rh': row_now['rh_2m'],
        'wind_speed': row_now['wind_speed'],
        'press': row_now['press_hpa'],
        'wave_h': row_now['WAVE_H'],
        'current_vel': row_now['CURRENT_VEL'],
        'sst': row_now['SST'] - 273.15, # Chuyển về °C để hiển thị
        'storm_severity': int(storm_severity),
        'pred_rain': max(0.0, pred_rain),
        'pred_wind': max(0.0, pred_wind),
        'pred_pres': max(0.0, pred_pres)
    }

def main():
    global is_fallback_active
    parser = argparse.ArgumentParser(description="Raspberry Pi Lightweight Weather & Oceanography Predictor using XGBoost")
    parser.add_argument("--storm", type=int, choices=[0, 1, 2, 3, 4, 5], nargs='?', const=1, 
                        help="Giả lập bão (0:Bình thường, 1:Áp thấp, 2:Bão thường, 3:Bão mạnh, 4:Bão rất mạnh, 5:Siêu bão)")
    args = parser.parse_args()

    print("\n==========================================================================================")
    print("      RASPBERRY PI LIGHTWEIGHT OCEANOGRAPHY & METEOROLOGY FORECAST SYSTEM - BIỂN ĐÔNG")
    print("==========================================================================================")
    print(f"Thời gian chạy: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    simulated_storm = None
    if args.storm is not None:
        simulated_storm = args.storm
        print(f"Trạng thái bão: [GIẢ LẬP - {SEVERITY_NAMES[simulated_storm].upper()}]")
    else:
        print(f"Trạng thái bão: [TỰ ĐỘNG - THỜI GIAN THỰC]")

    # 1. Nạp mô hình XGBoost 45 đặc trưng
    if not os.path.exists(MODEL_JSON_RAIN):
        print(f"Lỗi: Không tìm thấy tệp mô hình tại {MODEL_JSON_RAIN}!")
        return

    try:
        model_rain = XGBRegressor()
        model_rain.load_model(MODEL_JSON_RAIN)
        
        model_wind = XGBRegressor()
        model_wind.load_model(MODEL_JSON_WIND)
        
        model_pres = XGBRegressor()
        model_pres.load_model(MODEL_JSON_PRES)
        
        models = (model_rain, model_wind, model_pres)
    except Exception as e:
        print(f"Lỗi khi nạp mô hình: {e}")
        return

    # 2. Dự báo cho cả 37 trạm
    results = []
    raw_w_list, raw_m_list = fetch_all_stations_raw_data()
    
    is_valid_w = isinstance(raw_w_list, list) and len(raw_w_list) == len(STATIONS)
    is_valid_m = isinstance(raw_m_list, list) and len(raw_m_list) == len(STATIONS)
    
    for idx, (name, coords) in enumerate(STATIONS.items()):
        station_w = raw_w_list[idx] if is_valid_w else None
        station_m = raw_m_list[idx] if is_valid_m else None
        
        res = make_prediction_for_station(models, name, coords, station_w, station_m, simulated_storm)
        if res:
            results.append(res)
            
    if not results:
        print("Không thể lấy dữ liệu cho bất kỳ trạm nào.")
        return

    if is_fallback_active:
        print("\n[CẢNH BÁO]: Open-Meteo API bị lỗi/mất mạng. Đang sử dụng CƠ SỞ DỮ LIỆU DỰ PHÒNG NGOẠI TUYẾN.")

    # 3. Hiển thị bảng điều khiển dự báo hải dương khí tượng siêu đẹp
    print("\n+-----------------+-------------------+------------+----------+-------------------+------------+-----------+-----------+-------------------+---------------+------------------+")
    print("| Trạm Khí Tượng  | Thời Gian (Giờ VN)| Nhiệt Độ   | Độ Ẩm    | TỐC ĐỘ GIÓ (D.báo)| Sóng Biển  | Hải Lưu   | Nhiệt Biển| KHÍ ÁP (Dự báo)   | Cấp Độ Bão    | DỰ BÁO MƯA (24h) |")
    print("+-----------------+-------------------+------------+----------+-------------------+------------+-----------+-----------+-------------------+---------------+------------------+")
    for r in results:
        rain_alert = "KHÔNG MƯA"
        if r['pred_rain'] > 10.0:
            rain_alert = f"MƯA RẤT TO ({r['pred_rain']:.1f} mm)"
        elif r['pred_rain'] > 5.0:
            rain_alert = f"MƯA TO ({r['pred_rain']:.1f} mm)"
        elif r['pred_rain'] > 0.5:
            rain_alert = f"MƯA VỪA ({r['pred_rain']:.1f} mm)"
        elif r['pred_rain'] > 0.05:
            rain_alert = f"MƯA PHÙN ({r['pred_rain']:.2f} mm)"
            
        severity_label = SEVERITY_NAMES[r['storm_severity']]
        wind_display = f"{r['wind_speed']:>4.1f} ({r['pred_wind']:>4.1f}) km/h"
        pres_display = f"{r['press']:>6.1f} ({r['pred_pres']:>6.1f})"
        
        print(f"| {r['station_name']:<15} | {r['time']:<17} | {r['temp']:>7}°C | {r['rh']:>6}% | {wind_display:<17} | {r['wave_h']:>8.1f}m | {r['current_vel']:>6.2f}m/s | {r['sst']:>7.1f}°C | {pres_display:<17} | {severity_label:<13} | {rain_alert:<16} |")
    print("+-----------------+-------------------+------------+----------+-------------------+------------+-----------+-----------+-------------------+---------------+------------------+")
    print("Hệ thống dự báo khí tượng hải dương hoàn thành nhiệm vụ thành công!\n")

if __name__ == "__main__":
    main()
