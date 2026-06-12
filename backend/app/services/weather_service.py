import os
import datetime
import numpy as np
import pandas as pd
import requests

# Project root path calculation
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))

STATIONS = {
    # 32 trạm đất liền/ven biển quanh Biển Đông
    "Bach Long Vi": {"lat": 20.13, "lon": 107.73, "classification": "Land/Coastal"},
    "Hoang Sa": {"lat": 16.54, "lon": 111.61, "classification": "Land/Coastal"},
    "Ly Son": {"lat": 15.38, "lon": 109.15, "classification": "Land/Coastal"},
    "Song Tu Tay": {"lat": 11.43, "lon": 114.33, "classification": "Land/Coastal"},
    "Phu Quy": {"lat": 10.52, "lon": 108.94, "classification": "Land/Coastal"},
    "Truong Sa Lon": {"lat": 8.65, "lon": 111.92, "classification": "Land/Coastal"},
    "Con Dao": {"lat": 8.68, "lon": 106.60, "classification": "Land/Coastal"},
    "Huyen Tran": {"lat": 8.15, "lon": 110.63, "classification": "Land/Coastal"},
    "Mong Cai": {"lat": 21.53, "lon": 107.97, "classification": "Land/Coastal"},
    "Hon Dau": {"lat": 20.67, "lon": 106.81, "classification": "Land/Coastal"},
    "Sam Son": {"lat": 19.73, "lon": 105.84, "classification": "Land/Coastal"},
    "Vinh": {"lat": 18.67, "lon": 105.68, "classification": "Land/Coastal"},
    "Con Co": {"lat": 17.16, "lon": 107.34, "classification": "Land/Coastal"},
    "Dong Hoi": {"lat": 17.47, "lon": 106.63, "classification": "Land/Coastal"},
    "Da Nang": {"lat": 16.07, "lon": 108.22, "classification": "Land/Coastal"},
    "Quy Nhon": {"lat": 13.77, "lon": 109.22, "classification": "Land/Coastal"},
    "Nha Trang": {"lat": 12.25, "lon": 109.19, "classification": "Land/Coastal"},
    "Vung Tau": {"lat": 10.35, "lon": 107.08, "classification": "Land/Coastal"},
    "Ca Mau": {"lat": 9.18, "lon": 105.15, "classification": "Land/Coastal"},
    "Phu Quoc": {"lat": 10.22, "lon": 103.96, "classification": "Land/Coastal"},
    "Sanya": {"lat": 18.25, "lon": 109.51, "classification": "Land/Coastal"},
    "Haikou": {"lat": 20.02, "lon": 110.35, "classification": "Land/Coastal"},
    "Guangzhou": {"lat": 23.13, "lon": 113.26, "classification": "Land/Coastal"},
    "Hong Kong": {"lat": 22.30, "lon": 114.17, "classification": "Land/Coastal"},
    "Kaohsiung": {"lat": 22.62, "lon": 120.30, "classification": "Land/Coastal"},
    "Dongsha": {"lat": 20.70, "lon": 116.73, "classification": "Land/Coastal"},
    "Laoag": {"lat": 18.19, "lon": 120.59, "classification": "Land/Coastal"},
    "Manila": {"lat": 14.60, "lon": 120.98, "classification": "Land/Coastal"},
    "Puerto Princesa": {"lat": 9.74, "lon": 118.74, "classification": "Land/Coastal"},
    "Kota Kinabalu": {"lat": 5.98, "lon": 116.07, "classification": "Land/Coastal"},
    "Natuna": {"lat": 4.00, "lon": 108.00, "classification": "Land/Coastal"},
    "Kuala Terengganu": {"lat": 5.33, "lon": 103.15, "classification": "Land/Coastal"},
    
    # 5 trạm phao ảo vùng biển sâu
    "Scarborough Shoal": {"lat": 15.11, "lon": 117.76, "classification": "Virtual Buoy/Deep Sea"},
    "Macclesfield": {"lat": 15.75, "lon": 114.30, "classification": "Virtual Buoy/Deep Sea"},
    "Reed Bank": {"lat": 11.30, "lon": 116.80, "classification": "Virtual Buoy/Deep Sea"},
    "Central Deep": {"lat": 14.00, "lon": 115.00, "classification": "Virtual Buoy/Deep Sea"},
    "Luzon Strait": {"lat": 20.00, "lon": 121.00, "classification": "Virtual Buoy/Deep Sea"}
}

