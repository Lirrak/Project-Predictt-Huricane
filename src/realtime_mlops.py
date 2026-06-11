import os
import sys
import time
import datetime
import numpy as np
import pandas as pd
import requests
import glob
import xarray as xr
import cfgrib
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Đảm bảo import được các module khác trong thư mục src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thư mục làm việc và đường dẫn tệp tin
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "data", "gfs_data")
EXTRACTED_CSV = os.path.join(BASE_DIR, "data", "extracted_weather.csv")
HISTORICAL_CSV = os.path.join(BASE_DIR, "data", "historical_storm_weather.csv")
FEATURES_CSV = os.path.join(BASE_DIR, "data", "engineered_features.csv")

# 3 file mô hình tương ứng với 3 chỉ số dự báo
MODEL_JSON_RAIN = os.path.join(BASE_DIR, "models", "xgboost_rain_model.json")
MODEL_JSON_WIND = os.path.join(BASE_DIR, "models", "xgboost_wind_model.json")
MODEL_JSON_PRES = os.path.join(BASE_DIR, "models", "xgboost_pres_model.json")

LOG_FILE = os.path.join(BASE_DIR, "logs", "mlops_training_log.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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

# --- Custom Loss Functions (Asymmetric Loss) áp đặt trọng số phạt lỗi underestimation cao gấp 5 lần ---
def apcp_asymmetric_obj(y_true, y_pred):
    """Custom Loss cho Lượng mưa (APCP): Phạt dự đoán thiếu gấp 5 lần khi trời mưa to."""
    if not isinstance(y_true, np.ndarray) and hasattr(y_true, 'get_label'):
        y_pred, dtrain = y_true, y_pred
        y_true = dtrain.get_label()
    residual = y_pred - y_true
    weight = np.where((residual < 0) & (y_true > 2.0), 5.0, 1.0)
    grad = residual * weight
    hess = weight
    return grad, hess

def wind_asymmetric_obj(y_true, y_pred):
    """Custom Loss cho Tốc độ gió: Phạt dự đoán thiếu gấp 5 lần khi gió mạnh bão."""
    if not isinstance(y_true, np.ndarray) and hasattr(y_true, 'get_label'):
        y_pred, dtrain = y_true, y_pred
        y_true = dtrain.get_label()
    residual = y_pred - y_true
    weight = np.where((residual < 0) & (y_true > 15.0), 5.0, 1.0)
    grad = residual * weight
    hess = weight
    return grad, hess

def pres_asymmetric_obj(y_true, y_pred):
    """Custom Loss cho Áp suất (PRES): Phạt dự báo áp quá cao (underestimate bão) gấp 5 lần."""
    if not isinstance(y_true, np.ndarray) and hasattr(y_true, 'get_label'):
        y_pred, dtrain = y_true, y_pred
        y_true = dtrain.get_label()
    residual = y_pred - y_true
    weight = np.where((residual > 0) & (y_true < 100000.0), 5.0, 1.0)
    grad = residual * weight
    hess = weight
    return grad, hess

def log_message(message):
    """Ghi log kèm theo timestamp ra màn hình và file log."""
    local_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"[{local_time}] {message}"
    print(full_message)
    sys.stdout.flush()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(full_message + "\n")
    except Exception as e:
        print(f"Không thể ghi file log: {e}")

def get_vietnam_time():
    """Lấy thời gian hiện tại ở Việt Nam (ICT, UTC+7)."""
    return datetime.datetime.now()

def download_grib_file(date_str, cycle_str):
    """Tải tệp GRIB2 từ NOAA NOMADS cho chu kỳ GFS cụ thể."""
    file_name = f"gfs.{date_str}_{cycle_str}.f000.grib2"
    file_path = os.path.join(DOWNLOAD_DIR, file_name)
    
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
        
    url = f"https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?file=gfs.t{cycle_str}z.pgrb2.0p25.f000&subregion=&leftlon=100&rightlon=125&toplat=25&bottomlat=0&dir=/gfs.{date_str}/{cycle_str}/atmos&lev_10_m_above_ground=on&lev_850_mb=on&lev_700_mb=on&lev_500_mb=on&lev_200_mb=on&lev_mean_sea_level=on&lev_surface=on&var_PRMSL=on&var_PRES=on&var_TMP=on&var_RH=on&var_UGRD=on&var_VGRD=on&var_GUST=on&var_CAPE=on&var_APCP=on&var_PWAT=on&var_ABSV=on"
    
    log_message(f"Đang thử tải chu kỳ {date_str} {cycle_str}z từ: {url[:120]}...")
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                f.write(response.content)
            log_message(f"Tải thành công: {file_name} ({os.path.getsize(file_path) / 1024:.1f} KB)")
            return file_path
        elif response.status_code == 404:
            return None
        else:
            log_message(f"Phản hồi từ NOAA không thành công (Status: {response.status_code}) cho {file_name}")
            return None
    except Exception as e:
        log_message(f"Lỗi kết nối khi tải {file_name}: {e}")
        return None

def fetch_multi_location_marine_for_date(date_str):
    """Tải dữ liệu sóng và hải lưu cho cả 37 trạm tại một ngày cụ thể."""
    lats = ",".join([str(STATIONS[name]["lat"]) for name in STATIONS])
    lons = ",".join([str(STATIONS[name]["lon"]) for name in STATIONS])
    url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}&start_date={date_str}&end_date={date_str}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def extract_all_stations_from_grib(file_path):
    """Trích xuất biến khí quyển cho cả 37 trạm từ tệp GRIB2."""
    try:
        datasets = cfgrib.open_datasets(file_path)
    except Exception as e:
        log_message(f"Lỗi khi mở GRIB {os.path.basename(file_path)}: {e}")
        return []

    records = []

    for station_name, coords in STATIONS.items():
        lat = coords['lat']
        lon = coords['lon']
        record = {
            'timestamp': None,
            'station_name': station_name,
            'latitude': lat,
            'longitude': lon,
            'TMP': np.nan, 'RH': np.nan, 'UGRD': np.nan, 'VGRD': np.nan,
            'CAPE': np.nan, 'PWAT': np.nan, 'APCP': np.nan, 'PRES': np.nan
        }

        for ds in datasets:
            try:
                ds_pixel = ds.sel(latitude=lat, longitude=lon, method='nearest')
            except Exception:
                continue

            if 'valid_time' in ds_pixel.coords and record['timestamp'] is None:
                val_time = ds_pixel.valid_time.values
                if isinstance(val_time, np.ndarray):
                    val_time = val_time.item() if val_time.size == 1 else val_time[0]
                record['timestamp'] = pd.to_datetime(val_time)

            if 'surface' in ds_pixel.coords or ds_pixel.attrs.get('GRIB_typeOfLevel') == 'surface':
                if 'cape' in ds_pixel: record['CAPE'] = float(ds_pixel['cape'].values)
                if 't' in ds_pixel: record['TMP'] = float(ds_pixel['t'].values)
                if 'sp' in ds_pixel: record['PRES'] = float(ds_pixel['sp'].values)
                if 'pwat' in ds_pixel: record['PWAT'] = float(ds_pixel['pwat'].values)
                if 'tp' in ds_pixel: record['APCP'] = float(ds_pixel['tp'].values)

            if 'heightAboveGround' in ds_pixel.coords:
                if 'u10' in ds_pixel: record['UGRD'] = float(ds_pixel['u10'].values)
                if 'v10' in ds_pixel: record['VGRD'] = float(ds_pixel['v10'].values)
                if 't2m' in ds_pixel or '2t' in ds_pixel:
                    t_var = '2t' if '2t' in ds_pixel else 't2m'
                    record['TMP'] = float(ds_pixel[t_var].values)

            if 'isobaricInhPa' in ds_pixel.coords:
                try:
                    ds_level = ds_pixel.sel(isobaricInhPa=850.0)
                except Exception:
                    ds_level = ds_pixel.isel(isobaricInhPa=0)
                    
                if 'r' in ds_level: record['RH'] = float(ds_level['r'].values)
                if 't' in ds_level and np.isnan(record['TMP']): record['TMP'] = float(ds_level['t'].values)
                if 'u' in ds_level and np.isnan(record['UGRD']): record['UGRD'] = float(ds_level['u'].values)
                if 'v' in ds_level and np.isnan(record['VGRD']): record['VGRD'] = float(ds_level['v'].values)

        records.append(record)

    for ds in datasets:
        ds.close()

    return records

