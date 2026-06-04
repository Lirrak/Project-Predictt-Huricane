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
    input_path = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane/extracted_weather.csv"
    if not os.path.exists(input_path):
        print(f"Không tìm thấy file: {input_path}")
        return

    # Đọc dữ liệu thô đã trích xuất từ GRIB2
    df_real = pd.read_csv(input_path)
    df_real['timestamp'] = pd.to_datetime(df_real['timestamp'])
    
    print("--- DỮ LIỆU GRIB2 GỐC ĐÃ TRÍCH XUẤT (5 MẪU) ---")
    print(df_real)

    # THỰC HIỆN TĂNG CƯỜNG DỮ LIỆU CHUỖI THỜI GIAN (DATA AUGMENTATION)
    # Vì chúng ta chỉ có 5 file GRIB2 f000 (tần suất 6 tiếng từ 2026-06-01 00:00 đến 2026-06-02 00:00),
    # nếu trực tiếp tạo Lag và Rolling Features sẽ làm bộ dữ liệu chỉ còn lại 2 mẫu, không đủ để huấn luyện XGBoost.
    # Do đó, ta sẽ tự động tăng cường dữ liệu chuỗi thời gian một cách khoa học:
    # - Tạo chuỗi thời gian tần suất 3 tiếng (3-hourly) kéo dài trong 15 ngày xung quanh mốc này (từ 2026-05-20 đến 2026-06-04)
    # - Mô phỏng các đặc trưng thời tiết theo quy luật vật lý:
    #   + Nhiệt độ (TMP) biến thiên hình sin theo chu kỳ ngày đêm (đạt đỉnh lúc 14h, thấp nhất lúc 5h sáng)
    #   + Độ ẩm (RH) nghịch biến với nhiệt độ (đạt đỉnh lúc sáng sớm, thấp nhất buổi trưa)
    #   + Áp suất (PRES) biến thiên chậm chạp kèm triều khí áp nhỏ
    #   + Gió (UGRD, VGRD) mô phỏng theo mô hình tự hồi quy (Autoregressive - AR) cộng thêm nhiễu trắng
    #   + Lượng mưa (APCP) và Lượng nước ngưng tụ (PWAT) mô phỏng dựa trên tổ hợp của RH, CAPE và áp suất thấp.
    
    print("\nĐang thực hiện tăng cường dữ liệu chuỗi thời gian khoa học (15 ngày, bước 3 giờ)...")
    
    start_date = "2026-05-20 00:00:00"
    end_date = "2026-06-04 00:00:00"
    time_index = pd.date_range(start=start_date, end=end_date, freq='3h')
    
    np.random.seed(42)
    augmented_records = []
    
    # Lấy các giá trị trung bình từ dữ liệu thực tế để neo giữ dải giá trị thực tế
    avg_tmp = df_real['TMP'].mean() if not df_real['TMP'].isna().all() else 301.0
    avg_rh = df_real['RH'].mean() if not df_real['RH'].isna().all() else 78.0
    avg_pres = df_real['PRES'].mean() if not df_real['PRES'].isna().all() else 100800.0
    avg_cape = df_real['CAPE'].mean() if not df_real['CAPE'].isna().all() else 500.0
    avg_pwat = df_real['PWAT'].mean() if not df_real['PWAT'].isna().all() else 45.0
    
    # Khởi tạo giá trị gió cho quy trình AR
    last_u = 2.0
    last_v = -1.0
    
    for t in time_index:
        hour = t.hour
        # 1. Nhiệt độ (TMP): Đỉnh lúc 14h, đáy lúc 5h sáng
        # TMP_mean biến thiên chậm qua các ngày (sóng synoptic)
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
            
        record = {
            'timestamp': t,
            'TMP': tmp,
            'RH': rh,
            'UGRD': last_u,
            'VGRD': last_v,
            'CAPE': cape,
            'PWAT': pwat,
            'PRES': pres,
            'APCP': apcp
        }
        augmented_records.append(record)

    df_augmented = pd.DataFrame(augmented_records)
    
    # Chèn các dòng thực tế từ file GRIB2 vào đúng vị trí thời gian của chúng
    # Để làm điều này, ta xóa các mốc thời gian trùng lắp trong df_augmented rồi gộp lại
    real_timestamps = df_real['timestamp'].tolist()
    df_augmented = df_augmented[~df_augmented['timestamp'].isin(real_timestamps)]
    
    # Chỉ giữ các cột khớp nhau
    common_cols = ['timestamp', 'TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'PRES', 'APCP']
    df_combined = pd.concat([df_augmented[common_cols], df_real[common_cols]], ignore_index=True)
    df_combined = df_combined.sort_values(by='timestamp').reset_index(drop=True)
    
    print(f"Tổng số mẫu sau khi tăng cường và kết hợp: {len(df_combined)}")

    # THIẾT LẬP INDEX LÀ TIMESTAMP ĐỂ TẠO FEATURE ENGINEERING CHUỖI THỜI GIAN
    df_combined.set_index('timestamp', inplace=True)

    # 1. Tạo biến trễ (Lag features): Lấy giá trị của 1 bước trước (3 giờ trước) và 2 bước trước (6 giờ trước)
    features_to_lag = ['TMP', 'RH', 'UGRD', 'VGRD', 'CAPE', 'PWAT', 'APCP']
    for col in features_to_lag:
        df_combined[f'{col}_lag1'] = df_combined[col].shift(1) # Giá trị cách đây 3h
        df_combined[f'{col}_lag2'] = df_combined[col].shift(2) # Giá trị cách đây 6h

    # 2. Tạo biến thống kê động (Rolling features): Trung bình trượt độ ẩm và nhiệt độ trong 4 bước gần nhất (12 giờ)
    df_combined['RH_rolling_mean_12h'] = df_combined['RH'].rolling(window=4).mean()
    df_combined['TMP_rolling_mean_12h'] = df_combined['TMP'].rolling(window=4).mean()

    # 3. Trích xuất yếu tố thời gian (Time Features) để học tính chu kỳ mùa/ngày đêm
    df_combined['hour'] = df_combined.index.hour
    df_combined['month'] = df_combined.index.month

    # Xóa bỏ những dòng đầu tiên bị rỗng (NaN) do dùng hàm .shift() và .rolling()
    df_clean = df_combined.dropna()
    
    print(f"Số mẫu hợp lệ sau khi loại bỏ dòng NaN: {len(df_clean)}")
    print(df_clean.head(5))

    # Lưu kết quả Feature Engineering ra file CSV
    output_path = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane/engineered_features.csv"
    df_clean.to_csv(output_path)
    print(f"\nĐã lưu dữ liệu Feature Engineering thành công tại: {output_path}")

if __name__ == "__main__":
    main()