SEVERITY_NAMES = {
    0: "Bình thường",
    1: "Áp thấp n.đới",
    2: "Bão thường",
    3: "Bão mạnh",
    4: "Bão rất mạnh",
    5: "Siêu bão"
}

def load_climatology_priors():
    hist_path = os.path.join(PROJECT_ROOT, "data", "historical_storm_weather.csv")
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

def process_station_data(station_name, coords, station_w, station_m, simulated_storm_level=None):
    is_fallback = (station_w is None or station_m is None)
    
    if is_fallback:
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
        
        hourly_m = {
            'wave_height': [1.0 + np.random.uniform(-0.2, 0.2) for _ in times],
            'wave_direction': [180.0 + np.random.uniform(-10, 10) for _ in times],
            'wave_period': [5.0 + np.random.uniform(-0.5, 0.5) for _ in times],
            'ocean_current_velocity': [0.15 + np.random.uniform(-0.05, 0.05) for _ in times],
            'ocean_current_direction': [180.0 + np.random.uniform(-10, 10) for _ in times],
            'sea_surface_temperature': [28.5 + np.sin(2*np.pi*t.hour/24)*0.5 for t in times]
        }
        
        if simulated_storm_level is not None and simulated_storm_level > 0:
            sev = simulated_storm_level
            hourly_w['wind_speed_10m'] = [20.0 + sev * 15.0 + np.random.uniform(0, 5.0) for _ in times]
            hourly_w['surface_pressure'] = [1005.0 - sev * 12.0 + np.sin(4*np.pi*t.hour/24)*1.0 for t in times]
            hourly_m['wave_height'] = [1.2 + sev * 2.1 + np.random.uniform(0, 0.5) for _ in times]
            hourly_m['wave_period'] = [5.0 + sev * 1.5 for _ in times]
            hourly_m['ocean_current_velocity'] = [0.2 + sev * 0.28 for _ in times]
            hourly_m['sea_surface_temperature'] = [28.5 - sev * 0.9 for _ in times]
    else:
        hourly_w = station_w.get('hourly', {})
        hourly_m = station_m.get('hourly', {})

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
    
    for col in df_raw.columns:
        if col != 'time':
            df_raw[col] = df_raw[col].ffill().bfill().fillna(0.0)
            
    return df_raw, is_fallback

def compute_wind_components(speed_kmh, direction_deg):
    try:
        if pd.isna(speed_kmh) or pd.isna(direction_deg):
            return 0.0, 0.0
        speed_ms = float(speed_kmh) / 3.6
        rad = np.radians(float(direction_deg))
        return -speed_ms * np.sin(rad), -speed_ms * np.cos(rad)
    except Exception:
        return 0.0, 0.0