def run_ml_pipeline():
    """Chạy toàn bộ pipeline MLOps tối ưu: Cửa sổ trượt 30 ngày + Lọc mẫu bão lịch sử, huấn luyện đa mục tiêu XGBoost giới hạn tài nguyên."""
    log_message("BẮT ĐẦU CHẠY PIPELINE HUẤN LUYỆN MÔ HÌNH HẢI DƯƠNG - KHÍ TƯỢNG ĐA TRẠM TỐI ƯU...")
    
    # --- BƯỚC 1: ĐỌC VÀ LỌC CỬA SỔ TRƯỢT 30 NGÀY DỮ LIỆU THỰC TẾ (Moving Window - Phương án 4) ---
    if not os.path.exists(EXTRACTED_CSV):
        log_message("Lỗi: Không tìm thấy tệp tin extracted_weather.csv!")
        return False
        
    df_real = pd.read_csv(EXTRACTED_CSV)
    df_real['timestamp'] = pd.to_datetime(df_real['timestamp'])
    
    # Chỉ giữ lại dữ liệu thực tế 30 ngày gần nhất để tiết kiệm bộ nhớ RAM cực lớn cho Pi
    cutoff_date = df_real['timestamp'].max() - pd.Timedelta(days=30)
    df_real_filtered = df_real[df_real['timestamp'] >= cutoff_date].copy()
    
    core_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 
                 'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity', 'APCP']
    df_real_filtered = df_real_filtered[core_cols]

    # --- BƯỚC 2: LỌC MẪU DỮ LIỆU BÃO LỊCH SỬ TINH GỌN (Storm Sampling - Phương án 4) ---
    if os.path.exists(HISTORICAL_CSV):
        df_hist = pd.read_csv(HISTORICAL_CSV)
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        df_hist = df_hist[core_cols]
        
        # Chỉ giữ lại các mẫu thực sự có bão/áp thấp (storm_severity > 0) và 10% ngẫu nhiên mẫu biển lặng làm phản ví dụ
        df_storms = df_hist[df_hist['storm_severity'] > 0]
        df_normals_sample = df_hist[df_hist['storm_severity'] == 0].sample(frac=0.10, random_state=42)
        df_hist_sampled = pd.concat([df_storms, df_normals_sample], ignore_index=True)
        
        # Hợp nhất dữ liệu
        df_combined = pd.concat([df_real_filtered, df_hist_sampled], ignore_index=True)
        log_message(f"Hợp nhất dữ liệu thành công: {len(df_real_filtered)} mẫu thực tế (30 ngày gần đây) và {len(df_hist_sampled)} mẫu bão lịch sử đã lọc.")
    else:
        df_combined = df_real_filtered.copy()

    # --- BƯỚC 3: THỰC HIỆN FEATURE ENGINEERING ĐẦY ĐỦ 54 ĐẶC TRƯNG ---
    df_combined = df_combined.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    df_combined['time_diff'] = df_combined.groupby('station_name')['timestamp'].diff()
    df_combined['is_new_period'] = (df_combined['time_diff'] > pd.Timedelta(hours=12)).fillna(False)
    df_combined['period_id'] = df_combined.groupby('station_name')['is_new_period'].cumsum()
    
    # 11 biến cốt lõi để tính Lag
    features_to_lag = ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'APCP', 'WAVE_H', 'CURRENT_VEL', 'SST', 'PRES']
    
    grouped = df_combined.groupby(['station_name', 'period_id'])
    for col in features_to_lag:
        df_combined[f'{col}_lag1'] = grouped[col].shift(1)
        df_combined[f'{col}_lag2'] = grouped[col].shift(2)
        
    df_combined['RH_rolling_mean_12h'] = grouped['RH'].transform(lambda x: x.rolling(window=4).mean())
    df_combined['TMP_rolling_mean_12h'] = grouped['TMP'].transform(lambda x: x.rolling(window=4).mean())
    df_combined['PRES_rolling_mean_12h'] = grouped['PRES'].transform(lambda x: x.rolling(window=4).mean())
    
    # Tính toán biến Sức gió tức thời và trễ
    df_combined['WIND_SPEED_temp'] = np.sqrt(df_combined['UGRD']**2 + df_combined['VGRD']**2)
    df_combined['WIND_SPEED_lag1'] = np.sqrt(df_combined['UGRD_lag1']**2 + df_combined['VGRD_lag1']**2)
    df_combined['WIND_SPEED_lag2'] = np.sqrt(df_combined['UGRD_lag2']**2 + df_combined['VGRD_lag2']**2)
    
    df_combined['WIND_rolling_mean_12h'] = grouped['WIND_SPEED_temp'].transform(lambda x: x.rolling(window=4).mean())
    df_combined['WIND_rolling_max_12h'] = grouped['WIND_SPEED_temp'].transform(lambda x: x.rolling(window=4).max())
    
    df_combined['PRES_change_6h'] = df_combined['PRES'] - df_combined['PRES_lag2']
    df_combined['WIND_change_6h'] = df_combined['WIND_SPEED_temp'] - df_combined['WIND_SPEED_lag2']
    df_combined.drop(columns=['WIND_SPEED_temp'], inplace=True, errors='ignore')
    
    df_combined['hour'] = df_combined['timestamp'].dt.hour
    df_combined['month'] = df_combined['timestamp'].dt.month
    
    # Tính các biến đặc trưng vật lý khí quyển - hải văn học nâng cao
    # 1. MPI (Maximum Potential Intensity)
    sst_c = df_combined['SST'] - 273.15
    e_s = 6.112 * np.exp(17.67 * sst_c / (sst_c + 243.5))
    temp_diff_ratio = (df_combined['SST'] - df_combined['TMP']).clip(lower=0.0) / df_combined['TMP'].clip(lower=200.0)
    df_combined['MPI'] = 70.0 * np.sqrt(temp_diff_ratio * e_s)
    
    # 2. Wind Shear (Độ đứt gió)
    WS = np.sqrt(df_combined['UGRD']**2 + df_combined['VGRD']**2)
    WS_lag1 = np.sqrt(df_combined['UGRD_lag1']**2 + df_combined['VGRD_lag1']**2)
    WS_lag2 = np.sqrt(df_combined['UGRD_lag2']**2 + df_combined['VGRD_lag2']**2)
    
    df_combined['wind_shear_mag_lag1'] = np.abs(WS - WS_lag1)
    df_combined['wind_shear_mag_lag2'] = np.abs(WS - WS_lag2)
    
    df_combined['wind_shear_vec_lag1'] = np.sqrt((df_combined['UGRD'] - df_combined['UGRD_lag1'])**2 + (df_combined['VGRD'] - df_combined['VGRD_lag1'])**2)
    df_combined['wind_shear_vec_lag2'] = np.sqrt((df_combined['UGRD'] - df_combined['UGRD_lag2'])**2 + (df_combined['VGRD'] - df_combined['VGRD_lag2'])**2)
    
    # 3. Climatology Prior
    default_priors = {1: 0.05, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.1, 6: 0.2, 
                      7: 0.4, 8: 0.5, 9: 0.6, 10: 0.5, 11: 0.3, 12: 0.1}
    df_combined['climatology_prior'] = df_combined['month'].map(default_priors).fillna(0.2)
    
    df_combined = df_combined.drop(columns=['period_id', 'time_diff', 'is_new_period'])
    df_clean = df_combined.dropna().reset_index(drop=True)
    
    df_clean.to_csv(FEATURES_CSV, index=False)
    log_message(f"Tính toán xong 54 đặc trưng. Tổng số dòng dữ liệu sạch đưa vào train: {len(df_clean)}")
    
    # Tính tốc độ gió WIND_SPEED để làm biến mục tiêu
    df_clean['WIND_SPEED'] = np.sqrt(df_clean['UGRD']**2 + df_clean['VGRD']**2)
    
    # Xác định các cột đầu vào bằng danh sách 54 đặc trưng khí quyển - hải dương học tối ưu
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
    
    target_cols = ['APCP', 'WIND_SPEED', 'PRES']
    X = df_clean[FEATURE_COLS_54]
    
    # Chia tập Train (80%) và Test (20%) ngẫu nhiên
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train_full, y_test_full = train_test_split(X, df_clean[target_cols], test_size=0.2, random_state=42, shuffle=True)
    
    # --- BƯỚC 4: HUẤN LUYỆN ĐA MỤC TIÊU VỚI GIỚI HẠN TÀI NGUYÊN (XGBoost n_jobs=2 - Phương án 6) ---
    log_message("\n--- KHỞI CHẠY HUẤN LUYỆN ĐA MỤC TIÊU CHO RASPBERRY PI (MAX 2 CPU) ---")
    
    # 1. Dự báo APCP (Mưa)
    log_message("[1/3] Đang huấn luyện mô hình dự báo lượng mưa APCP...")
    model_apcp = XGBRegressor(
        n_estimators=100, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.9, n_jobs=2, random_state=42, objective=apcp_asymmetric_obj
    )
    model_apcp.fit(X_train, y_train_full['APCP'], eval_set=[(X_test, y_test_full['APCP'])], verbose=False)
    y_pred_apcp = model_apcp.predict(X_test)
    mae_apcp = mean_absolute_error(y_test_full['APCP'], y_pred_apcp)
    
    # 2. Dự báo WIND_SPEED (Gió)
    log_message("[2/3] Đang huấn luyện mô hình dự báo tốc độ gió WIND_SPEED...")
    model_wind = XGBRegressor(
        n_estimators=100, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.9, n_jobs=2, random_state=42, objective=wind_asymmetric_obj
    )
    model_wind.fit(X_train, y_train_full['WIND_SPEED'], eval_set=[(X_test, y_test_full['WIND_SPEED'])], verbose=False)
    y_pred_wind = model_wind.predict(X_test)
    mae_wind = mean_absolute_error(y_test_full['WIND_SPEED'], y_pred_wind)

    # 3. Dự báo PRES (Khí áp)
    log_message("[3/3] Đang huấn luyện mô hình dự báo khí áp bề mặt PRES...")
    model_pres = XGBRegressor(
        n_estimators=100, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.9, n_jobs=2, random_state=42, objective=pres_asymmetric_obj
    )
    model_pres.fit(X_train, y_train_full['PRES'], eval_set=[(X_test, y_test_full['PRES'])], verbose=False)
    y_pred_pres = model_pres.predict(X_test)
    mae_pres = mean_absolute_error(y_test_full['PRES'], y_pred_pres)
    
    # Xuất tất cả các mô hình thành file JSON
    model_apcp.save_model(MODEL_JSON_RAIN)
    model_wind.save_model(MODEL_JSON_WIND)
    model_pres.save_model(MODEL_JSON_PRES)
    
    log_message(f"--- KẾT QUẢ HUẤN LUYỆN KHÍ TƯỢNG - HẢI DƯƠNG TRÊN PI CORES ---")
    log_message(f"  Số mẫu dữ liệu huấn luyện: {len(X_train)} | Tập kiểm thử: {len(X_test)}")
    log_message(f"  Sai số MAE Lượng mưa: {mae_apcp:.4f} mm")
    log_message(f"  Sai số MAE Tốc độ gió: {mae_wind:.4f} m/s")
    log_message(f"  Sai số MAE Khí áp: {mae_pres:.2f} Pa")
    log_message("  Đã lưu 3 tệp mô hình mới thành công tại thư mục models/!")
    
    # --- BƯỚC 5: TỰ ĐỘNG GỬI YÊU CẦU NẠP MÔ HÌNH LÊN FASTAPI BACKEND (Zero-Downtime Hot-Reload) ---
    try:
        reload_url = "http://localhost:8000/api/ml/reload"
        resp = requests.post(reload_url, timeout=5)
        if resp.status_code == 200:
            log_message("✅ Đã kích hoạt nạp lại mô hình tĩnh trực tiếp trên FastAPI Backend thành công!")
        else:
            log_message(f"⚠️ Không thể kích hoạt nạp lại mô hình. Backend phản hồi mã: {resp.status_code}")
    except Exception as e:
        log_message(f"❌ Lỗi khi gửi yêu cầu Hot-Reload đến Backend: {e}")
        
    # --- BƯỚC 6: TỰ ĐỘNG CHẠY KIỂM ĐỊNH ĐỂ CẬP NHẬT CHỈ SỐ LÊN FRONTEND ---
    try:
        log_message("Đang chạy kiểm định toàn diện để cập nhật chỉ số thực tế lên Dashboard...")
        from audit_model import run_audit
        run_audit()
        log_message("✅ Đã cập nhật tệp kết quả kiểm định data/audit_results.json thành công!")
    except Exception as e:
        log_message(f"⚠️ Lỗi khi chạy kiểm định mô hình tự động: {e}")
        
    return True

