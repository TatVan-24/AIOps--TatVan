# DESIGN.md — Ronki Closed-Loop Orchestrator

## 1. Decision engine: Rule-based hay LLM-based?

**Chọn: Rule-based.**

Lý do: Orchestrator hiện tại sử dụng `config.yaml` chứa `runbook_map` để ánh xạ trực tiếp tên cảnh báo (alertname) với script khắc phục. Cách này cung cấp:
- **Độ trễ < 1ms:** Quyết định ngay lập tức trong bộ nhớ.
- **Tính tất định (Determinism) 100%:** Một lỗi nhất định luôn gọi đúng một script. 
- LLM-based không cần thiết ở giai đoạn này do số lượng kịch bản xử lý lỗi (runbooks) vẫn còn ít và cố định (`HighLatency`, `InstanceDown`, `HighErrorRate`).

## 2. Blast-radius config

```yaml
blast_radius:
  max_restarts_per_service_per_hour: 3
```

**Lý do chọn giá trị:**
- `max_restarts_per_service_per_hour: 3` — Nếu một dịch vụ bị khởi động lại quá 3 lần mà vẫn sập, chứng tỏ lỗi nằm ở tầng sâu hơn (ví dụ: mất kết nối DB, cấu hình sai) chứ không phải lỗi tạm thời. Việc tiếp tục restart là vô nghĩa và có nguy cơ làm chết chùm hệ thống (Cascading failure). 
- Khi vượt ngưỡng, hàm `check_blast_radius` trả về False, Orchestrator sẽ từ chối chạy script để chờ con người vào xử lý.

## 3. Verify step

**Metric kiểm tra:** Trạng thái `up` (1/0).

**Threshold & Timeout:**
- Sử dụng PromQL `up{service="X"}` để hỏi xem dịch vụ đã thực sự sống lại chưa.
- **Timeout (Chờ đợi):** `60` giây. Sau khi chạy script sửa lỗi, hệ thống bắt buộc ngủ 60s để chờ dịch vụ khởi động và Prometheus kịp cào (scrape) metric mới.
- **Min samples:** Hiện tại hệ thống chỉ lấy 1 sample `data[0]["value"][1]` sau khi hết 60s. Trong tương lai có thể nâng cấp lên 3 samples liên tiếp để tránh false positive.

## 4. Circuit breaker reset

**Reset mode: Manual (Thủ công).**

Lý do: Khi `consecutive_failures >= 3`, hệ thống in ra cảnh báo `CRITICAL` và đóng băng tính năng Auto-remediation (không gọi Alertmanager nữa). Đây là trạng thái thảm họa. Nếu hệ thống tự động reset sau vài phút, nó có thể gây ra một vòng lặp phá hoại vô tận. Việc yêu cầu con người vào can thiệp (Manual reset bằng cách khởi động lại script) là phương án an toàn nhất cho Production.

## 5. Mutex strategy (Stress 2 — concurrent alert race)

**Thiết kế hiện tại:** Sử dụng tập hợp `seen_fingerprints = set()` trong mỗi chu kỳ poll.

Lý do: Thay vì sử dụng `threading.Lock` phức tạp, hệ thống hiện tại chạy đơn luồng (single-thread) và lưu lại `fingerprint` của alert. Nếu cùng một alert bắn tới nhiều lần trong một vòng lặp, vòng lặp sẽ gạt bỏ qua các bản sao (duplicate). Điều này giải quyết một phần bài toán Race Condition ở mức cơ bản, tránh việc gọi cùng một script 2 lần liên tiếp cho cùng một lỗi.

## 6. Rollback chain ordering (Stress 1 — multi-step transactional deploy)

**Thiết kế hiện tại:** Ánh xạ Rollback đơn bước (1-1).

Hệ thống tra cứu `rollback_map` dựa trên `alertname` để tìm kịch bản cứu hộ (ví dụ `rollback_service.sh`). Hiện tại hệ thống thực thi lệnh rollback ngay lập tức khi verify thất bại. Tính năng Rollback đa bước (rollback-C -> rollback-B -> rollback-A) chưa được triển khai trong phiên bản này, nhưng logic `run_runbook` hiện tại đủ linh hoạt để gọi một chuỗi script nếu được bổ sung.

## 7. Lý do chọn metrics cho observability

**Thiết kế hiện tại:** Sử dụng Python `logging` module.

Trong phiên bản này, Observability được thiết kế theo hướng Log-driven thay vì Metric-driven. Các sự kiện quan trọng như `BLAST RADIUS`, `CIRCUIT OPEN`, `ROLLBACK` được xuất thẳng ra Terminal dưới dạng log mức độ `WARNING` hoặc `CRITICAL`. Mặc dù chưa có Prometheus exporter cho riêng Orchestrator, nhưng các log này đủ để kỹ sư truy vết (Trace) nguyên nhân gốc rễ trong vòng chưa tới 1 phút.

## 8. Decision validation policy (Stress 3 — LLM hallucination defense)

**Thiết kế hiện tại:** An toàn tuyệt đối (Không bị Hallucination).

Vì chúng ta sử dụng Rule-based Engine (`runbook_map.get()`), giá trị trả về luôn luôn nằm trong danh sách đã được định nghĩa cứng ở `config.yaml`. Do đó, hệ thống miễn nhiễm hoàn toàn với lỗi "Hallucination" (bịa ra tên script không tồn tại) của LLM. Kể cả khi có lỗi typo trong cấu hình, cơ chế `dry_run=True` của Bash script cũng sẽ chặn đứng lệnh thực thi trước khi OS bị ảnh hưởng.
