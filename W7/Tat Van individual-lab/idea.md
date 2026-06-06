1. Tư duy đúng ở đây phải là Tư duy có trạng thái (Stateful) và Tương quan (Correlation):

    - Trend (Xu hướng): Thông số này đang cao lên từ từ hay đột ngột vọt lên? (Cần lưu lại lịch sử ngắn hạn - Sliding Window).
    - Noise (Nhiễu) vs Anomaly (Dị thường): Thông số này có vượt ra khỏi mức dao động bình thường không?
    - Metrics + Logs: Metrics báo hiệu có biến (sớm), Logs khẳng định chính xác biến đó là gì (muộn hơn nhưng chắc chắn). Phải kết hợp cả hai.

2. Mổ xẻ 3 loại "bệnh" (Faults) trong hệ thống

2.1. Memory Leak (Rò rỉ bộ nhớ):

    - Đặc điểm: Rất chậm và từ từ (Slow burn). RAM tăng liên tục không giảm. CPU và GC Pause sẽ tăng theo sau đó vì hệ thống phải liên tục dọn dẹp rác (Garbage Collection).
    - Logs: Ban đầu sẽ im ắng, lúc gần chết mới gào lên OutOfMemoryWarning hoặc GC pause exceeded.
    - Thách thức: Làm sao phát hiện sớm trước khi nó sập mà không bị nhầm lẫn với việc app dùng nhiều RAM bình thường?

2.2. Traffic Spike (Tăng vọt lưu lượng):

    - Đặc điểm: Đột ngột (Sudden surge). Lượng Request vọt lên x5, x8. Hàng đợi (Queue) nghẽn, độ trễ (Latency) tăng phi mã.
    - Thách thức: Generator có mô phỏng "chu kỳ ngày đêm" (buổi sáng/tối đông khách hơn). Làm sao phân biệt được đâu là "đông khách bình thường" và đâu là "bị DDoS / dồn traffic bất thường"?

2.3. Dependency Timeout (Lỗi từ dịch vụ phụ thuộc):

    - Đặc điểm: Dịch vụ bên thứ 3 (upstream) bị chậm/chết. Tỉ lệ timeout tăng vọt, kéo theo lỗi 5xx tăng. Sinh ra hiệu ứng phụ là Retries (client gọi lại nhiều lần) làm Queue đầy.
    - Logs: Sẽ có cảnh báo về timeout và Circuit breaker OPEN.

## Discuss:

Neu dung z-score --> mean, std tai X se cao --> zscore --> tang vot, nhung qua N-times, thi zscore se approach binh thuong --> not alert

y tuong: EWMA =  alpha * value_current + (1 - alpha) * EWMA_old
        MAD over z-score


## 1. Ingest Layer (Lớp Phễu Hứng)

Lớp này đóng vai trò là điểm tiếp nhận đầu tiên của toàn bộ pipeline, tương tự một **Receiver** hoặc **Controller Layer**. Mục tiêu chính là tiếp nhận dữ liệu nhanh nhất có thể và tránh làm gián đoạn luồng dữ liệu từ phía Generator.

### Thành phần chính

* FastAPI Endpoint: `POST /ingest`

### Dữ liệu nắm giữ

Lớp này **không lưu trạng thái (Stateless)**.

### Logic hoạt động

1. Nhận payload JSON từ stream generator.
2. Parse dữ liệu đầu vào.
3. Tách payload thành:

   * `timestamp`
   * `metrics` (dictionary)
   * `logs` (list)
4. Chuyển dữ liệu xuống Stateful Math Layer và Rule Engine Layer.
5. Trả về phản hồi:

```json
{
  "status": "ok"
}
```

### Design Principle

* Non-blocking processing.
* Không thực hiện các tác vụ nặng như:

  * Sleep
  * Database query
  * File I/O đồng bộ
  * Vòng lặp xử lý phức tạp

Mục tiêu là giữ latency thấp và tránh timeout từ phía Generator.

---

## 2. Stateful Math Layer (Lớp Toán Học & Trạng Thái)

