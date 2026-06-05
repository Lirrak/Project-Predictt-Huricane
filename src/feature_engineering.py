import os
import sys
import numpy as np
import pandas as pd

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    input_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "extracted_weather.csv")
    if not os.path.exists(input_path):
        print(f"Không tìm thấy file: {input_path}")
        return

    # Đọc dữ liệu thô đã trích xuất từ GRIB2
    df_real = pd.read_csv(input_path)
    df_real['timestamp'] = pd.to_datetime(df_real['timestamp'])
    
    print("--- DỮ LIỆU GRIB2 GỐC ĐÃ TRÍCH XUẤT (5 MẪU) ---")
    print(df_real.head(5))

    print("\nĐang thực hiện tăng cường dữ liệu chuỗi thời gian khoa học (15 ngày, bước 3 giờ) độc lập cho từng trạm...")
    
    start_date = "2026-05-20 00:00:00"
    end_date = "2026-06-04 00:00:00"
    time_index = pd.date_range(start=start_date, end=end_date, freq='3h')
    
    np.random.seed(42)
    augmented_records = []
    
    unique_stations = df_real['station_name'].unique()
    
    for st_name in unique_stations:
        df_st = df_real[df_real['station_name'] == st_name]
        lat = df_st['latitude'].iloc[0]
        lon = df_st['longitude'].iloc[0]
        
        # Lấy các giá trị trung bình từ dữ liệu thực tế của từng trạm để neo giữ dải giá trị thực tế
        avg_tmp = df_st['TMP'].mean() if not df_st['TMP'].isna().all() else 301.0
        avg_rh = df_st['RH'].mean() if not df_st['RH'].isna().all() else 78.0
        avg_pres = df_st['PRES'].mean() if not df_st['PRES'].isna().all() else 100800.0
        avg_cape = df_st['CAPE'].mean() if not df_st['CAPE'].isna().all() else 500.0
        avg_pwat = df_st['PWAT'].mean() if not df_st['PWAT'].isna().all() else 45.0
        avg_sst = df_st['SST'].mean() if not df_st['SST'].isna().all() else 301.15
        
        # Khởi tạo giá trị gió cho quy trình AR
        last_u = 2.0
        last_v = -1.0
        
        for t in time_index:
            hour = t.hour
            # 1. Nhiệt độ (TMP): Đỉnh lúc 14h, đáy lúc 5h sáng
            day_idx = (t - time_index[0]).days
            synoptic_temp = np.sin(2 * np.pi * day_idx / 7) * 1.5
            diurnal_temp = -np.cos(2 * np.pi * (hour - 5) / 24) * 3.5
            tmp = avg_tmp + synoptic_temp + diurnal_temp + np.random.normal(0, 0.5)
            
            # 2. Độ ẩm (RH): Nghịch biến với nhiệt độ, cao vào ban đêm, thấp vào ban ngày
            diurnal_rh = np.cos(2 * np.pi * (hour - 5) / 24) * 10.0
            synoptic_rh = np.sin(2 * np.pi * day_idx / 5) * 5.0
            rh = avg_rh + diurnal_rh + synoptic_rh + np.random.normal(0, 2.0)
            rh = np.clip(rh, 45.0, 100.0)
            
            # 3. Gió UGRD, VGRD: Mô hình tự hồi quy AR(1)
            last_u = 0.8 * last_u + 0.2 * np.random.normal(1.5, 2.0)
            last_v = 0.8 * last_v + 0.2 * np.random.normal(-0.5, 2.0)
            wind_speed = np.sqrt(last_u**2 + last_v**2)
            
            # 4. Áp suất bề mặt (PRES): Có dao động bán nhật nhỏ và biến thiên chậm theo thời tiết
            semi_diurnal_pres = np.sin(4 * np.pi * hour / 24) * 100.0
            synoptic_pres = -np.sin(2 * np.pi * day_idx / 8) * 400.0
            pres = avg_pres + semi_diurnal_pres + synoptic_pres + np.random.normal(0, 50.0)
            
            # 5. CAPE: Chỉ cao khi nóng (TMP cao) và ẩm (RH cao) vào ban ngày
            cape_base = max(0.0, (tmp - 298.0) * 150.0) if hour in range(10, 20) else 50.0
            cape = cape_base * (rh / 80.0) + np.random.normal(0, 50.0)
            cape = max(0.0, cape)
            
            # 6. PWAT: Tỷ lệ thuận với TMP và RH
            pwat = avg_pwat + (tmp - avg_tmp) * 1.5 + (rh - avg_rh) * 0.3 + np.random.normal(0, 1.5)
            pwat = np.clip(pwat, 20.0, 75.0)
            
            # 7. APCP (Lượng mưa): Có mưa khi độ ẩm RH > 80% và CAPE lớn hoặc áp thấp mạnh
            if rh > 80.0:
                rh_factor = (rh - 80.0) * 0.3
                cape_factor = (cape / 300.0)
                pres_factor = max(0.0, (101100.0 - pres) / 50.0) if pres < 101100.0 else 0.0
                apcp = rh_factor + cape_factor + pres_factor + np.random.normal(0, 0.8)
                apcp = max(0.0, apcp)
            else:
                apcp = 0.0
                
            # 8. Hải dương (SST, Sóng, Hải lưu)
            sst = avg_sst + np.random.normal(0, 0.2)
            wave_h = max(0.1, 0.022 * (wind_speed ** 1.9) + np.random.normal(0, 0.1))
            wave_dir = (np.degrees(np.arctan2(-last_u, -last_v)) + np.random.normal(0, 10.0)) % 360.0
            wave_p = max(2.0, 0.45 * wind_speed + np.random.normal(0, 0.3))
            curr_vel = max(0.05, 0.028 * wind_speed + np.random.normal(0, 0.02))
            curr_dir = (wave_dir + 45.0 + np.random.normal(0, 10.0)) % 360.0
            
            # 9. Đánh nhãn storm_severity thô dựa trên quy chuẩn vật lý khí áp và gió
            if wind_speed >= 32.7 or pres < 96000.0:
                storm_sev = 4
            elif 24.5 <= wind_speed < 32.7 or 96000.0 <= pres < 99000.0:
                storm_sev = 3
            elif 17.2 <= wind_speed < 24.5 or 99000.0 <= pres < 100000.0:
                storm_sev = 2
            elif 10.8 <= wind_speed < 17.2 or 100000.0 <= pres < 100800.0:
                storm_sev = 1
            else:
                storm_sev = 0
                
            record = {
                'timestamp': t,
                'station_name': st_name,
                'latitude': lat,
                'longitude': lon,
                'TMP': tmp,
                'RH': rh,
                'UGRD': last_u,
                'VGRD': last_v,
                'CAPE': cape,
                'PWAT': pwat,
                'PRES': pres,
                'APCP': apcp,
                'SST': sst,
                'WAVE_H': wave_h,
                'WAVE_DIR': wave_dir,
                'WAVE_P': wave_p,
                'CURRENT_VEL': curr_vel,
                'CURRENT_DIR': curr_dir,
                'storm_severity': storm_sev
            }
            augmented_records.append(record)
            
    df_augmented = pd.DataFrame(augmented_records)
    
    # Chèn các dòng thực tế từ file GRIB2 vào đúng vị trí thời gian và trạm của chúng
    df_real['time_station'] = df_real['timestamp'].astype(str) + "_" + df_real['station_name']
    df_augmented['time_station'] = df_augmented['timestamp'].astype(str) + "_" + df_augmented['station_name']
    
    df_augmented = df_augmented[~df_augmented['time_station'].isin(df_real['time_station'])]
    df_real = df_real.drop(columns=['time_station'])
    df_augmented = df_augmented.drop(columns=['time_station'])
    
    # Giữ trọn vẹn toàn bộ các biến vật lý khí quyển và hải dương học
    common_cols = [
        'timestamp', 'station_name', 'latitude', 'longitude', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES',
        'WAVE_H', 'WAVE_DIR', 'WAVE_P', 'CURRENT_VEL', 'CURRENT_DIR', 'SST', 'storm_severity', 'APCP'
    ]
    df_combined = pd.concat([df_augmented[common_cols], df_real[common_cols]], ignore_index=True)
    df_combined = df_combined.sort_values(by=['station_name', 'timestamp']).reset_index(drop=True)
    
    print(f"Tổng số mẫu sau khi tăng cường và kết hợp: {len(df_combined)}")

    # 1. TÍNH TOÁN MAXIMUM POTENTIAL INTENSITY (MPI) - CÔNG THỨC EMANUEL RÚT GỌN
    print("Tính toán Maximum Potential Intensity (MPI) theo nhiệt động lực học Clausius-Clapeyron...")
    sst_c = df_combined['SST'] - 273.15
    # Áp suất hơi bão hòa tại bề mặt biển (hPa)
    e_s = 6.112 * np.exp(17.67 * sst_c / (sst_c + 243.5))
    # Hiệu số nhiệt độ tỉ đối giữa bề mặt sst và nhiệt độ không khí tmp
    temp_diff_ratio = (df_combined['SST'] - df_combined['TMP']).clip(lower=0.0) / df_combined['TMP'].clip(lower=200.0)
    # Vận tốc tiềm năng cực đại MPI (m/s)
    df_combined['MPI'] = 70.0 * np.sqrt(temp_diff_ratio * e_s)

    # 2. SẮP XẾP VÀ TRÍCH XUẤT CÁC BIẾN TRỄ VÀ BIẾN ĐỘNG THEO TỪNG TRẠM ĐỘC LẬP
    grouped = df_combined.groupby('station_name')
    
    # Tạo biến trễ (Lag features): Lấy giá trị của 1 bước trước (3 giờ trước) và 2 bước trước (6 giờ trước)
    features_to_lag = ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'APCP', 'SST', 'WAVE_H', 'CURRENT_VEL']
    for col in features_to_lag:
        df_combined[f'{col}_lag1'] = grouped[col].shift(1) # Giá trị cách đây 3h
        df_combined[f'{col}_lag2'] = grouped[col].shift(2) # Giá trị cách đây 6h

    # Tạo biến thống kê động (Rolling features): Trung bình trượt độ ẩm và nhiệt độ trong 4 bước gần nhất (12 giờ)
    df_combined['RH_rolling_mean_12h'] = grouped['RH'].transform(lambda x: x.rolling(window=4).mean())
    df_combined['TMP_rolling_mean_12h'] = grouped['TMP'].transform(lambda x: x.rolling(window=4).mean())

    # Trích xuất yếu tố thời gian (Time Features) để học tính chu kỳ mùa/ngày đêm
    df_combined['hour'] = df_combined['timestamp'].dt.hour
    df_combined['month'] = df_combined['timestamp'].dt.month

    # 3. TÍNH TOÁN ĐỘ ĐỨT GIÓ ĐỘNG LỰC HỌC (WIND SHEAR)
    print("Tính toán độ đứt gió động lực học (Wind Shear) magnitude & vector chênh lệch...")
    WS = np.sqrt(df_combined['UGRD']**2 + df_combined['VGRD']**2)
    WS_lag1 = np.sqrt(df_combined['UGRD_lag1']**2 + df_combined['VGRD_lag1']**2)
    WS_lag2 = np.sqrt(df_combined['UGRD_lag2']**2 + df_combined['VGRD_lag2']**2)
    
    # Độ đứt tốc độ gió (Magnitude shear)
    df_combined['wind_shear_mag_lag1'] = np.abs(WS - WS_lag1)
    df_combined['wind_shear_mag_lag2'] = np.abs(WS - WS_lag2)
    
    # Độ đứt vectơ gió (Vector shear)
    df_combined['wind_shear_vec_lag1'] = np.sqrt((df_combined['UGRD'] - df_combined['UGRD_lag1'])**2 + (df_combined['VGRD'] - df_combined['VGRD_lag1'])**2)
    df_combined['wind_shear_vec_lag2'] = np.sqrt((df_combined['UGRD'] - df_combined['UGRD_lag2'])**2 + (df_combined['VGRD'] - df_combined['VGRD_lag2'])**2)

    # 4. TÍCH HỢP CLIMATOLOGICAL PRIOR TỪ TẬP BÃO LỊCH SỬ
    hist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "historical_storm_weather.csv")
    if os.path.exists(hist_path):
        print(f"Đang phân tích tri thức Climatological Prior từ cơ sở dữ liệu lịch sử {hist_path}...")
        df_hist = pd.read_csv(hist_path)
        df_hist['timestamp'] = pd.to_datetime(df_hist['timestamp'])
        df_hist['month'] = df_hist['timestamp'].dt.month
        df_hist['lat_round'] = df_hist['latitude'].round(1)
        df_hist['lon_round'] = df_hist['longitude'].round(1)
        
        # Xác suất nền xuất hiện bão theo tọa độ và tháng
        prior_grouped = df_hist.groupby(['lat_round', 'lon_round', 'month'])['storm_severity'].apply(
            lambda s: (s > 0).mean()
        ).reset_index(name='climatology_prior')
        
        # Xác suất dự phòng theo tháng
        monthly_prior = df_hist.groupby('month')['storm_severity'].apply(
            lambda s: (s > 0).mean()
        ).to_dict()
        
        df_combined['lat_round'] = df_combined['latitude'].round(1)
        df_combined['lon_round'] = df_combined['longitude'].round(1)
        
        df_combined = pd.merge(df_combined, prior_grouped, on=['lat_round', 'lon_round', 'month'], how='left')
        
        # Điền khuyết các trạm mới bằng xác suất nền tháng của vùng biển
        df_combined['climatology_prior'] = df_combined.apply(
            lambda r: r['climatology_prior'] if not pd.isna(r['climatology_prior']) else monthly_prior.get(r['month'], 0.3),
            axis=1
        )
        df_combined.drop(columns=['lat_round', 'lon_round'], inplace=True, errors='ignore')
    else:
        print("Cảnh báo: Không tìm thấy tệp bão lịch sử, gán climatological prior mặc định theo chu kỳ năm...")
        default_priors = {1: 0.05, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.1, 6: 0.2, 
                          7: 0.4, 8: 0.5, 9: 0.6, 10: 0.5, 11: 0.3, 12: 0.1}
        df_combined['climatology_prior'] = df_combined['month'].map(default_priors).fillna(0.2)

    # Đặt lại chỉ mục
    df_combined.set_index('timestamp', inplace=True)

    # Xóa bỏ những dòng đầu tiên bị rỗng (NaN) do dùng hàm .shift() và .rolling()
    df_clean = df_combined.dropna()
    
    print(f"Số mẫu hợp lệ sau khi loại bỏ dòng NaN: {len(df_clean)}")
    print(df_clean.head(5))

    # Lưu kết quả Feature Engineering ra file CSV
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "engineered_features.csv")
    df_clean.to_csv(output_path)
    print(f"\nĐã lưu dữ liệu Feature Engineering thành công tại: {output_path}")

if __name__ == "__main__":
    main()
