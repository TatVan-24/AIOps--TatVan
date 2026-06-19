# DESIGN.md — MLOps Lifecycle: Anomaly Detection Pipeline

## Tổng quan
Hệ thống MLOps Pipeline xử lý bài toán Anomaly Detection sử dụng mô hình IsolationForest. Quy trình bao gồm: theo dõi Data Drift & Concept Drift bằng Evidently, điều phối Retrain tự động chống quên kiến thức bằng kỹ thuật Sliding Window, và triển khai Zero-downtime qua MLflow Alias cùng với cơ chế Auto-Rollback nghiêm ngặt. Hệ thống bám sát hoàn toàn thiết kế được đề ra trong `implementation_plan.md`.

---

## Sub-checkpoint 1: Drift Threshold
**Công cụ và Threshold:** Sử dụng thư viện Evidently AI với `DataDriftPreset`.
**Lý do chọn:** Tỷ lệ `share_of_drifted_columns` được đo lường và có thể đẩy lên Prometheus (qua Pushgateway). Việc phát hiện sớm phân phối dữ liệu bị lệch (P(X) thay đổi) giúp kích hoạt quy trình huấn luyện lại trước khi mô hình đưa ra các dự đoán sai trên diện rộng. Khi chạy lệnh, Drift Score đạt 1.0 (100% features drifted), hệ thống nhận diện đây là tín hiệu cấp cứu và chuyển sang chạy Orchestrator (`retrain.py`).

---

## Sub-checkpoint 2: Loại Drift
**Loại được detect:** Data drift và Performance drift.
**Cách thức:** `DataDriftPreset` phân tích sự khác biệt thống kê trên các biến số đầu vào (latency_p99, error_rate, rps). 
**Tại sao phù hợp:** Trong các hệ thống giám sát, khi traffic thay đổi, baseline cũ không còn đúng. Model cần được cập nhật "bình thường mới". Hệ thống không chỉ đo Data Drift mà còn đo Concept Drift thông qua chế độ combined.

---

## Sub-checkpoint 3: Retrain Trigger Configuration
**Trigger type:** Manual Approval Gate (Cửa ải bán tự động).
**Cơ chế:** Trong kịch bản `retrain.py`, hệ thống dừng lại hiển thị lệnh chờ gõ `[y/N]` trên terminal.
**Lý do (Theo CTO mandate):** Một model tự động đẩy thẳng lên Production ẩn chứa rủi ro thảm họa. Approval gate bắt buộc kỹ sư ML phải xem xét các chỉ số đánh giá Holdout của bản `@staging` trước khi quyết định gõ `Y` để promote sang môi trường `@production`.

---

## Sub-checkpoint 4: Versioning và Rollback
**Chiến lược versioning:** Sử dụng MLflow Model Registry với thẻ trạng thái Alias (`@production`, `@staging`, `@archived`).
**Lợi ích:** API `serve.py` sử dụng *Lifespan Loading*, chỉ trỏ cứng vào đường dẫn `models:/anomaly-detector@production`. Nó không cần quan tâm version ID vật lý là số mấy.
**Rollback path (Trải nghiệm Zero-downtime):**
1. Khi có sự cố, hệ thống đổi thẻ `@production` về lại version v1 qua Mlflow Client.
2. Gắn thẻ `@archived` cho version v2.
3. Bắn lệnh `POST /reload` vào `serve.py`.
4. API tự động nạp lại v1 vào RAM mà không làm gián đoạn các Request khác.

---

## Kiến trúc component
```text
baseline.csv (reference)
     │
     ├──► pipeline.py ──► MLflow Run ──► Registry v1 @production
     │
drifted.csv (current window)
     │
     ├──► drift_detection.py (Push metrics)
     │         ▼
     └──► retrain.py (Orchestrator)
               │
               ├── Trộn Sliding Window (baseline + drifted)
               ├── Gọi pipeline.py -> Registry v2 @staging
               ├── Đánh giá Holdout
               ├── [APPROVAL GATE: y/N]
               ├── set alias production → v2
               ├── POST /reload → serve.py
               └── Giám sát 24 cycles (Auto-Rollback)
```

---

## Sub-checkpoint 5: Cơ chế phát hiện drift — tại sao cần combined mode
**Giải quyết Stress 1 (Concept Drift Trap):**
Chỉ dùng `DataDriftPreset` là quá nguy hiểm vì nó bị "mù" trước việc label bị lật ngược. Trong `drift_detection.py`, chúng ta hỗ trợ tham số `--check-mode combined` và `--labeled-current`. Lúc này, ngoài việc đo độ lật phân phối (X), script đo thêm độ tụt giảm của Precision (P(Y|X)). Nếu Precision giảm sốc, đó là cảnh báo Concept Drift và cần retrain ngay dù Data Drift score có nhỏ đi chăng nữa.

---

## Sub-checkpoint 6: Data selection strategy — sliding window vs alternatives
**Giải quyết Stress 2 (Catastrophic Forgetting - Mất trí nhớ):**
Nếu Orchestrator chỉ lấy mỗi tập dữ liệu `drifted.csv` để train, mô hình v2 sẽ mất khả năng nhận diện các cuộc tấn công/lỗi cơ bản thuộc vùng baseline cũ.
**Chiến lược Sliding Window:** `retrain.py` chủ động gộp cả `baseline.csv` và `drifted.csv` tạo thành file tạm `temp_train.csv`. Mô hình IsolationForest sẽ được rèn luyện để "không quên" quá khứ mà vẫn nắm bắt được hiện tại, duy trì hiệu năng cao trên tập kiểm định độc lập `holdout.csv`.

---

## Sub-checkpoint 7: Auto-rollback — threshold và policy
**Giải quyết Stress 3 (Tự phục hồi):**
Ngay cả khi con người gõ `Y` ở Approval Gate, sai lầm vẫn có thể xảy ra.
**Policy:** Cơ chế Post-deploy monitoring sẽ giả lập thời gian trôi qua với 24 chu kỳ (cycles) đánh giá liên tục trên tập `post_deploy_eval.csv`.
**Threshold:** Ngưỡng chịu đựng là `Precision < 0.65`.
**Hành động:** Chạm ngưỡng, script nổ chuông BÁO ĐỘNG, ngay lập tức hạ cấp v2 xuống `@archived`, khôi phục v1 lên `@production`, ép Server `/reload` và ghi chứng cứ vào file `outputs/audit_log.jsonl`.