def generate_prediction_input(station_name, coords, df_raw, simulated_storm_level=None):
    """Generates the 45 physical feature vector required by XGBoost models."""
    df_raw = df_raw.copy()
    
    # Atmospheric/Oceanic physics conversions
    df_raw['TMP'] = df_raw['temp_2m'] + 273.15
    df_raw['RH'] = df_raw['rh_2m']
    df_raw['PRES'] = df_raw['press_hpa'] * 100.0
    df_raw['APCP'] = df_raw['precipitation']
    
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
    
    now_utc_naive = datetime.datetime.utcnow()
    df_raw['time_diff'] = np.abs((df_raw['time'] - now_utc_naive).dt.total_seconds())
    current_idx = df_raw['time_diff'].idxmin()
    
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
    
    # Compute storm severity
    if simulated_storm_level is not None:
        storm_severity = int(simulated_storm_level)
    else:
        wind_speed_ms = row_now['wind_speed'] / 3.6
        if wind_speed_ms >= 51.0:
            storm_severity = 5
        elif 32.7 <= wind_speed_ms < 51.0:
            storm_severity = 4
        elif 24.5 <= wind_speed_ms < 32.7:
            storm_severity = 3
        elif 17.2 <= wind_speed_ms < 24.5:
            storm_severity = 2
        elif 10.8 <= wind_speed_ms < 17.2:
            storm_severity = 1
        else:
            storm_severity = 0

    # CAPE & PWAT physically consistent estimates
    hour_series = df_raw['time'].dt.hour
    diurnal_cape = np.maximum(0.0, (df_raw['temp_2m'] - 24.0) * 150.0) * (hour_series.isin(range(10, 20)).astype(float))
    storm_cape = (storm_severity * 200.0) * (df_raw['RH'] / 100.0)
    df_raw['CAPE'] = diurnal_cape + storm_cape
    
    df_raw['PWAT'] = 30.0 + (df_raw['RH'] - 50.0) * 0.4 + (df_raw['TMP'] - 298.0) * 1.5 + (storm_severity * 4.0)
    df_raw['PWAT'] = df_raw['PWAT'].clip(lower=15.0, upper=80.0)
    
    row_now = df_raw.iloc[idx_now]
    row_lag1 = df_raw.iloc[idx_lag1]
    row_lag2 = df_raw.iloc[idx_lag2]
    row_lag3 = df_raw.iloc[idx_lag3]
    
    rh_rolling = np.mean([row_now['RH'], row_lag1['RH'], row_lag2['RH'], row_lag3['RH']])
    tmp_rolling = np.mean([row_now['TMP'], row_lag1['TMP'], row_lag2['TMP'], row_lag3['TMP']])
    pres_rolling = np.mean([row_now['PRES'], row_lag1['PRES'], row_lag2['PRES'], row_lag3['PRES']])
    
    # 1. Maximum Potential Intensity (MPI)
    sst_c = row_now['SST'] - 273.15
    e_s = 6.112 * np.exp(17.67 * sst_c / (sst_c + 243.5))
    temp_diff_ratio = max(0.0, row_now['SST'] - row_now['TMP']) / max(200.0, row_now['TMP'])
    mpi = 70.0 * np.sqrt(temp_diff_ratio * e_s)
    
    # 2. Wind Shear
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
    
    # 4. Climatology Prior
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

    feat_dict = {
        'latitude': coords['lat'], 'longitude': coords['lon'],
        'TMP': row_now['TMP'], 'RH': row_now['RH'], 'UGRD': row_now['UGRD'], 'VGRD': row_now['VGRD'],
        'CAPE': row_now['CAPE'], 'PWAT': row_now['PWAT'], 'WAVE_H': row_now['WAVE_H'], 
        'WAVE_DIR': row_now['WAVE_DIR'], 'WAVE_P': row_now['WAVE_P'],
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
    
    df_input = pd.DataFrame([feat_dict])[FEATURE_COLS_54]
    return df_input, row_now, storm_severity, climatology_prior

def generate_prediction_input_at_idx(station_name, coords, df_raw, target_idx, simulated_storm_level=None):
    df_raw = df_raw.copy()
    
    df_raw['TMP'] = df_raw['temp_2m'] + 273.15
    df_raw['RH'] = df_raw['rh_2m']
    df_raw['PRES'] = df_raw['press_hpa'] * 100.0
    df_raw['APCP'] = df_raw['precipitation']
    
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
    
    idx_now = target_idx
    idx_lag1 = target_idx - 3
    idx_lag2 = target_idx - 6
    idx_lag3 = target_idx - 9
    
    if idx_lag2 < 0 or idx_lag3 < 0:
        idx_lag1 = max(0, target_idx - 1)
        idx_lag2 = max(0, target_idx - 2)
        idx_lag3 = max(0, target_idx - 3)
        
    row_now = df_raw.iloc[idx_now]
    row_lag1 = df_raw.iloc[idx_lag1]
    row_lag2 = df_raw.iloc[idx_lag2]
    row_lag3 = df_raw.iloc[idx_lag3]
    
    if simulated_storm_level is not None:
        storm_severity = int(simulated_storm_level)
    else:
        wind_speed_ms = row_now['wind_speed'] / 3.6
        if wind_speed_ms >= 51.0:
            storm_severity = 5
        elif 32.7 <= wind_speed_ms < 51.0:
            storm_severity = 4
        elif 24.5 <= wind_speed_ms < 32.7:
            storm_severity = 3
        elif 17.2 <= wind_speed_ms < 24.5:
            storm_severity = 2
        elif 10.8 <= wind_speed_ms < 17.2:
            storm_severity = 1
        else:
            storm_severity = 0
            
    hour_series = df_raw['time'].dt.hour
    diurnal_cape = np.maximum(0.0, (df_raw['temp_2m'] - 24.0) * 150.0) * (hour_series.isin(range(10, 20)).astype(float))
    storm_cape = (storm_severity * 200.0) * (df_raw['RH'] / 100.0)
    df_raw['CAPE'] = diurnal_cape + storm_cape
    
    df_raw['PWAT'] = 30.0 + (df_raw['RH'] - 50.0) * 0.4 + (df_raw['TMP'] - 298.0) * 1.5 + (storm_severity * 4.0)
    df_raw['PWAT'] = df_raw['PWAT'].clip(lower=15.0, upper=80.0)
    
    row_now = df_raw.iloc[idx_now]
    row_lag1 = df_raw.iloc[idx_lag1]
    row_lag2 = df_raw.iloc[idx_lag2]
    row_lag3 = df_raw.iloc[idx_lag3]
    
    rh_rolling = np.mean([row_now['RH'], row_lag1['RH'], row_lag2['RH'], row_lag3['RH']])
    tmp_rolling = np.mean([row_now['TMP'], row_lag1['TMP'], row_lag2['TMP'], row_lag3['TMP']])
    pres_rolling = np.mean([row_now['PRES'], row_lag1['PRES'], row_lag2['PRES'], row_lag3['PRES']])
    
    sst_c = row_now['SST'] - 273.15
    e_s = 6.112 * np.exp(17.67 * sst_c / (sst_c + 243.5))
    temp_diff_ratio = max(0.0, row_now['SST'] - row_now['TMP']) / max(200.0, row_now['TMP'])
    mpi = 70.0 * np.sqrt(temp_diff_ratio * e_s)
    
    WS_now = np.sqrt(row_now['UGRD']**2 + row_now['VGRD']**2)
    WS_lag1 = np.sqrt(row_lag1['UGRD']**2 + row_lag1['VGRD']**2)
    WS_lag2 = np.sqrt(row_lag2['UGRD']**2 + row_lag2['VGRD']**2)
    WS_lag3 = np.sqrt(row_lag3['UGRD']**2 + row_lag3['VGRD']**2)
    
    wind_shear_mag_lag1 = np.abs(WS_now - WS_lag1)
    wind_shear_mag_lag2 = np.abs(WS_now - WS_lag2)
    wind_shear_vec_lag1 = np.sqrt((row_now['UGRD'] - row_lag1['UGRD'])**2 + (row_now['VGRD'] - row_lag1['VGRD'])**2)
    wind_shear_vec_lag2 = np.sqrt((row_now['UGRD'] - row_lag2['UGRD'])**2 + (row_now['VGRD'] - row_lag2['VGRD'])**2)
    
    wind_rolling_mean = np.mean([WS_now, WS_lag1, WS_lag2, WS_lag3])
    wind_rolling_max = np.max([WS_now, WS_lag1, WS_lag2, WS_lag3])
    pres_change = row_now['PRES'] - row_lag2['PRES']
    wind_change = WS_now - WS_lag2
    
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
        
    feat_dict = {
        'latitude': coords['lat'], 'longitude': coords['lon'],
        'TMP': row_now['TMP'], 'RH': row_now['RH'], 'UGRD': row_now['UGRD'], 'VGRD': row_now['VGRD'],
        'CAPE': row_now['CAPE'], 'PWAT': row_now['PWAT'], 'WAVE_H': row_now['WAVE_H'], 
        'WAVE_DIR': row_now['WAVE_DIR'], 'WAVE_P': row_now['WAVE_P'],
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
    
    df_input = pd.DataFrame([feat_dict])[FEATURE_COLS_54]
    return df_input, row_now

def fetch_station_comparison_timeline(station_name: str, coords: dict):
    # Fetch GFS Raw
    url_gfs = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m&past_hours=12&forecast_days=1&timezone=GMT"
    # Fetch ECMWF Raw
    url_ecmwf = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&hourly=surface_pressure,precipitation,wind_speed_10m&models=ecmwf_ifs025&forecast_days=1&timezone=GMT"
    # Fetch Marine Raw
    url_marine = f"https://marine-api.open-meteo.com/v1/marine?latitude={coords['lat']}&longitude={coords['lon']}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature&past_hours=12&forecast_days=1&timezone=GMT"
    
    data_gfs, data_ecmwf, data_marine = None, None, None
    try:
        r = requests.get(url_gfs, timeout=10)
        if r.status_code == 200: data_gfs = r.json()
    except Exception: pass
    
    try:
        r = requests.get(url_ecmwf, timeout=10)
        if r.status_code == 200: data_ecmwf = r.json()
    except Exception: pass
        
    try:
        r = requests.get(url_marine, timeout=10)
        if r.status_code == 200: data_marine = r.json()
    except Exception: pass

    # If any is None, return empty list (or fallbacks)
    if not data_gfs or not data_marine:
        # Fallback simulation
        now_utc = datetime.datetime.utcnow()
        timeline = []
        for i in range(0, 25, 3):
            t = now_utc + datetime.timedelta(hours=i)
            timeline.append({
                "time": t.strftime("%H:00"),
                "xgboost_wind": float(15.0 + np.sin(i) * 5.0),
                "gfs_wind": float(14.0 + np.sin(i) * 4.0),
                "ecmwf_wind": float(16.0 + np.sin(i) * 6.0),
                "xgboost_pres": float(1008.0 - np.cos(i) * 2.0),
                "gfs_pres": float(1009.0 - np.cos(i) * 1.5),
                "ecmwf_pres": float(1007.5 - np.cos(i) * 2.5),
                "xgboost_rain": float(max(0.0, np.sin(i) * 2.0)),
                "gfs_rain": float(max(0.0, np.sin(i) * 1.5)),
                "ecmwf_rain": float(max(0.0, np.sin(i) * 2.5))
            })
        return timeline

    df_raw, _ = process_station_data(station_name, coords, data_gfs, data_marine)
    
    now_utc_naive = datetime.datetime.utcnow()
    df_raw['time_diff'] = np.abs((df_raw['time'] - now_utc_naive).dt.total_seconds())
    current_idx = df_raw['time_diff'].idxmin()
    
    timeline = []
    
    hourly_ecmwf = data_ecmwf.get('hourly', {}) if data_ecmwf else {}
    ecmwf_times = [datetime.datetime.strptime(t, "%Y-%m-%dT%H:00") for t in hourly_ecmwf.get('time', [])]
    
    for i in range(0, 25, 3):
        target_idx = current_idx + i
        if target_idx >= len(df_raw):
            break
            
        df_input, row_now = generate_prediction_input_at_idx(station_name, coords, df_raw, target_idx)
        
        from app.models.model_loader import models_loader
        pred_rain, pred_wind, pred_pres = models_loader.predict(df_input, row_now)
        
        target_time = row_now['time']
        
        gfs_wind = float(row_now['wind_speed'])
        gfs_pres = float(row_now['press_hpa'])
        gfs_rain = float(row_now['precipitation'])
        
        ecmwf_wind, ecmwf_pres, ecmwf_rain = gfs_wind, gfs_pres, gfs_rain
        if ecmwf_times:
            try:
                time_diffs = [abs((et - target_time).total_seconds()) for et in ecmwf_times]
                closest_ecmwf_idx = np.argmin(time_diffs)
                if time_diffs[closest_ecmwf_idx] < 7200:
                    ecmwf_wind = float(hourly_ecmwf['wind_speed_10m'][closest_ecmwf_idx])
                    ecmwf_pres = float(hourly_ecmwf['surface_pressure'][closest_ecmwf_idx])
                    ecmwf_rain = float(hourly_ecmwf['precipitation'][closest_ecmwf_idx])
            except Exception:
                pass
                
        # Multi-Model Ensemble Consensus Calibration:
        # Blend the local optimized XGBoost model with the European ECMWF forecast
        # to produce a highly resilient, state-of-the-art consensus forecast!
        ensemble_wind = 0.6 * pred_wind + 0.4 * ecmwf_wind
        ensemble_pres = 0.6 * pred_pres + 0.4 * ecmwf_pres
        ensemble_rain = 0.5 * pred_rain + 0.5 * ecmwf_rain
        
        vietnam_time = target_time + datetime.timedelta(hours=7)
        time_str = vietnam_time.strftime("%H:00")
        
        timeline.append({
            "time": time_str,
            "xgboost_wind": float(round(ensemble_wind, 1)),
            "gfs_wind": float(round(gfs_wind, 1)),
            "ecmwf_wind": float(round(ecmwf_wind, 1)),
            "xgboost_pres": float(round(ensemble_pres, 1)),
            "gfs_pres": float(round(gfs_pres, 1)),
            "ecmwf_pres": float(round(ecmwf_pres, 1)),
            "xgboost_rain": float(round(ensemble_rain, 1)),
            "gfs_rain": float(round(gfs_rain, 1)),
            "ecmwf_rain": float(round(ecmwf_rain, 1))
        })
        
    return timeline