def main():
    log_message("=== KHỞI CHẠY HỆ THỐNG MLOPS KHÍ TƯỢNG - HẢI DƯƠNG ĐA TRẠM THỜI GIAN THỰC ===")
    log_message("Chế độ tối ưu hóa cực hạn cho Raspberry Pi 3 B+ (Tự động nạp mô hình không đổi link Cloudflare)")
    
    # Huấn luyện một lần khi khởi chạy hệ thống để kiểm tra và xác nhận mọi thứ hoạt động tốt
    try:
        run_ml_pipeline()
    except Exception as e:
        log_message(f"Lỗi khi huấn luyện ban đầu: {e}")
        
    last_trained_date = datetime.date.today()
    iteration = 1
    
    while True:
        current_time = get_vietnam_time()
        
        # Quét tìm các chu kỳ GFS khả dụng gần đây từ NOAA (UTC) để tải và làm giàu database
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        current_utc_hour = now_utc.hour
        latest_cycle_hour = (current_utc_hour // 6) * 6
        latest_cycle_dt = now_utc.replace(hour=latest_cycle_hour, minute=0, second=0, microsecond=0)
        
        cycle_candidates = []
        for i in range(6):
            dt = latest_cycle_dt - datetime.timedelta(hours=6*i)
            date_str = dt.strftime("%Y%m%d")
            cycle_str = dt.strftime("%H")
            cycle_candidates.append((date_str, cycle_str, dt))
            
        new_data_extracted = False
        
        for date_str, cycle_str, dt in cycle_candidates:
            file_name = f"gfs.{date_str}_{cycle_str}.f000.grib2"
            file_path = os.path.join(DOWNLOAD_DIR, file_name)
            
            if not os.path.exists(file_path):
                downloaded_path = download_grib_file(date_str, cycle_str)
                if downloaded_path:
                    log_message(f"Đang trích xuất dữ liệu đa trạm cho chu kỳ mới: {date_str} {cycle_str}z...")
                    station_records = extract_all_stations_from_grib(downloaded_path)
                    
                    if station_records:
                        # Đồng bộ hóa sóng biển và hải lưu trực tiếp tại ngày này từ Open-Meteo
                        marine_json = fetch_multi_location_marine_for_date(date_str)
                        
                        df_real = pd.read_csv(EXTRACTED_CSV)
                        df_real['timestamp'] = pd.to_datetime(df_real['timestamp'])
                        
                        new_rows = []
                        station_names = list(STATIONS.keys())
                        for rec in station_records:
                            if rec['timestamp'] is None:
                                continue
                            
                            # Điền khuyết cục bộ nếu thiếu APCP/PWAT
                            if np.isnan(rec['APCP']):
                                rh_val = rec['RH'] if not np.isnan(rec['RH']) else 75.0
                                cape_val = rec['CAPE'] if not np.isnan(rec['CAPE']) else 500.0
                                pres_val = rec['PRES'] if not np.isnan(rec['PRES']) else 100800.0
                                tmp_val = rec['TMP'] if not np.isnan(rec['TMP']) else 301.0
                                
                                rec['PWAT'] = 30.0 + (rh_val - 50.0) * 0.4 + (tmp_val - 298.0) * 1.5 + np.random.normal(0, 1.0)
                                rec['PWAT'] = np.clip(rec['PWAT'], 10.0, 80.0)
                                
                                if rh_val > 80.0:
                                    rec['APCP'] = max(0.0, (rh_val - 80.0) * 0.3 + (cape_val / 400.0) + max(0.0, (101100.0 - pres_val) / 50.0) + np.random.normal(0, 0.5))
                                else:
                                    rec['APCP'] = 0.0
                            
                            # Tính storm_severity dựa trên UGRD và VGRD theo tốc độ gió (chuẩn Việt Nam/Biển Đông)
                            wind_speed_ms = np.sqrt(rec['UGRD']**2 + rec['VGRD']**2)
                            
                            if wind_speed_ms >= 51.0:
                                rec['storm_severity'] = 5  # Siêu bão
                            elif 32.7 <= wind_speed_ms < 51.0:
                                rec['storm_severity'] = 4  # Bão rất mạnh
                            elif 24.5 <= wind_speed_ms < 32.7:
                                rec['storm_severity'] = 3  # Bão mạnh
                            elif 17.2 <= wind_speed_ms < 24.5:
                                rec['storm_severity'] = 2  # Bão thường
                            elif 10.8 <= wind_speed_ms < 17.2:
                                rec['storm_severity'] = 1  # Áp thấp nhiệt đới
                            else:
                                rec['storm_severity'] = 0
                                
                            # Thiết lập giá trị mặc định cho hải dương
                            rec['WAVE_H'] = 1.0
                            rec['WAVE_DIR'] = 180.0
                            rec['WAVE_P'] = 5.0
                            rec['CURRENT_VEL'] = 0.2
                            rec['CURRENT_DIR'] = 180.0
                            rec['SST'] = rec['TMP']
                            
                            # Khớp dữ liệu hải dương thời gian thực từ Open-Meteo
                            if marine_json:
                                try:
                                    st_idx = station_names.index(rec['station_name'])
                                    hourly_m = marine_json[st_idx].get('hourly', {})
                                    time_list = [datetime.datetime.strptime(t, "%Y-%m-%dT%H:00") for t in hourly_m['time']]
                                    target_dt = datetime.datetime.combine(rec['timestamp'].date(), datetime.time(rec['timestamp'].hour, 0))
                                    time_idx = time_list.index(target_dt)
                                    
                                    rec['WAVE_H'] = float(hourly_m['wave_height'][time_idx])
                                    rec['WAVE_DIR'] = float(hourly_m['wave_direction'][time_idx])
                                    rec['WAVE_P'] = float(hourly_m['wave_period'][time_idx])
                                    rec['CURRENT_VEL'] = float(hourly_m['ocean_current_velocity'][time_idx])
                                    rec['CURRENT_DIR'] = float(hourly_m['ocean_current_direction'][time_idx])
                                    rec['SST'] = float(hourly_m['sea_surface_temperature'][time_idx]) + 273.15
                                except Exception:
                                    pass
                                    
                            new_rows.append({
                                'timestamp': rec['timestamp'],
                                'station_name': rec['station_name'],
                                'latitude': rec['latitude'],
                                'longitude': rec['longitude'],
                                'TMP': rec['TMP'],
                                'RH': rec['RH'],
                                'UGRD': rec['UGRD'],
                                'VGRD': rec['VGRD'],
                                'CAPE': rec['CAPE'],
                                'PWAT': rec['PWAT'],
                                'PRES': rec['PRES'],
                                'WAVE_H': rec['WAVE_H'],
                                'WAVE_DIR': rec['WAVE_DIR'],
                                'WAVE_P': rec['WAVE_P'],
                                'CURRENT_VEL': rec['CURRENT_VEL'],
                                'CURRENT_DIR': rec['CURRENT_DIR'],
                                'SST': rec['SST'],
                                'storm_severity': rec['storm_severity'],
                                'file_name': file_name
                            })
                            
                        df_new = pd.DataFrame(new_rows)
                        df_merged = pd.concat([df_real, df_new], ignore_index=True)
                        df_merged['timestamp'] = pd.to_datetime(df_merged['timestamp'])
                        # Loại bỏ trùng lặp dựa trên cả thời gian và trạm
                        df_merged = df_merged.drop_duplicates(subset=['timestamp', 'station_name'], keep='last')
                        df_merged = df_merged.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
                        
                        df_merged.to_csv(EXTRACTED_CSV, index=False)
                        log_message(f"Đã tải, đồng bộ và hợp nhất thành công dữ liệu đa trạm chu kỳ GFS {date_str}_{cycle_str}!")
                        new_data_extracted = True
        
        # --- BƯỚC 6: KIỂM TRA ĐIỀU KIỆN KÍCH HOẠT HUẤN LUYỆN BAN ĐÊM (Phương án 6 - 3:00 AM) ---
        # Chỉ chạy huấn luyện nếu thời gian hiện tại là 3 giờ sáng (3:00 AM - 3:59 AM) và chưa chạy huấn luyện nào trong hôm nay
        if current_time.hour == 3 and current_time.date() != last_trained_date:
            log_message(f"⏰ Đã đến mốc 3:00 AM ban đêm. Kích hoạt huấn luyện MLOps hàng ngày tự động...")
            try:
                run_ml_pipeline()
                last_trained_date = current_time.date()
            except Exception as e:
                log_message(f"Lỗi khi huấn luyện lại mô hình ban đêm: {e}")
                
        # Ngủ 15 phút trước chu kỳ quét dữ liệu NOAA tiếp theo
        time.sleep(900)
        iteration += 1

if __name__ == "__main__":
    main()
