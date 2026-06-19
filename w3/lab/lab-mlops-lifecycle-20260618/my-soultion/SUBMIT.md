# SUBMIT.md — Reflection: MLOps Lifecycle Lab

## Câu 1: Drift threshold bạn chọn là bao nhiêu và tại sao?
Dựa theo chiến lược triển khai trong `implementation_plan.md`, thư viện Evidently AI được sử dụng để theo dõi `share_of_drifted_columns`. Khi chạy kịch bản thực tế với tập `drifted.csv`, hệ thống báo cáo Drift Score = 1.0000 (100% đặc trưng bị lật phân phối). Điểm số tuyệt đối này chứng tỏ dữ liệu đang đi lệch hoàn toàn so với baseline, do đó nó vượt qua mọi ngưỡng an toàn thông thường (dù thiết lập ở mức 0.15 hay 0.5) và là tín hiệu cấp bách yêu cầu phải kích hoạt `retrain.py` ngay lập tức.

---

## Câu 2: Điều gì xảy ra nếu model v2 sau retrain lại tệ hơn v1?
Căn cứ vào bản thiết kế, quy trình giải quyết 3 bài toán Stress Test đã dựng sẵn 2 lớp khiên bảo vệ kiên cố:
1. **Lớp 1 - Chốt chặn thủ công (Approval Gate):** Sau khi v2 được train và gắn tag `@staging`, `retrain.py` sẽ tự động tính toán điểm trên tập `holdout.csv`, sau đó hiển thị màn hình chờ `[y/N]`. Nếu nhận thấy v2 quá tồi, kỹ sư gõ `N` từ chối promote, hệ thống hủy quy trình.
2. **Lớp 2 - Auto-Rollback (Stress 3):** Nếu kỹ sư duyệt nhầm (gõ `Y`), mô hình lên `@production`. Vòng lặp giám sát giả lập 24 cycles sẽ bắt đầu đo đạc trên `post_deploy_eval.csv`. Khi phát hiện Precision rớt dưới ngưỡng 0.65, nó lập tức gỡ tag `@production` khỏi v2 trả cho v1, gọi API `/reload` trên `serve.py` để khôi phục dịch vụ mà không cần sự can thiệp của con người, đồng thời lưu log bằng chứng sự cố.

---

## Câu 3: Sự khác biệt giữa data drift và concept drift?
- **Data drift (P(X) thay đổi):** Sự phân phối của các biến đầu vào bị thay đổi. `drift_detection.py` giải quyết tốt vấn đề này thông qua `DataDriftPreset` của Evidently bằng các phép thử thống kê.
- **Concept drift (P(Y|X) thay đổi):** Các biến không thay đổi nhưng hành vi (ý nghĩa của lỗi) bị lật (Giải quyết Stress 1: Concept Drift Trap). Hệ thống giải pháp được đề xuất áp dụng cờ `--check-mode combined`, đo song song độ giảm sút của Precision trên tập `labeled-current` để không bị mù trước sự sai lệch của nhãn mà Data Drift thông thường không nhìn thấy.

---

## Câu 4: Tại sao blue-green swap quan trọng hơn replace file trực tiếp?
Nếu thực hiện việc ghi đè trực tiếp lên file mô hình `.pkl`, Server FastAPI `serve.py` đang xử lý các Request dở dang sẽ dính lỗi đọc file (corrupted) làm sập hệ thống (downtime). Tệ hơn, ta mất luôn bản backup của file cũ nên không thể cứu vãn.
Với **Blue-green deployment qua MLflow**, ta quản lý bằng Alias ảo. Cả v1 và v2 đều nằm song song an toàn trên server MLflow. Khi `retrain.py` đẩy lệnh `/reload`, cơ chế Lifespan của FastAPI nạp file mô hình v2 âm thầm vào một vùng RAM độc lập, khi xong xuôi mới chuyển luồng yêu cầu sang, đảm bảo ứng dụng cập nhật trong im lặng (**Zero-downtime**). Quá trình Rollback đổi Alias chỉ tốn < 5 giây.

---

## Câu 5: Nếu automate approval gate, dùng metric gì và threshold nào?
Để vượt qua cửa ải Approval Gate tự động hoàn toàn thay vì chờ gõ `[y/N]`, hệ thống cần đảm bảo đã khắc phục triệt để hội chứng "Mất trí nhớ" (Catastrophic Forgetting - Stress 2). 
Metric quan trọng nhất là **Precision trên tập Holdout**. Việc sử dụng Sliding Window (trộn dữ liệu) làm nền tảng, hệ thống tự động sẽ đối chiếu Precision của v2 với v1. 
- Ngưỡng Threshold: `v2_precision >= v1_precision` (Tuyệt đối không tệ hơn gốc) hoặc độ lệch `Delta < 0.05` và `v2_precision > 0.8`.
Chỉ khi đáp ứng được tiêu chí này, thuật toán điều phối mới tự động lật Alias sang `@production` và đẩy API `/reload`.
