# Báo Cáo Alert Correlation (AIOps W2-D1)

## 1. Lựa chọn tham số cấu hình

**Tại sao chọn `gap_sec = 30`?**
Tham số này tạo ra một "nhát cắt" thời gian hoàn hảo dựa trên dữ liệu thực tế. Cụ thể, cảnh báo của `recommender-svc` (lúc 09:45:10) cách đợt lỗi trước đó đúng 40 giây, và cách đợt lỗi sau 32 giây.
Với `gap_sec = 30`, hệ thống vừa đủ thời gian gom các lỗi lây lan liên tục, lại vừa kịp đóng phiên (vì $40s > 30s$) để cách ly thành công sự cố độc lập của `recommender-svc`. Nếu nới lỏng thành 45s hay 120s, các cảnh báo này sẽ bị gộp chung, dẫn đến gom nhầm tạp âm (Over-correlation).

**Tại sao chọn `max_hop = 2`?**
Mức 2 là điểm cân bằng lý tưởng để xử lý các kiến trúc giao tiếp bất đồng bộ:
- **Nếu nhỏ hơn (`hop = 1`):** Gây phân mảnh sự cố. Ví dụ `checkout` gọi `notification` thông qua hàng đợi `kafka-events` sẽ mất đúng 2 bước nhảy. Giới hạn 1 bước sẽ làm đứt gãy chuỗi domino này.
- **Nếu lớn hơn (`hop` $\ge 3$):** Gây hiệu ứng "Hố đen" (Blackhole effect). Các Hub Node hạ tầng (như Load Balancer hay DB dùng chung) sẽ vươn vòi quá xa, gom nhầm các dịch vụ không liên quan vào chung một rổ sự cố.

---

## 2. Hiệu suất và Xử lý ngoại lệ

**Có 1 alert ID không nằm trong cụm nào (bị "miss") — tại sao?**
Thực tế toàn bộ 20 alerts đều được gom cụm. Tuy nhiên, nếu xuất hiện alert bị "miss", nguyên nhân là do dịch vụ sinh ra nó chưa được khai báo trong bản đồ `services.json`. Lúc này, dịch vụ đó trở thành một "Node mồ côi" (Orphan Node), thuật toán không thể tìm thấy trên Service Graph để đo khoảng cách, dẫn đến việc bị loại bỏ khỏi các cụm.

**Nếu xử lý 10.000 alert thay vì 20, code sẽ bị chậm ở đâu?**
Nút thắt cổ chai nằm ở Layer 3 (Topology Grouping). Đoạn thuật toán lồng 2 vòng lặp để duyệt tìm đường đi ngắn nhất (`nx.shortest_path_length`) có độ phức tạp $O(N^2)$. Với 10.000 cảnh báo, số lượng cặp cần tính toán sẽ bùng nổ, vắt kiệt CPU.
- **Khắc phục:** Bắt buộc phải tính toán trước (pre-compute) toàn bộ ma trận khoảng cách của hệ thống và lưu vào bộ nhớ đệm (cache) ngay khi khởi động app.

---

## 3. Khái niệm cốt lõi (Short Answers)

**Vì sao fingerprint không bao gồm `timestamp` hay `value`?**
Thời gian và giá trị đo lường luôn biến động. Nếu đưa vào Fingerprint, mỗi lần hệ thống báo CPU 91% hay 95% ở các phút khác nhau đều sẽ bị xem là một sự cố mới. Loại bỏ hai trường này giúp Layer 1 (Dedup) gom gọn các thông báo lặp lại thành một sự cố duy nhất (kèm biến đếm `count`).

**Sự khác biệt giữa cảnh báo “duplicate” và “correlated”?**
- **Duplicate:** Cùng một lỗi lặp đi lặp lại trên cùng một dịch vụ (VD: hai alerts liên tiếp cùng báo full DB pool tại `payment-svc`).
- **Correlated:** Khác lỗi, khác dịch vụ nhưng chung nguyên nhân gốc (VD: `payment-svc` sập kéo theo `checkout-svc` bị báo lỗi timeout).

**Ảnh hưởng của việc điều chỉnh `gap_sec` (30 vs 600)?**
- **`gap_sec = 30`:** Giới hạn thời gian chặt chẽ, cắt lớp chính xác các đợt sóng lỗi dồn dập và cách ly tốt các sự cố độc lập.
- **`gap_sec = 600`:** Mở cửa sổ chờ quá lâu (10 phút), vơ vét bừa bãi mọi cảnh báo vào một cụm khổng lồ, làm tăng tỷ lệ báo động sai (False correlation).

**`recommender-svc` có bị gom vào cụm chính không? Vì sao?**
**Không.** Nó được tách riêng biệt ở cụm `c-001-000`.
*Lý do:* Cảnh báo của dịch vụ này cách chuỗi lỗi trước đó 40 giây. Nhờ cấu hình `gap_sec = 30` (nhỏ hơn 40s), Layer 2 đã kịp thời đóng nắp phiên sự cố đầu tiên, ngăn chặn hoàn toàn việc gom nhầm ở Layer 3.

**Hạn chế lớn nhất của Topology Grouping và hướng khắc phục?**
- **Hạn chế:** Dễ mắc bẫy Hub Node. Các dịch vụ trung tâm (Gateway, Load Balancer) kết nối với mọi nhánh, dễ trở thành cầu nối vô tình lôi kéo các sự cố độc lập gộp chung lại với nhau.
- **Khắc phục:** Loại bỏ hoàn toàn, hoặc gán trọng số phạt (weight) cực lớn cho các Hub Node hạ tầng này khi chạy thuật toán tìm đường đi ngắn nhất.
