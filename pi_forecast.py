import os
import sys
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_JSON = os.path.join(BASE_DIR, "xgboost_rain_model.json")

# Danh sách 8 trạm khí tượng tiêu biểu trên Biển Đông
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

# Các đặc trưng đầu vào theo đúng thứ tự huấn luyện của mô hình XGBoost
FEATURE_COLS = [
    'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 'is_storm',
    'TMP_lag1', 'TMP_lag2', 'RH_lag1', 'RH_lag2', 'UGRD_lag1', 'UGRD_lag2', 
    'VGRD_lag1', 'VGRD_lag2', 'CAPE_lag1', 'CAPE_lag2', 'PWAT_lag1', 'PWAT_lag2', 
    'APCP_lag1', 'APCP_lag2', 'RH_rolling_mean_12h', 'TMP_rolling_mean_12h', 'hour', 'month'
]

def fetch_station_api_data(lat, lon):
    """
    Tải dữ liệu thời tiết hiện tại và 12 giờ qua từ Open-Meteo API.
    """
    # past_hours=12 giúp lấy dữ liệu lịch sử gần để tính Lag và Rolling một cách chính xác
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m&past_hours=12&forecast_days=1&timezone=GMT"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Lỗi kết nối API Open-Meteo: {e}")
    return None

def compute_wind_components(speed_kmh, direction_deg):
    """Quy đổi hướng và tốc độ gió thành thành phần UGRD, VGRD (m/s) an toàn."""
    try:
        if pd.isna(speed_kmh) or pd.isna(direction_deg):
            return 0.0, 0.0
        speed_ms = float(speed_kmh) / 3.6
        rad = np.radians(float(direction_deg))
        u = -speed_ms * np.sin(rad)
        v = -speed_ms * np.cos(rad)
        return u, v
    except Exception:
        return 0.0, 0.0

def make_prediction_for_station(model, station_name, coords, is_storm_active):
    """
    Thu thập dữ liệu và dự đoán lượng mưa cho một trạm cụ thể.
    """
    data = fetch_station_api_data(coords['lat'], coords['lon'])
    if not data:
        return None
        
    hourly = data.get('hourly', {})
    
    # Ép kiểu dữ liệu an toàn tránh các lỗi định dạng không mong muốn
    df_raw = pd.DataFrame({
        'time': pd.to_datetime(hourly['time']),
        'temp_2m': pd.to_numeric(hourly['temperature_2m'], errors='coerce'),
        'rh_2m': pd.to_numeric(hourly['relative_humidity_2m'], errors='coerce'),
        'press_hpa': pd.to_numeric(hourly['surface_pressure'], errors='coerce'),
        'precipitation': pd.to_numeric(hourly['precipitation'], errors='coerce'),
        'wind_speed': pd.to_numeric(hourly['wind_speed_10m'], errors='coerce'),
        'wind_dir': pd.to_numeric(hourly['wind_direction_10m'], errors='coerce')
    })
    
    # Điền khuyết dữ liệu thời gian thực nếu có (bulletproof)
    for col in ['temp_2m', 'rh_2m', 'press_hpa', 'precipitation', 'wind_speed', 'wind_dir']:
        df_raw[col] = df_raw[col].ffill().bfill().fillna(0.0)
    
    # 1. Quy đổi vật lý giống GFS
    df_raw['TMP'] = df_raw['temp_2m'] + 273.15
    df_raw['RH'] = df_raw['rh_2m']
    df_raw['PRES'] = df_raw['press_hpa'] * 100.0
    df_raw['APCP'] = df_raw['precipitation']
    
    u_vals, v_vals = [], []
    for _, row in df_raw.iterrows():
        u, v = compute_wind_components(row['wind_speed'], row['wind_dir'])
        u_vals.append(u)
        v_vals.append(v)
    df_raw['UGRD'] = u_vals
    df_raw['VGRD'] = v_vals
    
    # Ước lượng CAPE và PWAT
    hour_series = df_raw['time'].dt.hour
    diurnal_cape = np.maximum(0.0, (df_raw['temp_2m'] - 24.0) * 150.0) * (hour_series.isin(range(10, 20)).astype(float))
    storm_cape = is_storm_active * 800.0 * (df_raw['RH'] / 100.0)
    df_raw['CAPE'] = diurnal_cape + storm_cape
    
    df_raw['PWAT'] = 30.0 + (df_raw['RH'] - 50.0) * 0.4 + (df_raw['TMP'] - 298.0) * 1.5 + is_storm_active * 15.0
    df_raw['PWAT'] = df_raw['PWAT'].clip(lower=15.0, upper=80.0)
    
    # 2. Định vị hàng hiện tại (sử dụng naive UTC datetime)
    now_utc_naive = datetime.datetime.utcnow()
    df_raw['time_diff'] = np.abs((df_raw['time'] - now_utc_naive).dt.total_seconds())
    current_idx = df_raw['time_diff'].idxmin()
    
    # Xác định các chỉ số dòng thời gian lùi (lùi 1 bước = 3 giờ, lùi 2 bước = 6 giờ)
    # Vì API trả về tần suất 1 giờ, lùi 3 bước = 3 giờ trước, lùi 6 bước = 6 giờ trước
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
    
    # Tính Rolling 12h (trung bình trượt của 4 mốc: hiện tại, -3h, -6h, -9h)
    rh_rolling = np.mean([row_now['RH'], row_lag1['RH'], row_lag2['RH'], row_lag3['RH']])
    tmp_rolling = np.mean([row_now['TMP'], row_lag1['TMP'], row_lag2['TMP'], row_lag3['TMP']])
    
    # 3. Tạo vector đặc trưng đầu vào (Input vector)
    feat_dict = {
        'latitude': coords['lat'],
        'longitude': coords['lon'],
        'TMP': row_now['TMP'],
        'RH': row_now['RH'],
        'UGRD': row_now['UGRD'],
        'VGRD': row_now['VGRD'],
        'CAPE': row_now['CAPE'],
        'PWAT': row_now['PWAT'],
        'PRES': row_now['PRES'],
        'is_storm': int(is_storm_active),
        'TMP_lag1': row_lag1['TMP'],
        'TMP_lag2': row_lag2['TMP'],
        'RH_lag1': row_lag1['RH'],
        'RH_lag2': row_lag2['RH'],
        'UGRD_lag1': row_lag1['UGRD'],
        'UGRD_lag2': row_lag2['UGRD'],
        'VGRD_lag1': row_lag1['VGRD'],
        'VGRD_lag2': row_lag2['VGRD'],
        'CAPE_lag1': row_lag1['CAPE'],
        'CAPE_lag2': row_lag2['CAPE'],
        'PWAT_lag1': row_lag1['PWAT'],
        'PWAT_lag2': row_lag2['PWAT'],
        'APCP_lag1': row_lag1['APCP'],
        'APCP_lag2': row_lag2['APCP'],
        'RH_rolling_mean_12h': rh_rolling,
        'TMP_rolling_mean_12h': tmp_rolling,
        'hour': row_now['time'].hour,
        'month': row_now['time'].month
    }
    
    # Chuyển thành DataFrame 1 hàng với các cột đúng thứ tự huấn luyện
    df_input = pd.DataFrame([feat_dict])[FEATURE_COLS]
    
    # Dự đoán lượng mưa
    pred_rain = float(model.predict(df_input)[0])
    
    return {
        'station_name': station_name,
        'time': row_now['time'].strftime("%Y-%m-%d %H:%M"),
        'temp': row_now['temp_2m'],
        'rh': row_now['rh_2m'],
        'wind_speed': row_now['wind_speed'],
        'press': row_now['press_hpa'],
        'pred_rain': max(0.0, pred_rain)
    }

