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

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thư mục làm việc và đường dẫn tệp tin
BASE_DIR = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane"
DOWNLOAD_DIR = os.path.join(BASE_DIR, "gfs_data")
EXTRACTED_CSV = os.path.join(BASE_DIR, "extracted_weather.csv")
HISTORICAL_CSV = os.path.join(BASE_DIR, "historical_storm_weather.csv")
FEATURES_CSV = os.path.join(BASE_DIR, "engineered_features.csv")
MODEL_JSON = os.path.join(BASE_DIR, "xgboost_rain_model.json")
LOG_FILE = os.path.join(BASE_DIR, "mlops_training_log.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Danh sách 8 trạm khí tượng bao phủ toàn Biển Đông
STATIONS = {
    "Bach Long Vi": {"lat": 20.13, "lon": 107.73},
    "Hoang Sa": {"lat": 16.54, "lon": 111.61},
    "Ly Son": {"lat": 15.38, "lon": 109.15},
    "Song Tu Tay": {"lat": 11.43, "lon": 114.33},
    "Phu Quy": {"lat": 10.52, "lon": 108.94},
    "Truong Sa Lon": {"lat": 8.65, "lon": 111.92},
    "Con Dao": {"lat": 8.68, "lon": 106.60},
    "Huyen Tran": {"lat": 8.15, "lon": 110.63}
}

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
    """Tải dữ liệu sóng và hải lưu cho cả 8 trạm tại một ngày cụ thể."""
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
    """Trích xuất biến khí quyển cho cả 8 trạm từ tệp GRIB2."""
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
    """Chạy toàn bộ pipeline MLOps kết hợp Khí tượng - Hải dương 38 đặc trưng."""
    log_message("BẮT ĐẦU CHẠY PIPELINE HUẤN LUYỆN MÔ HÌNH HẢI DƯƠNG - KHÍ TƯỢNG ĐA TRẠM...")
    
    # 1. Đọc dữ liệu thực tế GFS đa trạm
    if not os.path.exists(EXTRACTED_CSV):
        log_message("Lỗi: Không tìm thấy tệp tin extracted_weather.csv!")
        return False
        
    df_real = pd.read_csv(EXTRACTED_CSV)
    df_real['timestamp'] = pd.to_datetime(df_real['timestamp'])
    
    core_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 
                 'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity', 'APCP']
    df_real = df_real[core_cols]

    # 2. Đọc dữ liệu lịch sử bão đa trạm
    if os.path.exists(HISTORICAL_CSV):
        df_hist = pd.read_csv(HISTORICAL_CSV)
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        df_hist = df_hist[core_cols]
        df_combined = pd.concat([df_real, df_hist], ignore_index=True)
    else:
        df_combined = df_real.copy()

    # 3. Thực hiện Feature Engineering đa trạm theo phân đoạn độc lập bằng phương pháp vector hóa siêu nhanh
    df_combined = df_combined.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    df_combined['time_diff'] = df_combined.groupby('station_name')['timestamp'].diff()
    df_combined['is_new_period'] = (df_combined['time_diff'] > pd.Timedelta(hours=12)).fillna(False)
    df_combined['period_id'] = df_combined.groupby('station_name')['is_new_period'].cumsum()
    
    # Tính trễ cho cả Chiều cao sóng và Tốc độ hải lưu
    features_to_lag = ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'APCP', 'WAVE_H', 'CURRENT_VEL']
    
    # Sử dụng groupby trực tiếp và vectorized shift/transform để tăng tốc độ xử lý gấp 100 lần
    grouped = df_combined.groupby(['station_name', 'period_id'])
    for col in features_to_lag:
        df_combined[f'{col}_lag1'] = grouped[col].shift(1)
        df_combined[f'{col}_lag2'] = grouped[col].shift(2)
        
    df_combined['RH_rolling_mean_12h'] = grouped['RH'].transform(lambda x: x.rolling(window=4).mean())
    df_combined['TMP_rolling_mean_12h'] = grouped['TMP'].transform(lambda x: x.rolling(window=4).mean())
    
    df_combined['hour'] = df_combined['timestamp'].dt.hour
    df_combined['month'] = df_combined['timestamp'].dt.month
    df_combined = df_combined.drop(columns=['period_id', 'time_diff', 'is_new_period'])
    df_clean = df_combined.dropna().reset_index(drop=True)
    
    df_clean.to_csv(FEATURES_CSV, index=False)
    
    # 4. Huấn luyện XGBoost sử dụng đa nhân CPU (n_jobs=-1) để hoàn thành trong vài giây
    target_col = 'APCP'
    feature_cols = [col for col in df_clean.columns if col not in [target_col, 'timestamp', 'station_name']]

    X = df_clean[feature_cols]
    y = df_clean[target_col]

    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    model = XGBRegressor(
        n_estimators=150, learning_rate=0.03, max_depth=7, subsample=0.8, colsample_bytree=0.9, n_jobs=-1, random_state=42
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    # Đánh giá sai số
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    
    # Xuất mô hình
    model.save_model(MODEL_JSON)
    
    log_message(f"--- KẾT QUẢ HUẤN LUYỆN KHÍ TƯỢNG - HẢI DƯƠNG ---")
    log_message(f"  Số mẫu dữ liệu huấn luyện: {len(X_train)} | Tập kiểm thử: {len(X_test)}")
    log_message(f"  Sai số MAE: {mae:.4f} mm")
    log_message(f"  Sai số RMSE: {rmse:.4f} mm")
    log_message(f"  Mô hình 38 đặc trưng đã được cập nhật thành công tại: {MODEL_JSON}")
    return True

def main():
    log_message("=== KHỞI CHẠY HỆ THỐNG MLOPS KHÍ TƯỢNG - HẢI DƯƠNG ĐA TRẠM THỜI GIAN THỰC ===")
    log_message(f"Hệ thống sẽ chạy liên tục từ bây giờ cho đến 12:00 PM trưa ngày 05/06/2026.")
    
    target_end_time = datetime.datetime(2026, 6, 5, 12, 0, 0)
    
    iteration = 1
    
    while True:
        current_time = get_vietnam_time()
        if current_time >= target_end_time:
            log_message(f"Thời gian hiện tại ({current_time.strftime('%Y-%m-%d %H:%M:%S')}) đã vượt quá mốc 12:00 PM. Kết thúc quá trình huấn luyện.")
            break
            
        remaining_time = target_end_time - current_time
        log_message(f"\n[Chu kỳ #{iteration}] Thời gian: {current_time.strftime('%Y-%m-%d %H:%M:%S')} (Còn lại: {remaining_time})")
        
        # 1. Quét tìm các chu kỳ GFS khả dụng gần đây từ NOAA (UTC)
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
                        # 2. Đồng bộ hóa sóng biển và hải lưu trực tiếp tại ngày này
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
                            
                            # Tính storm_severity dựa trên UGRD, VGRD và PRES (áp suất)
                            wind_speed_ms = np.sqrt(rec['UGRD']**2 + rec['VGRD']**2)
                            pres_pa = rec['PRES']
                            
                            if wind_speed_ms >= 32.7 or pres_pa < 96000.0:
                                rec['storm_severity'] = 4  # Siêu bão
                            elif 24.5 <= wind_speed_ms < 32.7 or 96000.0 <= pres_pa < 99000.0:
                                rec['storm_severity'] = 3  # Bão mạnh
                            elif 17.2 <= wind_speed_ms < 24.5 or 99000.0 <= pres_pa < 100000.0:
                                rec['storm_severity'] = 2  # Bão nhiệt đới thường
                            elif 10.8 <= wind_speed_ms < 17.2 or 100000.0 <= pres_pa < 100800.0:
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
                        log_message(f"Đã thêm, đồng bộ hải dương và hợp nhất thành công dữ liệu đa trạm của chu kỳ {date_str}_{cycle_str}!")
                        new_data_extracted = True
        
        if new_data_extracted or iteration == 1:
            try:
                run_ml_pipeline()
            except Exception as e:
                log_message(f"Lỗi khi huấn luyện lại mô hình đa trạm: {e}")
        else:
            log_message("Không phát hiện thêm chu kỳ dữ liệu GFS mới từ NOAA. Bỏ qua huấn luyện chu kỳ này.")
            
        log_message("Hệ thống chuyển sang chế độ ngủ trong 15 phút...")
        sys.stdout.flush()
        
        sleep_duration = 900
        sleep_step = 15
        steps = sleep_duration // sleep_step
        for _ in range(steps):
            time.sleep(sleep_step)
            if get_vietnam_time() >= target_end_time:
                break
                
        iteration += 1

if __name__ == "__main__":
    main()
