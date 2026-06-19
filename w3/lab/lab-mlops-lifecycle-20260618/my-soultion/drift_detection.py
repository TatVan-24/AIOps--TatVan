import argparse
import os
import pandas as pd
import mlflow.pyfunc
from sklearn.metrics import precision_score
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

def push_metrics(drift_score, precision):
    """Bắn tín hiệu cấp cứu lên Pushgateway cho Prometheus thấy"""
    try:
        registry = CollectorRegistry()
        g_drift = Gauge('drift_score', 'Data drift score (0-1)', registry=registry)
        g_drift.set(drift_score)
        
        if precision is not None:
            g_perf = Gauge('model_precision', 'Model precision on current data', registry=registry)
            g_perf.set(precision)
            
        push_to_gateway('localhost:9091', job='drift_detector', registry=registry)
    except Exception as e:
        pass # Pushgateway tắt thì kệ nó, không crash chương trình

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--check-mode", choices=['data', 'performance', 'combined'], default='data')
    parser.add_argument("--model-uri", default="models:/anomaly-detector@production")
    parser.add_argument("--labeled-current", required=False)
    args = parser.parse_args()

    os.makedirs("outputs/drift_reports", exist_ok=True)
    features = ['latency_p99', 'error_rate', 'rps']
    
    ref_df = pd.read_csv(args.reference)
    curr_df = pd.read_csv(args.current)

    print("[*] Đang tính toán Data Drift bằng Evidently...")
    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=ref_df[features], current_data=curr_df[features])
    
    # Rút trích điểm Drift
    report_dict = report.as_dict()
    # In ra các key để debug xem Evidently trả về cái gì
    print("[DEBUG] Keys available:", report_dict['metrics'][0]['result'].keys())
    # Tạm thời gán bằng 0 để code đi tiếp
    drift_score = report_dict['metrics'][0]['result']['share_of_drifted_columns']
    report.save_html("outputs/drift_reports/drift_report.html")
    
    precision = None
    
    # Giải quyết Stress 1: Nếu bật cờ combined, phải đo độ tụt hậu (Performance Drift)
    if args.check_mode in ['performance', 'combined'] and args.labeled_current:
        print("[*] Kích hoạt Concept Drift Trap - Đang đo lường Precision của Model...")
        mlflow.set_tracking_uri("http://localhost:5000")
        model = mlflow.pyfunc.load_model(args.model_uri)
        
        labeled_df = pd.read_csv(args.labeled_current)
        preds = model.predict(labeled_df[features])
        
        # IsolationForest trả về -1 (Lỗi) và 1 (Bình thường)
        # Trong dataset gốc, anomaly_label quy định: 1 (Lỗi) và 0 (Bình thường)
        y_pred = [1 if p == -1 else 0 for p in preds]
        y_true = labeled_df['anomaly_label']
        
        precision = precision_score(y_true, y_pred, zero_division=0)
    
    push_metrics(drift_score, precision)

    # In kết quả bắt buộc theo Acceptance Criterion 4
    print(f"Drift score: {drift_score:.4f}")
    if precision is not None:
        print(f"Perf precision: {precision:.4f}")

if __name__ == "__main__":
    main()