def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi Lightweight Weather Predictor using XGBoost")
    parser.add_argument("--storm", action="store_true", help="Kích hoạt mô phỏng dự báo trong điều kiện BÃO hoạt động (is_storm=1)")
    args = parser.parse_args()

    print("\n=========================================================================")
    print("      RASPBERRY PI LIGHTWEIGHT FORECAST SYSTEM - BIỂN ĐÔNG REGION")
    print("=========================================================================")
    print(f"Thời gian chạy: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Trạng thái mô phỏng bão: {'[CẢNH BÁO BÃO]' if args.storm else '[BÌNH THƯỜNG]'}")

    # 1. Nạp mô hình XGBoost siêu nhẹ
    if not os.path.exists(MODEL_JSON):
        print(f"Lỗi: Không tìm thấy tệp mô hình tại {MODEL_JSON}!")
        print("Hãy đảm bảo bạn đã clone đầy đủ file xgboost_rain_model.json từ GitHub.")
        return

    try:
        model = XGBRegressor()
        model.load_model(MODEL_JSON)
    except Exception as e:
        print(f"Lỗi khi nạp mô hình: {e}")
        return

    # 2. Duyệt qua các trạm và dự báo
    results = []
    for name, coords in STATIONS.items():
        res = make_prediction_for_station(model, name, coords, args.storm)
        if res:
            results.append(res)
            
    if not results:
        print("Không thể lấy dữ liệu thời tiết thời gian thực cho bất kỳ trạm nào.")
        return

    # 3. Hiển thị bảng điều khiển dự báo cực đẹp
    print("\n+-----------------+-------------------+------------+----------+------------+--------------+------------------+")
    print("| Trạm Khí Tượng  | Thời Gian (UTC)   | Nhiệt Độ   | Độ Ẩm    | Tốc Độ Gió | Khí Áp (hPa) | DỰ BÁO MƯA (24h) |")
    print("+-----------------+-------------------+------------+----------+------------+--------------+------------------+")
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
            
        print(f"| {r['station_name']:<15} | {r['time']:<17} | {r['temp']:>7}°C | {r['rh']:>6}% | {r['wind_speed']:>6} km/h | {r['press']:>12.1f} | {rain_alert:<16} |")
    print("+-----------------+-------------------+------------+----------+------------+--------------+------------------+")
    print("Hệ thống dự báo Raspberry Pi hoàn thành nhiệm vụ thành công!\n")

if __name__ == "__main__":
    main()
