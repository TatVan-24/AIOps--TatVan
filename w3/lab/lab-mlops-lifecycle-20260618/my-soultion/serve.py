from fastapi import FastAPI
from pydantic import BaseModel
import mlflow.pyfunc
from mlflow.tracking import MlflowClient
from prometheus_client import make_asgi_app, Histogram, Counter, Gauge
import pandas as pd
import time

app = FastAPI()

REQUEST_COUNT = Counter('serve_request_total', 'Total /predict requests')
PREDICT_LATENCY = Histogram('serve_predict_latency_seconds', 'Latency of /predict')
ACTIVE_VERSION = Gauge('serve_active_version', 'Current model version loaded')

model = None
current_version = "unknown"

def load_model():
    """Hàm thò tay vào MLflow kéo Model đang mang tag @production"""
    global model, current_version
    mlflow.set_tracking_uri("http://localhost:5000")
    model_uri = "models:/anomaly-detector@production"
    
    print(f"[*] Đang kéo model từ: {model_uri}")
    model = mlflow.pyfunc.load_model(model_uri)
    
    client = MlflowClient()
    alias_info = client.get_model_version_by_alias("anomaly-detector", "production")
    current_version = alias_info.version
    ACTIVE_VERSION.set(float(current_version))
    print(f"[*] Đã nạp thành công Version {current_version} vào bộ nhớ.")

load_model()

app.mount("/metrics", make_asgi_app())

class PredictRequest(BaseModel):
    features: list[float]  # Cần 3 thông số: latency_p99, error_rate, rps

@app.post("/predict")
def predict(req: PredictRequest):
    REQUEST_COUNT.inc()
    start_time = time.time()
    
    # Đóng gói 3 số người dùng gửi thành DataFrame
    input_df = pd.DataFrame([req.features], columns=['latency_p99', 'error_rate', 'rps'])
    
    # Dự đoán (-1 là Bất thường, 1 là Bình thường)
    pred = model.predict(input_df)[0]
    
    PREDICT_LATENCY.observe(time.time() - start_time)
    
    return {
        "prediction": int(pred),
        "version": current_version
    }

@app.get("/health/active-version")
def get_version():
    return {"active_version": current_version}

@app.post("/reload")
def reload_model():
    print("[*] Nhận lệnh RELOAD. Đang nạp lại model...")
    load_model()
    return {"status": "success", "new_version": current_version}
