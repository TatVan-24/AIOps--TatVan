import sys
import pandas as pd
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

def parse_logs(logfile):
    config = TemplateMinerConfig()
    config.drain_sim_th = 0.4 
    config.drain_depth = 4
    miner = TemplateMiner(config=config)

    log_entries = []
    total_lines = 0

    with open(logfile, 'r', encoding='utf-8') as file:
        for line in file:
            line = file.strip()

            total_lines += 1
            parts = line.split()

            if len(parts) >= 2:
                raw_time = f"{parts[0]} {parts[1]}"
                try:
                    timestamp = pd.to_datetime(raw_time, format='%y%m%d %H%M%S')
                except ValueError:
                    timestamp = pd.NaT 
                
                result = miner.add_log_message(line)
                template_id = f"T-{result['cluster_id']}"
                
                if pd.notna(timestamp):
                    log_entries.append({'timestamp': timestamp, 'template_id': template_id})
    return log_entries, miner, total_lines

def print_basic_stats_and_top5(miner, total_lines):
    clusters = miner.drain.clusters
    
    print("\n" + "="*40)
    print("="*40)
    print(f"- Tổng số dòng log: {total_lines}")
    print(f"- Số template duy nhất (Unique): {len(clusters)}")
    
    print("\nTOP 5 TEMPLATES XUẤT HIỆN NHIỀU NHẤT:")
    sorted_clusters = sorted(clusters, key=lambda x: x.size, reverse=True)
    for i, cluster in enumerate(sorted_clusters[:5]):
        pct = (cluster.size / total_lines) * 100
        print(f"  {i+1}. [T-{cluster.cluster_id}] (Count: {cluster.size} | {pct:.1f}%)")
        print(f"     => {cluster.get_template()}")

def detect_anomalies_last_hour(log_entries):
    df = pd.DataFrame(log_entries)
    if df.empty:
        print("Không có dữ liệu thời gian hợp lệ để phân tích Time Series.")
        return
        
    max_time = df['timestamp'].max()
    cutoff_time = max_time - pd.Timedelta(hours=1)
    
    past_df = df[df['timestamp'] < cutoff_time]
    recent_df = df[df['timestamp'] >= cutoff_time]
    
    print("\n" + "="*40)
    print(f" PHÂN TÍCH ANOMALY 1 GIỜ GẦN NHẤT")
    print(f"    ({cutoff_time}  ->  {max_time})")
    print("="*40)
    
    past_templates = set(past_df['template_id'].unique())
    recent_templates = set(recent_df['template_id'].unique())
    new_templates = recent_templates - past_templates
    
    print("[*] NEW TEMPLATES (Hành vi hoàn toàn mới):")
    if new_templates:
        for t in new_templates:
            print(f"  Cảnh báo: {t} vừa xuất hiện lần đầu tiên!")
    else:
        print("  Không phát hiện template lạ.")
        
    print("\n[*] SPIKING TEMPLATES (Tăng vọt bất thường):")
    if not past_df.empty and not recent_df.empty:
        # Group window 5 phút
        past_ts = past_df.groupby([pd.Grouper(key='timestamp', freq='5min'), 'template_id']).size().unstack(fill_value=0)
        recent_ts = recent_df.groupby([pd.Grouper(key='timestamp', freq='5min'), 'template_id']).size().unstack(fill_value=0)
        
        spikes_found = False
        for template in recent_ts.columns:
            if template in past_ts.columns:
                past_mean = past_ts[template].mean()
                past_std = past_ts[template].std()
                
                if past_std > 0:
                    max_recent = recent_ts[template].max() 
                    z_score = (max_recent - past_mean) / past_std
                    
                    if z_score > 3:
                        print(f"  {template}: Số lượng đạt {max_recent} (Trung bình cũ: {past_mean:.1f} | Z-Score: {z_score:.1f}σ)")
                        spikes_found = True
                        
        if not spikes_found:
            print(" Các template cũ vẫn hoạt động trong ngưỡng an toàn.")
    else:
        print(" Không đủ dữ liệu để so sánh quá khứ và hiện tại.")
    print("\n" + "="*40 + "\n")

def main():
    if len(sys.argv) < 2:
        print("LỖI: Chưa truyền file log!")
        print("Sử dụng: python log_analyzer.py <đường_dẫn_file_log>")
        sys.exit(1)
        
    logfile = sys.argv[1]
    print(f"\nBẮT ĐẦU PHÂN TÍCH: {logfile}...")
    
    log_entries, miner, total_lines = parse_logs(logfile)
    
    if total_lines == 0:
        print("File log trống hoặc không đọc được.")
        sys.exit(1)
        
    print_basic_stats_and_top5(miner, total_lines)
    detect_anomalies_last_hour(log_entries)

if __name__ == "__main__":
    main()