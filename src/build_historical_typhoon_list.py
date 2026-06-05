import os
import sys
import datetime
import pandas as pd

# Đảm bảo mã hóa đầu ra là UTF-8 để hiển thị tiếng Việt trên Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=== ĐANG TẢI VÀ PHÂN TÍCH CƠ SỞ DỮ LIỆU BÃO TOÀN CẦU IBTrACS (NOAA) ===")
    
    ibtracs_url = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.WP.list.v04r01.csv"
    
    print("Đang tải tệp cơ sở dữ liệu bão Tây Thái Bình Dương (khoảng 113 MB)...")
    try:
        # Sử dụng usecols để tối ưu bộ nhớ RAM cực hạn và tăng tốc độ đọc
        df = pd.read_csv(
            ibtracs_url, 
            skiprows=[1], 
            usecols=['SID', 'SEASON', 'NAME', 'ISO_TIME', 'LAT', 'LON'],
            low_memory=False
        )
        print("Tải và đọc dữ liệu thành công!")
    except Exception as e:
        print(f"Lỗi khi tải hoặc đọc tệp: {e}")
        return

    print("\nĐang thực hiện lọc các cơn bão trong khu vực Biển Đông từ năm 1999 đến nay...")
    
    # 1. Ép kiểu dữ liệu tọa độ và thời gian
    df['LAT'] = pd.to_numeric(df['LAT'], errors='coerce')
    df['LON'] = pd.to_numeric(df['LON'], errors='coerce')
    df['SEASON'] = pd.to_numeric(df['SEASON'], errors='coerce')
    df['ISO_TIME'] = pd.to_datetime(df['ISO_TIME'], errors='coerce')
    
    # 2. Lọc theo không gian (Biển Đông Bounding Box: 0 - 25°N, 100 - 125°E) và thời gian (1999 - nay)
    df_scs = df[
        (df['SEASON'] >= 1999) &
        (df['LAT'] >= 0.0) & (df['LAT'] <= 25.0) &
        (df['LON'] >= 100.0) & (df['LON'] <= 125.0)
    ].copy()
    
    df_scs['NAME'] = df_scs['NAME'].fillna('UNNAMED')
    
    # 3. Gom nhóm theo Storm ID (SID) để tìm khoảng thời gian hoạt động của từng cơn bão
    storm_groups = df_scs.groupby('SID')
    
    storm_list = []
    for sid, group in storm_groups:
        name = group['NAME'].iloc[0]
        year = int(group['SEASON'].iloc[0])
        start_time = group['ISO_TIME'].min()
        end_time = group['ISO_TIME'].max()
        
        # Bổ sung biên 1 ngày trước và sau bão để lấy trọn vẹn chu kỳ hình thành và suy yếu
        padded_start = (start_time - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        padded_end = (end_time + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Tính số ngày hoạt động trong Biển Đông
        duration_days = (end_time - start_time).days + 1
        
        # Chỉ lấy các cơn bão có thời gian ghi nhận hợp lý
        if duration_days >= 1:
            storm_list.append({
                'SID': sid,
                'NAME': name,
                'YEAR': year,
                'START_DATE': padded_start,
                'END_DATE': padded_end,
                'DURATION_DAYS': duration_days
            })
            
    df_storms = pd.DataFrame(storm_list)
    df_storms = df_storms.sort_values(by=['YEAR', 'START_DATE']).reset_index(drop=True)
    
    print("\n--- THỐNG KÊ DANH SÁCH BÃO LỌC ĐƯỢC ---")
    print(f"Tổng số lượng áp thấp nhiệt đới và bão trên Biển Đông kể từ 1999: {len(df_storms)}")
    print(f"Số lượng bão trung bình mỗi năm: {len(df_storms) / (datetime.datetime.now().year - 1999 + 1):.1f}")
    
    print("\nHiển thị 15 cơn bão gần nhất:")
    print(df_storms.tail(15))
    
    # Lưu danh sách bão ra tệp CSV để sử dụng tiếp
    output_csv = os.path.join(BASE_DIR, "data", "scs_all_storms_1999_to_present.csv")
    df_storms.to_csv(output_csv, index=False)
    print(f"\nĐã lưu danh sách bão đầy đủ thành công tại: {output_csv}")

if __name__ == "__main__":
    main()
