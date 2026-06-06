# Detection Approach — DESIGN.md

## Approach tôi dùng
Hệ thống được thiết kế theo kiến trúc 3 lớp (3-Tier Architecture) kết hợp phân tích **Cross-Signal Analysis** (Metrics + Logs), bao gồm:
1. **Ingest Layer (Lớp Phễu Hứng):** Tiếp nhận dữ liệu Non-blocking.
2. **Stateful Math Layer (Lớp Toán Học & Trạng Thái):** Cập nhật các chỉ số toán học O(1) như **EWMA** và **Z-Score (Shifted Baseline)**.
3. **Rule Engine & Alerting Layer (Lớp Chẩn Đoán):** Chẩn đoán và kích hoạt cảnh báo dựa trên BVA và Alert Cooldown.

## Tại sao chọn approach này
- **Non-blocking processing:** Ingest Layer không thực hiện các tác vụ nặng như sleep hay file I/O đồng bộ. Mục tiêu là giữ latency thấp và tránh timeout từ phía Generator.
- **Độ phức tạp O(1) cho mỗi event:** Stateful Layer chỉ thực hiện tính toán và cập nhật trạng thái ngay khi có data rót xuống, không cần quét lại toàn bộ lịch sử.
- **Hạn chế Window Poisoning:** Bằng kỹ thuật Shifted Baseline (sử dụng `target_window` và `reference_window` tách biệt), hệ thống tránh được hiện tượng metric bất thường kéo lệch toàn bộ cửa sổ tính toán.

## Cách hoạt động

### 1. Ingest Layer (Lớp Phễu Hứng)
Lớp này là điểm tiếp nhận đầu tiên (FastAPI Endpoint `POST /ingest`), không lưu trạng thái (Stateless). Nó parse JSON payload thành `timestamp`, `metrics`, `logs` và chuyển ngay xuống các lớp dưới rồi trả về `200 OK`.

### 2. Stateful Math Layer (Lớp Toán Học & Trạng Thái)
Được thiết kế theo mẫu Singleton, duy trì bộ nhớ ngắn hạn của hệ thống:
- **Cập nhật EWMA:**
  $$EWMA_t = \alpha \cdot x_t + (1-\alpha) \cdot EWMA_{t-1}$$
- **Tính Z-Score (Shifted Baseline):**
  $$Z = \frac{x - \mu_{ref}}{\sigma_{ref}}$$
- **Trượt cửa sổ (Sliding Window):** Loại điểm dữ liệu cũ nhất khỏi `reference_window`, chuyển dữ liệu từ `target_window` sang `reference_window`, và đưa điểm dữ liệu mới vào `target_window`.

### 3. Rule Engine & Alerting Layer (Lớp Chẩn Đoán)
Bộ não nghiệp vụ kết hợp Metric và Log để đưa ra cảnh báo:
- **Memory Leak:** Kiểm tra `memory_usage_bytes` bám sát EWMA và Log chứa `"GC pause exceeded threshold"` hoặc `"OutOfMemoryWarning"`.
- **Traffic Spike / Dependency Timeout:** Kiểm tra Z-Score `> 3.0` kết hợp quét log (`"Queue depth high"` hoặc `"Circuit breaker OPEN"`).

## Parameters tôi chọn
- **Floating-Point Boundary Value Analysis (BVA):** Các threshold được thiết kế bằng số thực (ví dụ: `z_score > 3.0` hoặc `mem_ratio > 0.795`) thay vì số nguyên tuyệt đối để tránh sai lệch làm tròn.
- **Alert Cooldown (300s - 5 phút):** Sau khi cảnh báo sinh ra, hệ thống kích hoạt cooldown để giảm Alert Fatigue và tránh spam file `alerts.jsonl`.
- **Window Sizes:** `reference_window` = 20 điểm (~10 phút) để làm chuẩn, `target_window` = 2 điểm (~1 phút) để hứng biến động.

## Cải thiện nếu có thêm thời gian
- **Tối ưu Log Parsing:** Áp dụng thuật toán parse log chuyên sâu (ví dụ: Drain3) thay vì hardcode tìm kiếm chuỗi string thủ công.
- **Dynamic Thresholds:** Tự động điều chỉnh cấu hình Z-Score hoặc EWMA dựa trên chu kỳ ngày/đêm thay vì cố định các tham số ban đầu.
