import os
import sys
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTED_CSV = os.path.join(BASE_DIR, "data", "extracted_weather.csv")
HISTORICAL_CSV = os.path.join(BASE_DIR, "data", "historical_storm_weather.csv")
ENGINEERED_CSV = os.path.join(BASE_DIR, "data", "engineered_features.csv")
MODEL_JSON = os.path.join(BASE_DIR, "models", "xgboost_rain_model.json")

# Định nghĩa các Custom Loss Functions (Asymmetric Loss) áp đặt trọng số phạt lỗi underestimation cao gấp 5 lần
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

def process_and_engineer_features(df):
    """
    Thực hiện Feature Engineering nâng cao độc lập cho từng TRẠM khí tượng và từng PHÂN ĐOẠN thời gian:
    1. Sắp xếp dữ liệu theo trạm và thời gian.
    2. Xác định các phân đoạn thời gian liên tục (Periods) cho từng trạm độc lập bằng phương pháp vector hóa.
    3. Tính toán Lag và Rolling bằng các hàm Vectorized của Pandas để tăng tốc độ xử lý hơn 100 lần.
    4. Trích xuất đặc trưng vật lý nâng cao (MPI, Wind Shear, Climatological Prior).
    5. Trích xuất đặc trưng thời gian (hour, month).
    """
    df = df.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    # Tính toán chênh lệch thời gian giữa các hàng của từng trạm độc lập
    df['time_diff'] = df.groupby('station_name')['timestamp'].diff()
    
    # Đánh nhãn phân đoạn (period_id) riêng biệt cho từng trạm - Tối ưu hóa Vector hóa cực mạnh
    df['is_new_period'] = (df['time_diff'] > pd.Timedelta(hours=12)).fillna(False)
    df['period_id'] = df.groupby('station_name')['is_new_period'].cumsum()
    
    # Mở rộng các biến tính trễ (Lag) bao gồm Chiều cao sóng, Tốc độ hải lưu, SST và Khí áp
    features_to_lag = ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'APCP', 'WAVE_H', 'CURRENT_VEL', 'SST', 'PRES']
    
    # Sử dụng groupby trực tiếp và vectorized shift/transform
    grouped = df.groupby(['station_name', 'period_id'])
    for col in features_to_lag:
        df[f'{col}_lag1'] = grouped[col].shift(1)
        df[f'{col}_lag2'] = grouped[col].shift(2)
        
    df['RH_rolling_mean_12h'] = grouped['RH'].transform(lambda x: x.rolling(window=4).mean())
    df['TMP_rolling_mean_12h'] = grouped['TMP'].transform(lambda x: x.rolling(window=4).mean())
    df['PRES_rolling_mean_12h'] = grouped['PRES'].transform(lambda x: x.rolling(window=4).mean())
    
    # Tính toán biến Sức gió tức thời và trễ
    df['WIND_SPEED_temp'] = np.sqrt(df['UGRD']**2 + df['VGRD']**2)
    df['WIND_SPEED_lag1'] = np.sqrt(df['UGRD_lag1']**2 + df['VGRD_lag1']**2)
    df['WIND_SPEED_lag2'] = np.sqrt(df['UGRD_lag2']**2 + df['VGRD_lag2']**2)
    
    df['WIND_rolling_mean_12h'] = df.groupby(['station_name', 'period_id'])['WIND_SPEED_temp'].transform(lambda x: x.rolling(window=4).mean())
    df['WIND_rolling_max_12h'] = df.groupby(['station_name', 'period_id'])['WIND_SPEED_temp'].transform(lambda x: x.rolling(window=4).max())
    
    df['PRES_change_6h'] = df['PRES'] - df['PRES_lag2']
    df['WIND_change_6h'] = df['WIND_SPEED_temp'] - df['WIND_SPEED_lag2']
    df.drop(columns=['WIND_SPEED_temp'], inplace=True, errors='ignore')
    
    df['hour'] = df['timestamp'].dt.hour
    df['month'] = df['timestamp'].dt.month
    
    # 1. Tính toán Maximum Potential Intensity (MPI) - Emanuel rút gọn
    sst_c = df['SST'] - 273.15
    e_s = 6.112 * np.exp(17.67 * sst_c / (sst_c + 243.5))
    temp_diff_ratio = (df['SST'] - df['TMP']).clip(lower=0.0) / df['TMP'].clip(lower=200.0)
    df['MPI'] = 70.0 * np.sqrt(temp_diff_ratio * e_s)
    
    # 2. Tính toán Wind Shear
    WS = np.sqrt(df['UGRD']**2 + df['VGRD']**2)
    WS_lag1 = np.sqrt(df['UGRD_lag1']**2 + df['VGRD_lag1']**2)
    WS_lag2 = np.sqrt(df['UGRD_lag2']**2 + df['VGRD_lag2']**2)
    
    df['wind_shear_mag_lag1'] = np.abs(WS - WS_lag1)
    df['wind_shear_mag_lag2'] = np.abs(WS - WS_lag2)
    
    df['wind_shear_vec_lag1'] = np.sqrt((df['UGRD'] - df['UGRD_lag1'])**2 + (df['VGRD'] - df['VGRD_lag1'])**2)
    df['wind_shear_vec_lag2'] = np.sqrt((df['UGRD'] - df['UGRD_lag2'])**2 + (df['VGRD'] - df['VGRD_lag2'])**2)
    
    # 3. Tính toán Climatological Prior từ tập bão lịch sử
    hist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "historical_storm_weather.csv")
    if os.path.exists(hist_path):
        df_hist = pd.read_csv(hist_path)
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        df_hist['month'] = df_hist['timestamp'].dt.month
        df_hist['lat_round'] = df_hist['latitude'].round(1)
        df_hist['lon_round'] = df_hist['longitude'].round(1)
        
        prior_grouped = df_hist.groupby(['lat_round', 'lon_round', 'month'])['storm_severity'].apply(
            lambda s: (s > 0).mean()
        ).reset_index(name='climatology_prior')
        
        monthly_prior = df_hist.groupby('month')['storm_severity'].apply(
            lambda s: (s > 0).mean()
        ).to_dict()
        
        df['lat_round'] = df['latitude'].round(1)
        df['lon_round'] = df['longitude'].round(1)
        
        df = pd.merge(df, prior_grouped, on=['lat_round', 'lon_round', 'month'], how='left')
        df['climatology_prior'] = df.apply(
            lambda r: r['climatology_prior'] if not pd.isna(r['climatology_prior']) else monthly_prior.get(r['month'], 0.3),
            axis=1
        )
        df.drop(columns=['lat_round', 'lon_round'], inplace=True, errors='ignore')
    else:
        default_priors = {1: 0.05, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.1, 6: 0.2, 
                          7: 0.4, 8: 0.5, 9: 0.6, 10: 0.5, 11: 0.3, 12: 0.1}
        df['climatology_prior'] = df['month'].map(default_priors).fillna(0.2)
        
    df = df.drop(columns=['period_id', 'time_diff', 'is_new_period'])
    df_clean = df.dropna().reset_index(drop=True)
    return df_clean

