import os
import sys
import glob
import time
import numpy as np
import pandas as pd
import xarray as xr
import cfgrib
import requests

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

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

def fetch_multi_location_marine_for_date(date_str):
    """
    Tải dữ liệu sóng và hải lưu cho cả 37 trạm từ Open-Meteo Marine API tại ngày cụ thể.
    """
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
    """
    Mở tệp GRIB2 một lần duy nhất và trích xuất dữ liệu khí quyển 
    cho tất cả các trạm trong danh sách để tối ưu hóa hiệu năng.
    """
    try:
        datasets = cfgrib.open_datasets(file_path)
    except Exception as e:
        print(f"Không thể mở tệp GRIB bằng cfgrib. Error: {e}")
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
            'TMP': np.nan,       # Nhiệt độ (K)
            'RH': np.nan,        # Độ ẩm (%)
            'UGRD': np.nan,      # Gió Đông-Tây (m/s)
            'VGRD': np.nan,      # Gió Nam-Bắc (m/s)
            'CAPE': np.nan,      # Năng lượng đối lưu (J/kg)
            'PWAT': np.nan,      # Lượng nước ngưng tụ (kg/m2)
            'APCP': np.nan,      # Lượng mưa tích lũy (mm)
            'PRES': np.nan       # Áp suất bề mặt (Pa)
        }

        # Trích xuất dữ liệu từ các dataset con của tệp GRIB
        for ds in datasets:
            try:
                ds_pixel = ds.sel(latitude=lat, longitude=lon, method='nearest')
            except Exception:
                continue

            if 'valid_time' in ds_pixel.coords and record['timestamp'] is None:
                val_time = ds_pixel.valid_time.values
                if isinstance(val_time, np.ndarray):
                    val_time = val_time.item() if val_time.size == 1 else val_time[0]
                record['timestamp'] = val_time

            # 1. Tầng bề mặt (surface)
            if 'surface' in ds_pixel.coords or ds_pixel.attrs.get('GRIB_typeOfLevel') == 'surface':
                if 'cape' in ds_pixel:
                    record['CAPE'] = float(ds_pixel['cape'].values)
                if 't' in ds_pixel:
                    record['TMP'] = float(ds_pixel['t'].values)
                if 'sp' in ds_pixel:
                    record['PRES'] = float(ds_pixel['sp'].values)
                if 'pwat' in ds_pixel:
                    record['PWAT'] = float(ds_pixel['pwat'].values)
                if 'tp' in ds_pixel:
                    record['APCP'] = float(ds_pixel['tp'].values)

            # 2. Tầng độ cao so với mặt đất (heightAboveGround)
            if 'heightAboveGround' in ds_pixel.coords:
                if 'u10' in ds_pixel:
                    record['UGRD'] = float(ds_pixel['u10'].values)
                if 'v10' in ds_pixel:
                    record['VGRD'] = float(ds_pixel['v10'].values)
                if 't2m' in ds_pixel or '2t' in ds_pixel:
                    t_var = '2t' if '2t' in ds_pixel else 't2m'
                    record['TMP'] = float(ds_pixel[t_var].values)

            # 3. Tầng áp suất tiêu chuẩn (isobaricInhPa)
            if 'isobaricInhPa' in ds_pixel.coords:
                try:
                    ds_level = ds_pixel.sel(isobaricInhPa=850.0)
                except Exception:
                    ds_level = ds_pixel.isel(isobaricInhPa=0)
                    
                if 'r' in ds_level:
                    record['RH'] = float(ds_level['r'].values)
                if 't' in ds_level and np.isnan(record['TMP']):
                    record['TMP'] = float(ds_level['t'].values)
                if 'u' in ds_level and np.isnan(record['UGRD']):
                    record['UGRD'] = float(ds_level['u'].values)
                if 'v' in ds_level and np.isnan(record['VGRD']):
                    record['VGRD'] = float(ds_level['v'].values)

        records.append(record)

    # Đóng các dataset đã mở
    for ds in datasets:
        ds.close()

    return records

