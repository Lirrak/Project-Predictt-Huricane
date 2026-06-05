import os
import sys
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

# Setup UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINEERED_CSV = os.path.join(BASE_DIR, "data", "engineered_features.csv")
MODEL_JSON_RAIN = os.path.join(BASE_DIR, "models", "xgboost_rain_model.json")
MODEL_JSON_WIND = os.path.join(BASE_DIR, "models", "xgboost_wind_model.json")
MODEL_JSON_PRES = os.path.join(BASE_DIR, "models", "xgboost_pres_model.json")

def calculate_severity(wind_ms, pres_pa):
    """Phân cấp độ bão vật lý."""
    if wind_ms >= 32.7 or pres_pa < 96000.0:
        return 4
    elif 24.5 <= wind_ms < 32.7 or 96000.0 <= pres_pa < 99000.0:
        return 3
    elif 17.2 <= wind_ms < 24.5 or 99000.0 <= pres_pa < 100000.0:
        return 2
    elif 10.8 <= wind_ms < 17.2 or 100000.0 <= pres_pa < 100800.0:
        return 1
    return 0

def run_audit():
    if not os.path.exists(ENGINEERED_CSV):
        print(f"Lỗi: Không tìm thấy file {ENGINEERED_CSV}")
        return None
        
    df = pd.read_csv(ENGINEERED_CSV)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Calculate target column for Wind Speed
    df['WIND_SPEED'] = np.sqrt(df['UGRD']**2 + df['VGRD']**2)
    
    # Target variables
    target_cols = ['APCP', 'WIND_SPEED', 'PRES']
    feature_cols = [col for col in df.columns if col not in target_cols + ['timestamp', 'station_name']]
    
    # 5. Chia ngẫu nhiên tập dữ liệu (Random Shuffling Split: 80% Train, 20% Test) không theo thứ tự thời gian
    from sklearn.model_selection import train_test_split
    df_train, df_test = train_test_split(df, test_size=0.2, random_state=42, shuffle=True)
    df_train = df_train.copy()
    df_test = df_test.copy()
    
    X_test = df_test[feature_cols]
    
    # Load Models
    model_rain = XGBRegressor()
    model_rain.load_model(MODEL_JSON_RAIN)
    
    model_wind = XGBRegressor()
    model_wind.load_model(MODEL_JSON_WIND)
    
    model_pres = XGBRegressor()
    model_pres.load_model(MODEL_JSON_PRES)
    
    # Predict
    pred_rain = model_rain.predict(X_test)
    pred_wind = model_wind.predict(X_test)
    pred_pres = model_pres.predict(X_test)
    
    df_test['pred_APCP'] = pred_rain
    df_test['pred_WIND_SPEED'] = pred_wind
    df_test['pred_PRES'] = pred_pres
    
    # Compute Persistence Baseline
    # Since each row represents a station's sequential time steps, we group by station_name and shift(1)
    df_test['APCP_persistence'] = df_test.groupby('station_name')['APCP'].shift(1).fillna(method='bfill')
    df_test['WIND_persistence'] = df_test.groupby('station_name')['WIND_SPEED'].shift(1).fillna(method='bfill')
    df_test['PRES_persistence'] = df_test.groupby('station_name')['PRES'].shift(1).fillna(method='bfill')
    
    # Determine actual and predicted severity
    actual_sev = df_test['storm_severity'].values
    
    pred_sev = np.array([calculate_severity(w, p) for w, p in zip(pred_wind, pred_pres)])
    persist_sev = np.array([calculate_severity(w, p) for w, p in zip(df_test['WIND_persistence'], df_test['PRES_persistence'])])
    
    # Class distribution in Test set
    unique_classes, class_counts = np.unique(actual_sev, return_counts=True)
    class_dist = dict(zip(unique_classes, class_counts))
    total_test = len(df_test)
    
    # Strong storm indicators (severity >= 2)
    actual_strong = (actual_sev >= 2)
    pred_strong = (pred_sev >= 2)
    persist_strong = (persist_sev >= 2)
    
    # Metrics calculation
    def get_recall_csi(act, pred):
        tp = np.sum(act & pred)
        fn = np.sum(act & ~pred)
        fp = np.sum(~act & pred)
        tn = np.sum(~act & ~pred)
        
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        csi = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
        return recall, csi
        
    recall_xgb, csi_xgb = get_recall_csi(actual_strong, pred_strong)
    recall_pers, csi_pers = get_recall_csi(actual_strong, persist_strong)
    
    # Convert targets to desired units for evaluation
    # APCP is in mm (no change)
    # Wind Speed is converted from m/s to km/h (multiply by 3.6)
    # Surface Pressure is converted from Pa to hPa (divide by 100.0)
    
    def evaluate_errors(y_true, y_pred, scale=1.0):
        t = y_true * scale
        p = y_pred * scale
        mae = np.mean(np.abs(p - t))
        rmse = np.sqrt(np.mean((p - t)**2))
        mbe = np.mean(p - t)
        return mae, rmse, mbe
        
    mae_r_xgb, rmse_r_xgb, mbe_r_xgb = evaluate_errors(df_test['APCP'].values, pred_rain, 1.0)
    mae_r_pers, rmse_r_pers, mbe_r_pers = evaluate_errors(df_test['APCP'].values, df_test['APCP_persistence'].values, 1.0)
    
    mae_w_xgb, rmse_w_xgb, mbe_w_xgb = evaluate_errors(df_test['WIND_SPEED'].values, pred_wind, 3.6)
    mae_w_pers, rmse_w_pers, mbe_w_pers = evaluate_errors(df_test['WIND_SPEED'].values, df_test['WIND_persistence'].values, 3.6)
    
    mae_p_xgb, rmse_p_xgb, mbe_p_xgb = evaluate_errors(df_test['PRES'].values, pred_pres, 0.01)
    mae_p_pers, rmse_p_pers, mbe_p_pers = evaluate_errors(df_test['PRES'].values, df_test['PRES_persistence'].values, 0.01)
    
    print("AUDIT_RESULTS_START")
    print(f"CLASS_DIST_0:{class_dist.get(0, 0)}")
    print(f"CLASS_DIST_1:{class_dist.get(1, 0)}")
    print(f"CLASS_DIST_2:{class_dist.get(2, 0)}")
    print(f"CLASS_DIST_3:{class_dist.get(3, 0)}")
    print(f"CLASS_DIST_4:{class_dist.get(4, 0)}")
    print(f"TOTAL_TEST:{total_test}")
    print(f"RECALL_XGB:{recall_xgb*100:.2f}")
    print(f"CSI_XGB:{csi_xgb*100:.2f}")
    print(f"RECALL_PERS:{recall_pers*100:.2f}")
    print(f"CSI_PERS:{csi_pers*100:.2f}")
    print(f"MAE_R_XGB:{mae_r_xgb:.4f}")
    print(f"RMSE_R_XGB:{rmse_r_xgb:.4f}")
    print(f"MBE_R_XGB:{mbe_r_xgb:.4f}")
    print(f"MAE_R_PERS:{mae_r_pers:.4f}")
    print(f"RMSE_R_PERS:{rmse_r_pers:.4f}")
    print(f"MBE_R_PERS:{mbe_r_pers:.4f}")
    print(f"MAE_W_XGB:{mae_w_xgb:.4f}")
    print(f"RMSE_W_XGB:{rmse_w_xgb:.4f}")
    print(f"MBE_W_XGB:{mbe_w_xgb:.4f}")
    print(f"MAE_W_PERS:{mae_w_pers:.4f}")
    print(f"RMSE_W_PERS:{rmse_w_pers:.4f}")
    print(f"MBE_W_PERS:{mbe_w_pers:.4f}")
    print(f"MAE_P_XGB:{mae_p_xgb:.4f}")
    print(f"RMSE_P_XGB:{rmse_p_xgb:.4f}")
    print(f"MBE_P_XGB:{mbe_p_xgb:.4f}")
    print(f"MAE_P_PERS:{mae_p_pers:.4f}")
    print(f"RMSE_P_PERS:{rmse_p_pers:.4f}")
    print(f"MBE_P_PERS:{mbe_p_pers:.4f}")
    
    # Physical Consistency Calculations
    # Correlation of predicted wind speed and WAVE_H
    corr_wind_wave = np.corrcoef(pred_wind, df_test['WAVE_H'].values)[0, 1]
    # Correlation of predicted wind speed and CURRENT_VEL
    corr_wind_current = np.corrcoef(pred_wind, df_test['CURRENT_VEL'].values)[0, 1]
    # Correlation of predicted wind speed and PRES
    corr_wind_pres = np.corrcoef(pred_wind, pred_pres)[0, 1]
    
    # SST Cooling check: average SST for strong predicted storms vs normal
    avg_sst_strong = df_test[pred_strong]['SST'].mean() - 273.15 if np.any(pred_strong) else np.nan
    avg_sst_normal = df_test[~pred_strong]['SST'].mean() - 273.15 if np.any(~pred_strong) else np.nan
    
    print(f"CORR_WIND_WAVE:{corr_wind_wave:.4f}")
    print(f"CORR_WIND_CURRENT:{corr_wind_current:.4f}")
    print(f"CORR_WIND_PRES:{corr_wind_pres:.4f}")
    print(f"SST_STRONG:{avg_sst_strong:.2f}")
    print(f"SST_NORMAL:{avg_sst_normal:.2f}")
    print("AUDIT_RESULTS_END")

if __name__ == "__main__":
    run_audit()
