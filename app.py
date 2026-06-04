import os
import sys
import time
import datetime
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from xgboost import XGBRegressor

# Cấu hình giao diện Streamlit
st.set_page_config(
    page_title="Biển Đông Forecast Dashboard",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Thư mục gốc dự án và tệp mô hình
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_JSON = os.path.join(BASE_DIR, "xgboost_rain_model.json")

# Danh sách 8 trạm khí tượng bao phủ Biển Đông
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

FEATURE_COLS = [
    'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 'WAVE_H', 'WAVE_DIR', 'WAVE_P',
    'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity',
    'TMP_lag1', 'TMP_lag2', 'RH_lag1', 'RH_lag2', 'UGRD_lag1', 'UGRD_lag2', 
    'VGRD_lag1', 'VGRD_lag2', 'CAPE_lag1', 'CAPE_lag2', 'PWAT_lag1', 'PWAT_lag2', 
    'APCP_lag1', 'APCP_lag2', 'WAVE_H_lag1', 'WAVE_H_lag2', 'CURRENT_VEL_lag1', 'CURRENT_VEL_lag2',
    'RH_rolling_mean_12h', 'TMP_rolling_mean_12h', 'hour', 'month'
]

SEVERITY_NAMES = {
    0: "Bình thường",
    1: "Áp thấp n.đới",
    2: "Bão thường",
    3: "Bão mạnh",
    4: "Siêu bão"
}

SEVERITY_COLORS = {
    0: "#2ecc71",  # Xanh lá
    1: "#3498db",  # Xanh dương
    2: "#f1c40f",  # Vàng
    3: "#e67e22",  # Cam
    4: "#e74c3c"   # Đỏ
}

# --- CÁC HÀM LẤY DỮ LIỆU & DỰ BÁO (Tương thích hoàn toàn với pi_forecast.py) ---

@st.cache_data(ttl=600)  # Cache kết quả gọi API trong 10 phút
def fetch_weather_and_marine_data(lat, lon, station_name, simulated_storm_level=None):
    """
    Tải dữ liệu thời tiết và hải dương từ Open-Meteo.
    Nếu lỗi kết nối, tự động chuyển sang chế độ dự phòng ngoại tuyến phù hợp vật lý.
    """
    err_w, err_m = False, False
    
    # 1. Gọi API khí quyển
    url_w = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m,surface_pressure,precipitation,wind_speed_10m,wind_direction_10m&past_hours=12&forecast_days=1&timezone=GMT"
    try:
        r = requests.get(url_w, timeout=5)
        if r.status_code == 200:
            data_w = r.json()
        else:
            err_w = True
    except Exception:
        err_w = True

    # 2. Gọi API hải dương
    url_m = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction,sea_surface_temperature&past_hours=12&forecast_days=1&timezone=GMT"
    try:
        r = requests.get(url_m, timeout=5)
        if r.status_code == 200:
            data_m = r.json()
        else:
            err_m = True
    except Exception:
        err_m = True

    is_fallback = err_w or err_m
    
    if is_fallback:
        # Chế độ dự phòng ngoại tuyến
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
        
        # Mô phỏng bão
        if simulated_storm_level is not None and simulated_storm_level > 0:
            sev = simulated_storm_level
            hourly_w['wind_speed_10m'] = [20.0 + sev * 15.0 + np.random.uniform(0, 5.0) for _ in times]
            hourly_w['surface_pressure'] = [1005.0 - sev * 12.0 + np.sin(4*np.pi*t.hour/24)*1.0 for t in times]
            hourly_m['wave_height'] = [1.2 + sev * 2.1 + np.random.uniform(0, 0.5) for _ in times]
            hourly_m['wave_period'] = [5.0 + sev * 1.5 for _ in times]
            hourly_m['ocean_current_velocity'] = [0.2 + sev * 0.28 for _ in times]
            hourly_m['sea_surface_temperature'] = [28.5 - sev * 0.9 for _ in times]
    else:
        hourly_w = data_w.get('hourly', {})
        hourly_m = data_m.get('hourly', {})

    # Tạo DataFrame
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

def predict_station(model, station_name, coords, simulated_storm_level=None):
    """Tính toán vector đặc trưng và dự báo lượng mưa bằng mô hình XGBoost."""
    df_raw, is_fallback = fetch_weather_and_marine_data(coords['lat'], coords['lon'], station_name, simulated_storm_level)
    
    # Quy đổi vật lý giống GFS
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
    
    # Tính toán Cấp độ bão (storm_severity)
    if simulated_storm_level is not None:
        storm_severity = int(simulated_storm_level)
    else:
        wind_speed_ms = row_now['wind_speed'] / 3.6
        pres_pa = row_now['PRES']
        if wind_speed_ms >= 32.7 or pres_pa < 96000.0:
            storm_severity = 4
        elif 24.5 <= wind_speed_ms < 32.7 or 96000.0 <= pres_pa < 99000.0:
            storm_severity = 3
        elif 17.2 <= wind_speed_ms < 24.5 or 99000.0 <= pres_pa < 100000.0:
            storm_severity = 2
        elif 10.8 <= wind_speed_ms < 17.2 or 100000.0 <= pres_pa < 100800.0:
            storm_severity = 1
        else:
            storm_severity = 0

    # Ước lượng CAPE và PWAT phù hợp vật lý khí tượng
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
    
    # Tạo vector đầu vào XGBoost
    feat_dict = {
        'latitude': coords['lat'], 'longitude': coords['lon'],
        'TMP': row_now['TMP'], 'RH': row_now['RH'], 'UGRD': row_now['UGRD'], 'VGRD': row_now['VGRD'],
        'CAPE': row_now['CAPE'], 'PWAT': row_now['PWAT'], 'PRES': row_now['PRES'],
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
        'RH_rolling_mean_12h': rh_rolling, 'TMP_rolling_mean_12h': tmp_rolling,
        'hour': row_now['time'].hour, 'month': row_now['time'].month
    }
    
    df_input = pd.DataFrame([feat_dict])[FEATURE_COLS]
    
    # Dự báo bằng mô hình
    try:
        pred_rain = float(model.predict(df_input)[0])
    except Exception:
        pred_rain = 0.0
        
    return {
        'station_name': station_name,
        'latitude': coords['lat'],
        'longitude': coords['lon'],
        'time': row_now['time'].strftime("%Y-%m-%d %H:%M"),
        'temp': float(row_now['temp_2m']),
        'rh': float(row_now['rh_2m']),
        'wind_speed': float(row_now['wind_speed']),
        'wind_dir': float(row_now['wind_dir']),
        'press': float(row_now['press_hpa']),
        'wave_h': float(row_now['WAVE_H']),
        'wave_p': float(row_now['WAVE_P']),
        'current_vel': float(row_now['CURRENT_VEL']),
        'sst': float(row_now['SST'] - 273.15),
        'storm_severity': int(storm_severity),
        'pred_rain': max(0.0, float(pred_rain))
    }, is_fallback

# --- CHƯƠNG TRÌNH CHÍNH & GIAO DIỆN ---

# CSS tùy chỉnh để làm đẹp giao diện
st.markdown("""
<style>
    .main-title {
        color: #1e3799;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 800;
        text-align: center;
        margin-bottom: 5px;
    }
    .sub-title {
        color: #4a69bd;
        font-family: 'Segoe UI', sans-serif;
        text-align: center;
        margin-bottom: 25px;
        font-style: italic;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #1e3799;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stAlert {
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">🌊 HỆ THỐNG DỰ BÁO KHÍ TƯỢNG HẢI DƯƠNG & BÃO BIỂN ĐÔNG</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Ứng dụng web thời gian thực tích hợp Mô hình XGBoost & Bản đồ Tương tác</p>', unsafe_allow_html=True)

# 1. Nạp mô hình XGBoost
@st.cache_resource
def load_xgboost_model():
    if not os.path.exists(MODEL_JSON):
        return None
    try:
        model = XGBRegressor()
        model.load_model(MODEL_JSON)
        return model
    except Exception:
        return None

model = load_xgboost_model()

if model is None:
    st.error(f"❌ Không thể tìm thấy hoặc nạp tệp mô hình tại: `{MODEL_JSON}`. Vui lòng chạy `train_model.py` để huấn luyện trước.")
    st.stop()

# --- SIDEBAR - BẢNG ĐIỀU KHIỂN ---
st.sidebar.image("https://img.icons8.com/clouds/200/typhoon.png", width=150)
st.sidebar.title("🛠️ Bảng Điều Khiển")

# Lựa chọn Chế độ Bão
st.sidebar.subheader("🌪️ Chế độ Khí tượng")
storm_mode = st.sidebar.radio(
    "Chọn phương thức phân tích:",
    ("Tự động (Thời gian thực API)", "Giả lập Cấp độ Bão")
)

simulated_storm = None
if storm_mode == "Giả lập Cấp độ Bão":
    simulated_storm = st.sidebar.slider(
        "Cấp độ Bão Giả lập:",
        min_value=0,
        max_value=4,
        value=1,
        format="%d",
        help="0: Bình thường, 1: Áp thấp nhiệt đới, 2: Bão thường, 3: Bão mạnh, 4: Siêu bão"
    )
    st.sidebar.info(f"Đang giả lập: **{SEVERITY_NAMES[simulated_storm].upper()}**\n\n*(Hệ thống sẽ tự động điều chỉnh sóng biển, gió, áp suất khí quyển tương thích vật lý bão)*")

# Tải lại dữ liệu
if st.sidebar.button("🔄 Cập nhật dữ liệu mới nhất"):
    st.cache_data.clear()
    st.toast("Đang tải lại dữ liệu khí tượng hải dương thời gian thực...", icon="🔄")
    time.sleep(1)
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("🛰️ Hướng dẫn Kết nối WiFi")
st.sidebar.info(
    "**Để xem UI từ thiết bị khác (Điện thoại, Tablet, Máy tính khác):**\n\n"
    "1. Kết nối thiết bị đó vào **cùng WiFi** với máy tính này.\n"
    "2. Nhập địa chỉ **Network URL** (thường có dạng `http://192.168.x.x:8501`) hiển thị trên cửa sổ Terminal của máy này vào trình duyệt web thiết bị đó."
)

# --- THU THẬP & TÍNH TOÁN DỰ BÁO CHO CẢ 8 TRẠM ---
results = []
any_fallback = False

with st.spinner("🚀 Đang đồng bộ hóa dữ liệu vệ tinh & tính toán dự báo lượng mưa..."):
    for name, coords in STATIONS.items():
        res, is_fb = predict_station(model, name, coords, simulated_storm)
        if res:
            results.append(res)
            if is_fb:
                any_fallback = True

df_results = pd.DataFrame(results)

# Cảnh báo nếu đang chạy chế độ ngoại tuyến do mất mạng
if any_fallback and storm_mode != "Giả lập Cấp độ Bão":
    st.warning("⚠️ Không thể kết nối với Open-Meteo API. Hệ thống đã tự động kích hoạt **Mô phỏng Vật lý Dự phòng Ngoại tuyến**.")
elif any_fallback:
    st.info("ℹ️ Chế độ Giả lập đang sử dụng mô phỏng động học biển sâu và khí quyển.")

# --- BỐ CỤC CHÍNH ĐỒ THỊ VÀ BẢN ĐỒ ---
col_map, col_detail = st.columns([1.2, 1])

# --- CỘT 1: BẢN ĐỒ TƯƠNG TÁC (PLOTLY MAPBOX) ---
with col_map:
    st.subheader("📍 Bản Đồ Giám Sát Trạm Biển Đông")
    
    # Định nghĩa nhãn mô tả bão cho từng trạm
    df_results['Trạng Thái'] = df_results['storm_severity'].map(SEVERITY_NAMES)
    df_results['Kích thước marker'] = df_results['pred_rain'].apply(lambda x: max(15, min(x * 1.5 + 15, 60)))
    
    # Vẽ bản đồ bằng Plotly Express Scatter Mapbox
    fig_map = px.scatter_mapbox(
        df_results,
        lat="latitude",
        lon="longitude",
        color="storm_severity",
        color_continuous_scale=[[0, "#2ecc71"], [0.25, "#3498db"], [0.5, "#f1c40f"], [0.75, "#e67e22"], [1, "#e74c3c"]],
        range_color=[0, 4],
        size="Kích thước marker",
        size_max=35,
        hover_name="station_name",
        hover_data={
            "latitude": False,
            "longitude": False,
            "time": True,
            "temp": ":.1f",
            "wind_speed": ":.1f",
            "wave_h": ":.1f",
            "current_vel": ":.2f",
            "pred_rain": ":.1f",
            "Trạng Thái": True,
            "Kích thước marker": False
        },
        zoom=5.0,
        center={"lat": 14.5, "lon": 111.0},
        height=550,
        title="Bản đồ các Trạm quan trắc (Màu sắc: Cấp bão | Kích thước: Dự báo mưa)"
    )
    
    # Cấu hình phong cách bản đồ mở (Không cần token Mapbox)
    fig_map.update_layout(
        mapbox_style="open-street-map",
        margin={"r":0,"t":40,"l":0,"b":0},
        coloraxis_colorbar=dict(
            title="Cấp Bão",
            tickvals=[0, 1, 2, 3, 4],
            ticktext=list(SEVERITY_NAMES.values())
        )
    )
    
    st.plotly_chart(fig_map, use_container_width=True)

# --- CỘT 2: THÔNG TIN CHI TIẾT TRẠM ĐÃ CHỌN ---
with col_detail:
    st.subheader("🔍 Chi Tiết Trạm Quan Trắc")
    selected_station_name = st.selectbox(
        "Chọn một trạm khí tượng để xem chi tiết:",
        df_results['station_name'].tolist()
    )
    
    selected_row = df_results[df_results['station_name'] == selected_station_name].iloc[0]
    
    # Định vị nhãn hiển thị mưa phù hợp
    rain_val = selected_row['pred_rain']
    if rain_val > 10.0:
        rain_class = "🔴 MƯA RẤT TO"
    elif rain_val > 5.0:
        rain_class = "🟠 MƯA TO"
    elif rain_val > 0.5:
        rain_class = "🟡 MƯA VỪA"
    elif rain_val > 0.05:
        rain_class = "🟢 MƯA PHÙN"
    else:
        rain_class = "⚪ KHÔNG MƯA"

    # Hiển thị tóm tắt tình trạng bão của trạm
    sev_lvl = selected_row['storm_severity']
    st.markdown(f"#### Trạng thái hiện tại: <span style='color:{SEVERITY_COLORS[sev_lvl]}; font-weight:bold; font-size: 20px;'>{SEVERITY_NAMES[sev_lvl].upper()} ({rain_class})</span>", unsafe_allow_html=True)
    st.write(f"⏱️ *Thời gian cập nhật dữ liệu: {selected_row['time']} (UTC)*")

    # Vẽ 2 Gauge đồ họa siêu đẹp cho: Gió & Sóng, Dự báo mưa
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        # Gauge Chiều cao Sóng
        fig_g1 = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = selected_row['wave_h'],
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Chiều cao Sóng (m)"},
            gauge = {
                'axis': {'range': [0, 12]},
                'bar': {'color': "#1e3799"},
                'steps' : [
                    {'range': [0, 2], 'color': "rgba(46, 204, 113, 0.2)"},
                    {'range': [2, 4], 'color': "rgba(241, 196, 15, 0.2)"},
                    {'range': [4, 7], 'color': "rgba(230, 126, 34, 0.2)"},
                    {'range': [7, 12], 'color': "rgba(231, 76, 60, 0.2)"}
                ]
            }
        ))
        fig_g1.update_layout(height=230, margin=dict(l=20, r=20, t=40, b=10))
        st.plotly_chart(fig_g1, use_container_width=True)
        
    with col_g2:
        # Gauge Lượng mưa dự báo
        fig_g2 = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = selected_row['pred_rain'],
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Dự báo Mưa 24h (mm)"},
            gauge = {
                'axis': {'range': [0, 50]},
                'bar': {'color': "#3498db"},
                'steps' : [
                    {'range': [0, 1], 'color': "rgba(200, 200, 200, 0.2)"},
                    {'range': [1, 5], 'color': "rgba(52, 152, 219, 0.2)"},
                    {'range': [5, 15], 'color': "rgba(155, 89, 182, 0.2)"},
                    {'range': [15, 50], 'color': "rgba(231, 76, 60, 0.2)"}
                ]
            }
        ))
        fig_g2.update_layout(height=230, margin=dict(l=20, r=20, t=40, b=10))
        st.plotly_chart(fig_g2, use_container_width=True)

# --- DÒNG THÔNG SỐ ĐO ĐẠC KHÍ TƯỢNG HẢI DƯƠNG ---
st.write("---")
st.subheader(f"📊 Các Chỉ Số Khí Tượng Hải Dương - {selected_station_name}")

m1, m2, m3, m4, m5, m6 = st.columns(6)
with m1:
    st.metric(label="🌡️ Nhiệt độ khí quyển", value=f"{selected_row['temp']:.1f} °C")
with m2:
    st.metric(label="💧 Độ ẩm không khí", value=f"{selected_row['rh']:.1f} %")
with m3:
    st.metric(label="💨 Tốc độ Gió", value=f"{selected_row['wind_speed']:.1f} km/h", delta=f"Cấp {int(selected_row['wind_speed']/6):.0f} BF" if selected_row['wind_speed'] > 0 else None)
with m4:
    st.metric(label="🔄 Vận tốc Hải lưu", value=f"{selected_row['current_vel']:.2f} m/s")
with m5:
    st.metric(label="🌊 Nhiệt độ nước biển", value=f"{selected_row['sst']:.1f} °C")
with m6:
    st.metric(label="📉 Áp suất khí quyển", value=f"{selected_row['press']:.1f} hPa")

# --- ĐỒ THỊ SO SÁNH GIỮA CÁC TRẠM ---
st.write("---")
st.subheader("📈 Phân Tích So Sánh Toàn Bộ Các Trạm")

col_c1, col_c2 = st.columns(2)

with col_c1:
    # So sánh lượng mưa dự báo giữa các trạm
    fig_c1 = px.bar(
        df_results.sort_values(by="pred_rain", ascending=False),
        x="station_name",
        y="pred_rain",
        color="pred_rain",
        color_continuous_scale="Blues",
        labels={"station_name": "Trạm Khí Tượng", "pred_rain": "Lượng mưa Dự báo (mm/24h)"},
        title="Dự báo lượng mưa trong 24 giờ tới tại các trạm",
        height=320
    )
    fig_c1.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig_c1, use_container_width=True)

with col_c2:
    # So sánh chiều cao sóng giữa các trạm
    fig_c2 = px.bar(
        df_results.sort_values(by="wave_h", ascending=False),
        x="station_name",
        y="wave_h",
        color="wave_h",
        color_continuous_scale="Viridis",
        labels={"station_name": "Trạm Khí Tượng", "wave_h": "Chiều cao sóng (m)"},
        title="Độ cao sóng biển đo được hiện tại giữa các trạm",
        height=320
    )
    fig_c2.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig_c2, use_container_width=True)

# --- BẢNG DỮ LIỆU TỔNG HỢP VÀ XUẤT CSV ---
st.write("---")
st.subheader("📋 Bảng Tổng Hợp Dự Báo Chi Tiết")

# Định dạng bảng hiển thị
df_display = df_results.copy()
df_display['storm_severity'] = df_display['storm_severity'].map(SEVERITY_NAMES)
df_display = df_display.rename(columns={
    'station_name': 'Trạm Khí Tượng',
    'time': 'Thời Gian (UTC)',
    'temp': 'Nhiệt Độ (°C)',
    'rh': 'Độ Ẩm (%)',
    'wind_speed': 'Gió (km/h)',
    'press': 'Áp Suất (hPa)',
    'wave_h': 'Sóng Cao (m)',
    'current_vel': 'Hải Lưu (m/s)',
    'sst': 'Nhiệt Biển (°C)',
    'storm_severity': 'Cấp Độ Bão',
    'pred_rain': 'Dự Báo Mưa (mm)'
})

cols_to_show = ['Trạm Khí Tượng', 'Thời Gian (UTC)', 'Nhiệt Độ (°C)', 'Độ Ẩm (%)', 'Gió (km/h)', 'Sóng Cao (m)', 'Hải Lưu (m/s)', 'Nhiệt Biển (°C)', 'Áp Suất (hPa)', 'Cấp Độ Bão', 'Dự Báo Mưa (mm)']
st.dataframe(df_display[cols_to_show].style.format({
    'Nhiệt Độ (°C)': '{:.1f}',
    'Độ Ẩm (%)': '{:.1f}',
    'Gió (km/h)': '{:.1f}',
    'Sóng Cao (m)': '{:.1f}',
    'Hải Lưu (m/s)': '{:.2f}',
    'Nhiệt Biển (°C)': '{:.1f}',
    'Áp Suất (hPa)': '{:.1f}',
    'Dự Báo Mưa (mm)': '{:.2f}'
}), use_container_width=True)

# Nút tải dữ liệu CSV về máy
csv_data = df_display[cols_to_show].to_csv(index=False, encoding='utf-8-sig')
st.download_button(
    label="💾 Tải dữ liệu Dự báo về máy (.CSV)",
    data=csv_data,
    file_name=f"du_bao_bien_dong_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv"
)

# --- CHÂN TRANG ---
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #7f8c8d; font-size: 13px;'>"
    "Hệ thống Dự báo khí tượng hải dương Biển Đông • Sử dụng mô hình Machine Learning XGBoost Regressor"
    "</div>",
    unsafe_allow_html=True
)
