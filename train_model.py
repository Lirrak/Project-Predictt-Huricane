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

BASE_DIR = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane"
EXTRACTED_CSV = os.path.join(BASE_DIR, "extracted_weather.csv")
HISTORICAL_CSV = os.path.join(BASE_DIR, "historical_storm_weather.csv")
ENGINEERED_CSV = os.path.join(BASE_DIR, "engineered_features.csv")
MODEL_JSON = os.path.join(BASE_DIR, "xgboost_rain_model.json")

def process_and_engineer_features(df):
    """
    Thực hiện Feature Engineering nâng cao độc lập cho từng TRẠM khí tượng và từng PHÂN ĐOẠN thời gian:
    1. Sắp xếp dữ liệu theo trạm và thời gian.
    2. Xác định các phân đoạn thời gian liên tục (Periods) cho từng trạm độc lập.
    3. Tính toán Lag và Rolling độc lập theo cặp (station_name, period_id) bao gồm các yếu tố hải dương học.
    4. Trích xuất đặc trưng thời gian (hour, month).
    """
    df = df.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    # Tính toán chênh lệch thời gian giữa các hàng của từng trạm độc lập
    df['time_diff'] = df.groupby('station_name')['timestamp'].diff()
    
    # Đánh nhãn phân đoạn (period_id) riêng biệt cho từng trạm
    df['period_id'] = df.groupby('station_name', group_keys=False).apply(
        lambda g: (g['time_diff'] > pd.Timedelta(hours=12)).fillna(False).cumsum()
    )
    
    # Mở rộng các biến tính trễ (Lag) bao gồm Chiều cao sóng và Tốc độ hải lưu
    features_to_lag = ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'APCP', 'WAVE_H', 'CURRENT_VEL']
    lagged_dfs = []
    
    for (station, pid), group in df.groupby(['station_name', 'period_id']):
        group = group.copy()
        for col in features_to_lag:
            group[f'{col}_lag1'] = group[col].shift(1)
            group[f'{col}_lag2'] = group[col].shift(2)
        group['RH_rolling_mean_12h'] = group['RH'].rolling(window=4).mean()
        group['TMP_rolling_mean_12h'] = group['TMP'].rolling(window=4).mean()
        lagged_dfs.append(group)
        
    df_engineered = pd.concat(lagged_dfs, ignore_index=True)
    df_engineered['hour'] = df_engineered['timestamp'].dt.hour
    df_engineered['month'] = df_engineered['timestamp'].dt.month
    df_engineered = df_engineered.drop(columns=['period_id', 'time_diff'])
    df_clean = df_engineered.dropna().reset_index(drop=True)
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
    
    # 4. Xác định Input (X) và Target (y)
    # Loại bỏ APCP, timestamp, và station_name ra khỏi X
    target_col = 'APCP'
    feature_cols = [col for col in df_features.columns if col not in [target_col, 'timestamp', 'station_name']]
    
    X = df_features[feature_cols]
    y = df_features[target_col]
    
    print(f"Số lượng đặc trưng đầu vào ({len(feature_cols)}): {feature_cols}")

    # 5. Chia tập dữ liệu (80% Train, 20% Test) theo ranh giới trạm và dòng thời gian
    df_features = df_features.sort_values(by='timestamp').reset_index(drop=True)
    split_idx = int(len(df_features) * 0.8)
    
    X_train = df_features.iloc[:split_idx][feature_cols]
    y_train = df_features.iloc[:split_idx][target_col]
    X_test = df_features.iloc[split_idx:][feature_cols]
    y_test = df_features.iloc[split_idx:][target_col]

    print(f"Mẫu huấn luyện đa trạm: {len(X_train)} | Mẫu kiểm thử đa trạm: {len(X_test)}")

    # 6. Khởi tạo và huấn luyện XGBoost Regressor
    model = XGBRegressor(
        n_estimators=200,      # Tăng số cây vì tập dữ liệu bão lịch sử cực kỳ lớn (~10,000 dòng) và đa dạng đặc trưng
        learning_rate=0.03,
        max_depth=7,           # Tăng độ sâu cây lên 7 để học các hàm phi tuyến hải dương cực đoan
        subsample=0.8,
        colsample_bytree=0.9,
        random_state=42
    )
    
    print("\n--- BẮT ĐẦU HUẤN LUYỆN XGBOOST TRÊN SIÊU CƠ SỞ DỮ LIỆU ĐA TRẠM KẾT HỢP ---")
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=20
    )
    
    # 7. Dự báo và đánh giá sai số
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))

    print(f"\n==========================================")
    print(f"--- KẾT QUẢ ĐÁNH GIÁ MÔ HÌNH HẢI DƯƠNG - KHÍ TƯỢNG ---")
    print(f"Sai số tuyệt đối trung bình (MAE): {mae:.4f} mm")
    print(f"Sai số bình phương trung bình (RMSE): {rmse:.4f} mm")
    print(f"==========================================")

    # 8. Xuất mô hình thành file JSON
    model.save_model(MODEL_JSON)
    print(f"Đã lưu mô hình XGBoost đa trạm hải dương thành công tại: {MODEL_JSON}")

if __name__ == "__main__":
    main()