Đây là lớp duy trì trạng thái (State) của hệ thống và thực hiện các phép tính thống kê theo thời gian thực.

### Thành phần chính

* Class `PipelineDetector` hoặc `StateTracker`
* Được khởi tạo duy nhất một lần (Singleton)

### Dữ liệu nắm giữ

* `ewma_memory` (float)
* `reference_window` (20 điểm dữ liệu ~ 10 phút)
* `target_window` (2 điểm dữ liệu ~ 1 phút)

### Logic hoạt động

#### 1. Cập nhật EWMA

Sử dụng công thức:

[
EWMA_t = \alpha \cdot x_t + (1-\alpha) \cdot EWMA_{t-1}
]

Trong đó:

* (x_t): giá trị metric hiện tại
* (\alpha): hệ số làm mượt

#### 2. Tính Z-Score (Shifted Baseline)

[
Z = \frac{x - \mu_{ref}}{\sigma_{ref}}
]

Trong đó:

* (x): metric hiện tại
* (\mu_{ref}): trung bình của `reference_window`
* (\sigma_{ref}): độ lệch chuẩn của `reference_window`

#### 3. Trượt cửa sổ (Sliding Window)

* Loại bỏ điểm dữ liệu cũ nhất khỏi `reference_window`
* Chuyển dữ liệu từ `target_window` sang `reference_window`
* Đưa điểm dữ liệu mới vào `target_window`

### Design Principle

* Chỉ thực hiện tính toán và cập nhật trạng thái.
* Không chứa logic cảnh báo.
* Độ phức tạp xử lý mỗi event là (O(1)).
* Hạn chế hiện tượng Window Poisoning bằng kỹ thuật Shifted Baseline.

---

## 3. Rule Engine & Alerting Layer (Lớp Chẩn Đoán)

Lớp này đóng vai trò là bộ não nghiệp vụ của hệ thống AIOps. Nó sử dụng các chỉ số toán học từ Stateful Layer kết hợp với log để xác định nguyên nhân bất thường và phát sinh cảnh báo.

### Thành phần chính

* Class `RuleEngine`
* File `alerts.jsonl`

### Dữ liệu nắm giữ

* `alert_cooldown`

  * Dictionary lưu timestamp của lần cảnh báo gần nhất
  * Dùng để chống spam alert

### Logic hoạt động

#### Memory Leak Detection

Điều kiện:

* `memory_usage_bytes` liên tục tăng và bám sát đường EWMA
* Log chứa:

  * `"GC pause exceeded threshold"`
  * `"OutOfMemoryWarning"`

Kết luận:

```text
Memory Leak Detected
```

#### Traffic Spike Detection

Điều kiện:

* `http_requests_per_sec` có:

```text
Z-Score > 3.0
```

* Đồng thời log chứa:

```text
Queue depth high
```

Kết luận:

```text
Traffic Spike Detected
```

### Floating-Point Boundary Value Analysis (BVA)

Các metric streaming là số thực (floating-point), do đó các ngưỡng phải được thiết kế dưới dạng số thực thay vì số nguyên tuyệt đối.

Ví dụ:

```python
if z_score > 3.0:
```

hoặc

```python
if deviation > 5.5:
```

Cách tiếp cận này giúp tránh sai lệch do làm tròn và phát hiện được các bất thường nhỏ nhưng có ý nghĩa.

### Alert Cooldown

Sau khi một cảnh báo được sinh ra, hệ thống sẽ kích hoạt cooldown trong khoảng 5–10 phút trước khi cho phép ghi lại cùng loại cảnh báo.

Mục tiêu:

* Giảm Alert Fatigue
* Tránh spam file `alerts.jsonl`
* Giúp người vận hành tập trung vào các sự cố thực sự quan trọng

### Output

Khi đủ điều kiện cảnh báo, hệ thống sẽ tạo một JSON Alert và append vào file:

```text
alerts.jsonl
```

Ví dụ:

```json
{
  "timestamp": "2026-06-03T10:00:00Z",
  "severity": "HIGH",
  "type": "Traffic Spike",
  "message": "Request rate increased significantly and queue depth is high."
}
```
