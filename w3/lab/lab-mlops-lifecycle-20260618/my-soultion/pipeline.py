import argparse
import pandas as pd
import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from sklearn.ensemble import IsolationForest

def main():
    parser = argparse.ArgumentParser(description="Train and register Anomaly Detection Model")
    parser.add_argument("--data", type=str, required=True, help="Path to training data CSV")
    parser.add_argument("--alias", type=str, default="production", help="Alias to assign in MLflow Registry")
    args = parser.parse_args()

    features = ['latency_p99', 'error_rate', 'rps']

    print(f"[*] Đang nạp dữ liệu từ {args.data}...")
    df = pd.read_csv(args.data)
    X = df[features]

    contamination = 0.05
    n_estimators = 100
    random_state = 42

    model = IsolationForest(
        contamination=contamination,
        n_estimators=n_estimators,
        random_state=random_state
    )

    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment("anomaly_detection_lifecycle")

    with mlflow.start_run() as run:
        print("[*] Đang train model IsolationForest...")
        model.fit(X)

        preds = model.predict(X)
        train_anomaly_rate = (preds == -1).sum() / len(preds)
        print(f"[*] Train Anomaly Rate: {train_anomaly_rate:.4f}")

        mlflow.log_param("contamination", contamination)
        mlflow.log_param("n_estimators", n_estimators)
        mlflow.log_metric("train_anomaly_rate", train_anomaly_rate)

        model_name = "anomaly-detector"
        print(f"[*] Đang đăng ký model với tên '{model_name}'...")
        
        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=model_name
        )
        
        client = MlflowClient()
        # Trong MLflow 2.13.2, ta cần dùng search_model_versions để tìm version vừa tạo
        versions = client.search_model_versions(f"run_id='{run.info.run_id}'")
        version = versions[0].version
        print(f"[*] Gắn thẻ '@{args.alias}' cho Version {version}...")
        client.set_registered_model_alias(model_name, args.alias, version)
        
        print(f"[*] HOÀN THÀNH! Run ID: {run.info.run_id}")

if __name__ == "__main__":
    main()