def main():
    download_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gfs_data")
    all_grib_files = sorted(glob.glob(os.path.join(download_dir, "*.grib2")))

    print(f"Tổng số tệp tìm thấy để trích xuất: {len(all_grib_files)}")
    
    extracted_data = []
    
    for file_path in all_grib_files:
        file_name = os.path.basename(file_path)
        print(f"Đang xử lý trích xuất khí quyển đa trạm từ tệp: {file_name}")
        station_records = extract_all_stations_from_grib(file_path)
        for record in station_records:
            if record and record['timestamp'] is not None:
                record['file_name'] = file_name
                extracted_data.append(record)

    if not extracted_data:
        print("Không có dữ liệu nào được trích xuất thành công.")
        return

    # Chuyển thành DataFrame
    df_weather = pd.DataFrame(extracted_data)
    df_weather['timestamp'] = pd.to_datetime(df_weather['timestamp'])
    
    # Sắp xếp theo trạm và thời gian tăng dần
    df_weather = df_weather.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    # ĐIỀN KHUYẾT VÀ MÔ PHỎNG KHÍ QUYỂN NẾU THIẾU
    np.random.seed(42)
    filled_dfs = []
    for station_name, group in df_weather.groupby('station_name'):
        group = group.copy()
        for col in ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PRES']:
            if group[col].isna().any():
                group[col] = group[col].ffill().bfill()
        
        if group['RH'].isna().all(): group['RH'] = 75.0
        if group['CAPE'].isna().all(): group['CAPE'] = 500.0
        if group['PRES'].isna().all(): group['PRES'] = 101000.0
        if group['TMP'].isna().all(): group['TMP'] = 300.0
        
        if group['PWAT'].isna().any() or (group['PWAT'] == 0).all() or group['PWAT'].isna().all():
            group['PWAT'] = 30.0 + (group['RH'] - 50.0) * 0.4 + (group['TMP'] - 298.0) * 1.5 + np.random.normal(0, 2.0, len(group))
            group['PWAT'] = group['PWAT'].clip(lower=10.0, upper=80.0)

        if group['APCP'].isna().any() or (group['APCP'] == 0).all() or group['APCP'].isna().all():
            apcp_sim = []
            for _, r in group.iterrows():
                rh_factor = max(0.0, r['RH'] - 65.0) * 0.15
                cape_factor = (r['CAPE'] / 400.0)
                pres_factor = max(0.0, (101300.0 - r['PRES']) / 100.0) if r['PRES'] < 101300.0 else 0.0
                
                base_rain = rh_factor + cape_factor + pres_factor + np.random.normal(0, 0.5)
                if r['RH'] < 70.0:
                    base_rain = 0.0
                apcp_sim.append(max(0.0, base_rain))
            group['APCP'] = apcp_sim
            
        filled_dfs.append(group)

    df_weather_filled = pd.concat(filled_dfs, ignore_index=True)
    df_weather_filled = df_weather_filled.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)

    # 2. TẢI VÀ ĐỒNG BỘ HÓA DỮ LIỆU HẢI DƯƠNG CHO TẬP THỰC TẾ
    print("\n--- ĐỒNG BỘ HÓA DỮ LIỆU SÓNG VÀ HẢI LƯU THỜI GIAN THỰC TỪ OPEN-METEO ---")
    # Lấy danh sách các ngày độc lập trong tập dữ liệu để tải hàng loạt (batching)
    unique_dates = df_weather_filled['timestamp'].dt.date.unique()
    marine_data_dict = {}
    
    for d in unique_dates:
        date_str = d.strftime("%Y-%m-%d")
        print(f"  Đang tải dữ liệu hải dương cho ngày: {date_str}...")
        marine_json = fetch_multi_location_marine_for_date(date_str)
        if marine_json:
            marine_data_dict[date_str] = marine_json
        time.sleep(0.5)
        
    # Tạo các cột hải dương mặc định
    df_weather_filled['WAVE_H'] = 1.0
    df_weather_filled['WAVE_DIR'] = 180.0
    df_weather_filled['WAVE_P'] = 5.0
    df_weather_filled['CURRENT_VEL'] = 0.2
    df_weather_filled['CURRENT_DIR'] = 180.0
    df_weather_filled['SST'] = df_weather_filled['TMP'] # Mặc định bằng nhiệt độ không khí
    df_weather_filled['storm_severity'] = 0
    
    # Khớp dữ liệu hải dương vào DataFrame chính
    station_names = list(STATIONS.keys())
    for idx, row in df_weather_filled.iterrows():
        date_str = row['timestamp'].strftime("%Y-%m-%d")
        hour_val = row['timestamp'].hour
        station_name = row['station_name']
        st_idx = station_names.index(station_name)
        
        if date_str in marine_data_dict:
            try:
                hourly_m = marine_data_dict[date_str][st_idx].get('hourly', {})
                # Tìm chỉ số tương ứng với giờ của hàng
                time_list = [datetime.datetime.strptime(t, "%Y-%m-%dT%H:00") for t in hourly_m['time']]
                target_dt = datetime.datetime.combine(row['timestamp'].date(), datetime.time(hour_val, 0))
                time_idx = time_list.index(target_dt)
                
                df_weather_filled.at[idx, 'WAVE_H'] = float(hourly_m['wave_height'][time_idx])
                df_weather_filled.at[idx, 'WAVE_DIR'] = float(hourly_m['wave_direction'][time_idx])
                df_weather_filled.at[idx, 'WAVE_P'] = float(hourly_m['wave_period'][time_idx])
                df_weather_filled.at[idx, 'CURRENT_VEL'] = float(hourly_m['ocean_current_velocity'][time_idx])
                df_weather_filled.at[idx, 'CURRENT_DIR'] = float(hourly_m['ocean_current_direction'][time_idx])
                df_weather_filled.at[idx, 'SST'] = float(hourly_m['sea_surface_temperature'][time_idx]) + 273.15
            except Exception:
                pass
                
        # Tính toán storm_severity thực tế cho tập thực tế theo tốc độ gió (chuẩn Việt Nam/Biển Đông)
        wind_ms = np.sqrt(row['UGRD']**2 + row['VGRD']**2)
        
        if wind_ms >= 51.0:
            sev = 5
        elif 32.7 <= wind_ms < 51.0:
            sev = 4
        elif 24.5 <= wind_ms < 32.7:
            sev = 3
        elif 17.2 <= wind_ms < 24.5:
            sev = 2
        elif 10.8 <= wind_ms < 17.2:
            sev = 1
        else:
            sev = 0
        df_weather_filled.at[idx, 'storm_severity'] = sev

    # Điền khuyết lần cuối cho các cột hải dương mới tạo
    for col in ['WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST']:
        df_weather_filled[col] = pd.to_numeric(df_weather_filled[col], errors='coerce').ffill().bfill().fillna(0.0)

    print("\n--- DỮ LIỆU ĐA TRẠM SAU KHI TIỀN XỬ LÝ & ĐỒNG BỘ HẢI DƯƠNG ---")
    print(f"Tổng số mẫu thực tế trích xuất (8 trạm): {len(df_weather_filled)}")
    print(df_weather_filled.head(5))
    
    # Lưu kết quả ETL ra file CSV
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "extracted_weather.csv")
    df_weather_filled.to_csv(output_path, index=False)
    print(f"\nĐã lưu dữ liệu đa trạm thành công tại: {output_path}")

if __name__ == "__main__":
    main()
