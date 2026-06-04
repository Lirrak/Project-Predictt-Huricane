import os
import sys
import pandas as pd
import requests

# Đảm bảo mã hóa đầu ra là UTF-8 để không bị lỗi ký tự tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def main():
    # 1. Đọc file manifest người dùng cung cấp
    manifest_path = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane/noaa_gfs_south_china_sea_manifest_20260601_to_20260602.csv"
    df_manifest = pd.read_csv(manifest_path)

    # 2. Tạo thư mục chứa các file grib2 tải về
    download_dir = "C:/Users/Lirrak/Documents/Born Again/Project Predict Huricane/gfs_data"
    os.makedirs(download_dir, exist_ok=True)

    print(f"Tổng số file cần tải: {len(df_manifest)}")

    # 3. Vòng lặp tải file
    for index, row in df_manifest.iterrows():
        url = row['data_url']
        # Đặt tên file thông qua cycle_id và forecast_hour để đảm bảo tính duy nhất và không bị lỗi tham số URL
        file_name = f"gfs.{row['cycle_id']}.{row['forecast_hour']}.grib2"
        file_path = os.path.join(download_dir, file_name)
        
        # Kiểm tra nếu file đã tải rồi thì bỏ qua để tiết kiệm thời gian
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            print(f"[{index+1}/{len(df_manifest)}] Đã tồn tại: {file_name}")
            continue
            
        print(f"[{index+1}/{len(df_manifest)}] Đang tải: {file_name}...")
        try:
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                print(f"[{index+1}/{len(df_manifest)}] Tải thành công: {file_name}")
            else:
                print(f"Lỗi tải file (Status code: {response.status_code}) tại URL: {url}")
        except Exception as e:
            print(f"Lỗi kết nối khi tải {file_name}: {e}")

    print("Hoàn thành quá trình tải dữ liệu!")

if __name__ == "__main__":
    main()