def main():
    print("=== PIPELINE HUẤN LUYỆN MÔ HÌNH HẢI DƯƠNG - KHÍ TƯỢNG ĐA TRẠM BIỂN ĐÔNG ===")
    
    # 1. Đọc dữ liệu thực tế GFS đa trạm hiện tại
    if not os.path.exists(EXTRACTED_CSV):
        print(f"Lỗi: Không tìm thấy file {EXTRACTED_CSV}")
        return
    df_real = pd.read_csv(EXTRACTED_CSV)
    df_real['timestamp'] = pd.to_datetime(df_real['timestamp'])
    
    core_cols = ['timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 
                 'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity', 'APCP']
    df_real = df_real[core_cols]

    # 2. Đọc dữ liệu bão lịch sử cực đại tích hợp hải dương
    if os.path.exists(HISTORICAL_CSV):
        print(f"Đọc dữ liệu lịch sử bão đa trạm từ {HISTORICAL_CSV}...")
        df_hist = pd.read_csv(HISTORICAL_CSV)
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        df_hist = df_hist[core_cols]
        
        print(f"Hợp nhất: {len(df_real)} mẫu thực tế và {len(df_hist)} mẫu bão lịch sử đa trạm.")
        df_combined = pd.concat([df_real, df_hist], ignore_index=True)
    else:
        print("Cảnh báo: Không tìm thấy file dữ liệu lịch sử bão, chỉ sử dụng dữ liệu đa trạm hiện tại.")
        df_combined = df_real.copy()

    # 3. Thực hiện Feature Engineering đa trạm phân đoạn hải dương học
    print("Thực hiện Feature Engineering đa trạm theo phân đoạn...")
    df_features = process_and_engineer_features(df_combined)
    df_features.to_csv(ENGINEERED_CSV, index=False)
    print(f"Đã lưu tệp đặc trưng đa trạm hoàn chỉnh tại: {ENGINEERED_CSV}")
    print(f"Tổng số mẫu đặc trưng đa trạm hợp lệ: {len(df_features)}")
    
    # Tính toán cột mục tiêu cho Gió (Wind Speed)
    df_features['WIND_SPEED'] = np.sqrt(df_features['UGRD']**2 + df_features['VGRD']**2)
    
    # 4. Xác định Input (X) và Target (y) bằng danh sách 54 đặc trưng khí quyển - hải dương học tối ưu
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
    
    print(f"Số lượng đặc trưng đầu vào ({len(FEATURE_COLS_54)}): {FEATURE_COLS_54}")

    # 5. Chia ngẫu nhiên tập dữ liệu (Random Shuffling Split: 80% Train, 20% Test) không theo thứ tự thời gian
    from sklearn.model_selection import train_test_split
    df_train, df_test = train_test_split(df_features, test_size=0.2, random_state=42, shuffle=True)
    
    X_train = df_train[FEATURE_COLS_54]
    X_test = df_test[FEATURE_COLS_54]

    print(f"Mẫu huấn luyện đa trạm (Ngẫu nhiên 80%): {len(df_train)} | Mẫu kiểm thử đa trạm (Ngẫu nhiên 20%): {len(df_test)}")

    # 6. Khởi tạo và huấn luyện đa mục tiêu (Multi-Task) dự báo APCP, Gió, Khí áp
    print("\n--- BẮT ĐẦU HUẤN LUYỆN ĐA MỤC TIÊU (MULTI-TASK) DỰ BÁO ĐỒNG THỜI APCP, WIND_SPEED, PRES ---")
    
    # 1. Dự báo APCP (Mưa)
    print("\n[Mục tiêu 1/3] Huấn luyện mô hình dự báo lượng mưa APCP (Custom Asymmetric Loss)...")
    model_apcp = XGBRegressor(
        n_estimators=150,
        learning_rate=0.03,
        max_depth=7,
        subsample=0.8,
        colsample_bytree=0.9,
        n_jobs=-1,
        random_state=42,
        objective=apcp_asymmetric_obj
    )
    model_apcp.fit(X_train, df_train['APCP'], eval_set=[(X_test, df_test['APCP'])], verbose=15)
    
    # 2. Dự báo WIND_SPEED (Gió)
    print("\n[Mục tiêu 2/3] Huấn luyện mô hình dự báo tốc độ gió WIND_SPEED (Custom Asymmetric Loss)...")
    model_wind = XGBRegressor(
        n_estimators=150,
        learning_rate=0.03,
        max_depth=7,
        subsample=0.8,
        colsample_bytree=0.9,
        n_jobs=-1,
        random_state=42,
        objective=wind_asymmetric_obj
    )
    model_wind.fit(X_train, df_train['WIND_SPEED'], eval_set=[(X_test, df_test['WIND_SPEED'])], verbose=15)
    
    # 3. Dự báo PRES (Khí áp)
    print("\n[Mục tiêu 3/3] Huấn luyện mô hình dự báo khí áp bề mặt PRES (Custom Asymmetric Loss)...")
    model_pres = XGBRegressor(
        n_estimators=150,
        learning_rate=0.03,
        max_depth=7,
        subsample=0.8,
        colsample_bytree=0.9,
        n_jobs=-1,
        random_state=42,
        objective=pres_asymmetric_obj
    )
    model_pres.fit(X_train, df_train['PRES'], eval_set=[(X_test, df_test['PRES'])], verbose=15)
    
    # 7. Dự báo và đánh giá sai số trên tập kiểm thử độc lập
    y_pred_apcp = model_apcp.predict(X_test)
    y_pred_wind = model_wind.predict(X_test)
    y_pred_pres = model_pres.predict(X_test)
    
    mae_apcp = mean_absolute_error(df_test['APCP'], y_pred_apcp)
    rmse_apcp = np.sqrt(mean_squared_error(df_test['APCP'], y_pred_apcp))
    
    mae_wind = mean_absolute_error(df_test['WIND_SPEED'], y_pred_wind)
    rmse_wind = np.sqrt(mean_squared_error(df_test['WIND_SPEED'], y_pred_wind))
    
    mae_pres = mean_absolute_error(df_test['PRES'], y_pred_pres)
    rmse_pres = np.sqrt(mean_squared_error(df_test['PRES'], y_pred_pres))

    print(f"\n==========================================")
    print(f"--- KẾT QUẢ ĐÁNH GIÁ MÔ HÌNH ĐA MỤC TIÊU HẢI DƯƠNG - KHÍ TƯỢNG ---")
    print(f"1. Lượng mưa APCP:  MAE = {mae_apcp:.4f} mm | RMSE = {rmse_apcp:.4f} mm")
    print(f"2. Tốc độ gió WS:   MAE = {mae_wind:.4f} m/s | RMSE = {rmse_wind:.4f} m/s")
    print(f"3. Khí áp PRES:     MAE = {mae_pres:.4f} Pa  | RMSE = {rmse_pres:.4f} Pa")
    print(f"==========================================")
 
    # 8. Xuất các mô hình thành file JSON
    MODEL_JSON_WIND = os.path.join(BASE_DIR, "models", "xgboost_wind_model.json")
    MODEL_JSON_PRES = os.path.join(BASE_DIR, "models", "xgboost_pres_model.json")
    
    model_apcp.save_model(MODEL_JSON)
    model_wind.save_model(MODEL_JSON_WIND)
    model_pres.save_model(MODEL_JSON_PRES)
    
    print(f"Đã lưu mô hình APCP (Mưa) tại: {MODEL_JSON}")
    print(f"Đã lưu mô hình WIND_SPEED (Gió) tại: {MODEL_JSON_WIND}")
    print(f"Đã lưu mô hình PRES (Áp suất) tại: {MODEL_JSON_PRES}")

if __name__ == "__main__":
    main()
