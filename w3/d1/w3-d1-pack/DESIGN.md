## 1. SLI choice cho frontend. Tại sao chọn metric X thay vì Y? Frontend RUM cho 4 candidate signal (page load time, DOM ready, JS error rate, network error rate). Chọn cái nào, vì sao loại 3 cái còn lại?

Em chọn kết hợp cả ***dom_ready<3000ms, js_error=false, network_error=false*** vì:

    - page load time: phải chờ tải toàn bộ source ảnh/video do đó sẽ mất thời gian 
    - dom ready: thì chỉ cần phân tích xong file HTML, do đó sẽ nhanh hơn

## 2. SLO target cho api. Tại sao 99.9% chứ không 99% hoặc 99.99%? Cost của mỗi tier (§3.2) so với baseline hiện tại 99.7% (từ baseline.json).

SLO_spec cho API em chọn 98%, nhưng qua thực nghiệm thì thấy không ổn theo kết quả:
```
"static_baseline": {
    "fired": 4,
    "tp": 3,
    "fp": 1,
    "fn": 0,
    "mttd_p50_s": 0
  }
  ```

  | Mục tiêu (SLO) | Quỹ Lỗi (Events/Tháng) | Downtime/Tháng (Phút) | Yêu cầu Kiến trúc & Chi phí (Cost Ladder) |
|---------------|-----------------------:|----------------------:|--------------------------------------------|
| 98.0% | 414,756 | 864 phút (~14.4 giờ) | 1 Server đơn giản. Sập thì khởi động lại bằng tay (Manual Recovery). Chi phí rất thấp. |
| 99.0% | 207,378 | 432 phút (~7.2 giờ) | Vẫn có thể dùng 1 Instance, phục hồi thủ công. Chi phí thấp. |
| 99.9% | 20,737 | 43.2 phút | Cần nhiều Server (Multi-Instance), có Load Balancer, tự động chuyển đổi dự phòng (Auto-Failover). |
| 99.95% | 10,368 | 21.6 phút | Mức chuẩn rất cao, thường dành cho các hệ thống nền tảng cốt lõi như Database hoặc Core Services. |
| 99.99% | 2,073 | 4.32 phút | Chạy đa vùng (Multi-AZ), tự động hóa gần như 100%, đội ngũ SRE trực 24/7. Chi phí tăng 3–10 lần so với mức 99.9%. |


## 3. Latency threshold p99. Bạn cut latency ở mốc nào (200ms? 500ms? 1s?)? Plot distribution latency 7-day (text/table OK), defend choice.

Trong baseline.json thì "latency_p99_ms": 156 và set threshold ở mức 500ms vì:

    - tránh false alert
    - SLO của Frontend (DOM Ready) yêu cầu hoàn thành dưới 3000ms. Nếu API được phép trễ tới 1000ms hay 2000ms, trình duyệt sẽ không kịp render, dẫn đến vi phạm SLO tổng.

## 4. 4xx exclusion. Tại sao loại 4xx ra khỏi error count (trừ 429)? Có log endpoint nào có rate 4xx > 5% mà không phải hệ thống lỗi không? Reference data.

Lý do loại trừ: Các mã 4xx (400, 401, 404) là lỗi xuất phát từ phía người dùng (Client gõ sai URL, nhập sai mật khẩu). Đây không phải lỗi hệ thống, nếu tính vào sẽ làm trừ oan Error Budget. Ngoại lệ là 429 (Too Many Requests) - cần giữ lại vì nó báo hiệu server đang quá tải và từ chối phục vụ.

## 5. MWMBR tuning. Dùng Google default (14.4, 6, 1) hay tune? Nếu tune, dựa vào ảnh hưởng đến noise_reduction_pct và fn thế nào?
Em giữ nguyên hệ số mặc định của Google (14.4, 6, 1). Với SLO 98% (ngân sách lỗi lớn), việc validation_report.json báo fn: 3 (bỏ qua 3 sự cố) là tính năng, không phải lỗi. Các sự cố giả lập quá ngắn (8-10 phút), tiêu thụ không đáng kể Error Budget.
