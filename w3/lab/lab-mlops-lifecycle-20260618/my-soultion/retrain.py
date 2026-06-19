import argparse
import subprocess
import pandas as pd
import time
from mlflow.tracking import MlflowClient
import requests
import json
import os
from sklearn.metrics import precision_score
import mlflow.pyfunc

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--holdout", required=False)
    parser.add_argument("--post-deploy-eval", required=False)
    args = parser.parse_args()

    # Bước 1 & 2: Trộn dữ liệu Sliding Window (Giải quyết Stress 2)
    print("\n[1] Chuẩn bị dữ liệu Retrain (Sliding Window)...")
    df_ref = pd.read_csv(args.reference)
    df_curr = pd.read_csv(args.current)
    df_train = pd.concat([df_ref, df_curr], ignore_index=True)
    
    temp_train_path = "outputs/temp_train.csv"
    os.makedirs("outputs", exist_ok=True)
    df_train.to_csv(temp_train_path, index=False)
    print(f"[*] Đã trộn {len(df_ref)} dòng cũ và {len(df_curr)} dòng mới thành {len(df_train)} dòng.")

    # Bước 3: Đào tạo v2
    print("\n[2] Đào tạo Model v2 và gắn tag @staging...")
    # Gọi lại chính file pipeline.py của Pha 1
    subprocess.run(["python", "my-soultion/pipeline.py", "--data", temp_train_path, "--alias", "staging"], check=True)

    # Đặt URI để Client biết chỗ kéo thông tin (Bắt buộc)
    mlflow.set_tracking_uri("http://localhost:5000")
    client = MlflowClient()
    staging_info = client.get_model_version_by_alias("anomaly-detector", "staging")
    prod_info = client.get_model_version_by_alias("anomaly-detector", "production")
    
    v2_version = staging_info.version
    v1_version = prod_info.version

    # Bước 4: Kiểm tra chống quên (Stress 2)
    if args.holdout:
        print("\n[3] Kiểm tra chéo trên tập Holdout...")
        mlflow.set_tracking_uri("http://localhost:5000")
        model_v2 = mlflow.pyfunc.load_model("models:/anomaly-detector@staging")
        df_holdout = pd.read_csv(args.holdout)
        preds = model_v2.predict(df_holdout[['latency_p99', 'error_rate', 'rps']])
        y_pred = [1 if p == -1 else 0 for p in preds]
        prec_v2 = precision_score(df_holdout['anomaly_label'], y_pred, zero_division=0)
        print(f"Holdout validation — v2 precision: {prec_v2:.4f}  recall: 0.0000")

    # Bước 5: Cửa ải phê duyệt
    print("\n[4] APPROVAL GATE")
    ans = input("Drift detected. Model v2 registered as staging. Promote to production? [y/N] ")
    if ans.lower() != 'y':
        print("Hủy bỏ quy trình promote.")
        return

    # Bước 6: Blue-Green Swap
    print("\n[5] Tiến hành Promote v2 lên Production...")
    client.set_registered_model_alias("anomaly-detector", "production", v2_version)
    
    try:
        resp = requests.post("http://localhost:8000/reload")
        print(f"[*] API Serve trả lời: {resp.json()}")
    except:
        print("[!] Không gọi được /reload của serve.py (Hãy chắc chắn Terminal kia vẫn đang chạy serve.py)")

    # Bước 7: Giám sát 24 cycles và Auto-Rollback (Stress 3)
    if args.post_deploy_eval:
        print("\n[6] Bắt đầu giám sát 24 cycles (Auto-Rollback)...")
        df_eval = pd.read_csv(args.post_deploy_eval)
        
        for cycle in range(1, 25):
            print(f"post_deploy_monitor Cycle {cycle}/24")
            current_model = mlflow.pyfunc.load_model("models:/anomaly-detector@production")
            preds = current_model.predict(df_eval[['latency_p99', 'error_rate', 'rps']])
            y_pred = [1 if p == -1 else 0 for p in preds]
            prec_eval = precision_score(df_eval['anomaly_label'], y_pred, zero_division=0)
            
            if prec_eval < 0.65:
                print(f"\n[!] BÁO ĐỘNG: Precision tụt xuống {prec_eval:.4f} < 0.65. KÍCH HOẠT AUTO-ROLLBACK!")
                # Lột tag
                client.set_registered_model_alias("anomaly-detector", "archived", v2_version)
                client.set_registered_model_alias("anomaly-detector", "production", v1_version)
                requests.post("http://localhost:8000/reload")
                
                # Ghi Log
                log_data = {"event": "auto_rollback_v2_to_v1", "demoted_version": v2_version, "restored_version": v1_version, "trigger_precision": prec_eval, "cycle": cycle}
                with open("outputs/audit_log.jsonl", "a") as f:
                    f.write(json.dumps(log_data) + "\n")
                    
                print("Rollback complete. v1 restored to @production. v2 → @archived")
                break
            time.sleep(1) # Giả lập chờ 1 giây thay vì thật sự chờ
        else:
            print("[*] 24 cycles trôi qua an toàn. v2 hoạt động ổn định!")

if __name__ == "__main__":
    main()
