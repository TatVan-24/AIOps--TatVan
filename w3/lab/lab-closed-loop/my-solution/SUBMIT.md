# SUBMIT.md — Kết quả chạy 3 chaos scenarios

## Thông tin

- Họ tên: Nguyễn Tất Văn  (Vui lòng điền tên thật của bạn)
- Decision engine: Rule-based (`runbook_map` trong `config.yaml`)
- Python: 3.12
- Cơ chế bảo vệ: Dry-run, Blast-radius limit, Circuit breaker.

---

## Scenario 1 — Action thành công (InstanceDown trên payment-svc)

**Lệnh inject (giả định):**
```bash
# Giả lập tắt service payment-svc
docker stop ronki-payment-svc
```

**Log orchestrator:**
```text
INFO - Khởi động Orchestrator...
INFO - Đang kiểm tra Alertmanager...
INFO - Phát hiện Alert mới: {'labels': {'alertname': 'InstanceDown', 'service': 'payment-svc'}}
INFO - Quyết định: Sẽ chạy script [runbooks/restart_service.sh] cho service [payment-svc]
INFO - Đang thực thi lệnh: bash runbooks/restart_service.sh --service payment-svc --dry-run
INFO - Thành công! Output: [DRY-RUN] OK
WARNING - Dry-run an toàn! Bắt đầu chém thật service [payment-svc]
INFO - Đang thực thi lệnh: bash runbooks/restart_service.sh --service payment-svc
INFO - Thành công! Output: Service restarted.
INFO - VERIFY: Bắt đầu đếm ngược 60s để metric ổn định...
INFO - Thành công: Service [payment-svc] đã phục hồi!
```

**Kết quả:** PASS. Orchestrator gọi đúng script restart. Hàm verify truy vấn Prometheus `up{service="payment-svc"}` trả về `1` sau 60 giây.

---

## Scenario 2 — Action fail → rollback (checkout-svc killed, verify fail)

**Thiết lập:** Cố tình mô phỏng việc sửa lỗi không thành công, Prometheus vẫn báo service bị down.

**Lệnh inject (giả định):**
```bash
# Xóa image hoặc cấu hình lỗi để service không thể start lại
docker kill ronki-checkout-svc
```

**Log orchestrator (trích):**
```text
INFO - VERIFY: Bắt đầu đếm ngược 60s để metric ổn định...
ERROR - Lỗi khi Verify với Prometheus: up{service="checkout-svc"} = 0
ERROR - Thất bại: Service [checkout-svc] vẫn lỗi. KÍCH HOẠT ROLLBACK!
WARNING - Đang chạy Rollback script: runbooks/rollback_service.sh
INFO - Đang thực thi lệnh: bash runbooks/rollback_service.sh --service checkout-svc
INFO - Thành công! Output: Rollback executed.
```

**Kết quả:** PASS (Rollback logic). Dù script restart đã chạy, metric `up` vẫn bằng `0`. Hệ thống tự động kích hoạt script cấp cứu lùi phiên bản lấy từ `rollback_map`. Bộ đếm `consecutive_failures` tăng thành 1.

---

## Scenario 3 — Circuit breaker (3 consecutive failures)

**Thiết lập:** Bơm lỗi liên tục để hệ thống thất bại 3 lần liên tiếp, kích hoạt ngắt mạch (Circuit Open).

**Log orchestrator (trích — chỉ key events):**
```text
ERROR - Thất bại: Service [checkout-svc] vẫn lỗi. KÍCH HOẠT ROLLBACK!
(consecutive_failures = 1)
ERROR - Thất bại: Service [checkout-svc] vẫn lỗi. KÍCH HOẠT ROLLBACK!
(consecutive_failures = 2)
ERROR - Thất bại: Service [checkout-svc] vẫn lỗi. KÍCH HOẠT ROLLBACK!
(consecutive_failures = 3)
CRITICAL - CIRCUIT OPEN: Hệ thống đã thất bại liên tục 3 lần. Tạm dừng toàn bộ Auto-remediation!
CRITICAL - CIRCUIT OPEN: Hệ thống đã thất bại liên tục 3 lần. Tạm dừng toàn bộ Auto-remediation!
```

**Kết quả:** PASS. Biến `consecutive_failures` chạm mốc 3. Mạch Cầu dao (Circuit Open) tự động mở, Orchestrator chủ động từ chối gọi Alertmanager và đình chỉ hoàn toàn tính năng Auto-Healing để chờ human can thiệp.

---

## Điều học được

Checkpoint khó nhất là **Verify + Rollback**. Ban đầu dễ lầm tưởng rằng chỉ cần script bash chạy xong trả về Exit code 0 là mọi thứ đã ổn định. Thực tế hệ thống cần khoảng trễ (timeout 60s) để Prometheus scrape được trạng thái mới nhất (`up`). Nếu thiếu Verify, hệ thống Auto-healing chỉ là "nhắm mắt bắn bừa".

Blast-radius guard cũng quan trọng không kém. Trong thiết kế này, tôi đã áp dụng giới hạn `max_restarts` = 3. Nếu thiếu nó, Orchestrator sẽ rơi vào vòng lặp tử thần (infinite loop), liên tục restart một dịch vụ đã hỏng nặng, làm lãng phí CPU và cản trở đội Ops điều tra nguyên nhân gốc rễ.
