# BÁO CÁO KẾT QUẢ TÌM HIỂU (FINDINGS)

**Dự án:** Evidence-Driven Remediation Engine (AIOps)

---

## 1. Quyết định Thiết kế & Trích xuất Đặc trưng (Feature Engineering)

### Xử lý Nhiễu Logs

Thách thức lớn nhất của hệ thống là log chứa rất nhiều tham số thay đổi liên tục như:

- User ID
- IP Address
- Timestamp
- UUID

Giải pháp được áp dụng là sử dụng **Regular Expression (Regex)** để che mờ (mask) các giá trị động thành các token chuẩn hóa:

```text
12345        → <NUM>
192.168.1.1  → <IP>
550e8400...  → <UUID>
```

Nhờ vậy, các log có cùng ý nghĩa nhưng khác giá trị cụ thể sẽ được gom nhóm thành các **Log Signatures** thống nhất, giúp tăng hiệu quả truy vấn và giảm nhiễu trong dữ liệu.

### Nhận diện Nút thắt cổ chai (Bottleneck Detection)

Thay vì phụ thuộc hoàn toàn vào các Alert (vốn có thể bị ảnh hưởng bởi hiện tượng cascading failure), hệ thống ưu tiên phân tích:

- Distributed Traces
- Metrics

Thông qua các ngưỡng động như:

```text
Error Rate > 5%
P99 Latency > 1000ms
```

Từ đó xác định chính xác Service gốc rễ gây ra sự cố thay vì chỉ nhìn vào các cảnh báo phát sinh phía sau.

---

## 2. Thuật toán Truy vấn (Retrieval)

### Sử dụng Jaccard Similarity thay vì Cosine Similarity

Các đặc trưng được trích xuất từ sự cố bao gồm:

- Log Signatures
- Failing Traces
- Error Patterns

Các đặc trưng này có bản chất là các **tập hợp rời rạc (Sets)** thay vì vector liên tục.

Do đó, hệ thống sử dụng:

```text
Jaccard Similarity
```

thay vì:

```text
Cosine Similarity
```

Jaccard được lựa chọn vì:

- Tính toán nhanh trên dữ liệu dạng tập hợp
- Phản ánh chính xác mức độ giao nhau giữa các đặc trưng
- Hoạt động hiệu quả với dữ liệu sparse

### Thuật toán k-Nearest Neighbors

Hệ thống cấu hình:

```text
K = 3
```

cho thuật toán k-Nearest Neighbors (k-NN).

Lý do lựa chọn:

- Đảm bảo có đủ dữ liệu lịch sử để tạo đồng thuận (Consensus)
- Tránh bị ảnh hưởng bởi các sự cố quá khác biệt
- Giảm nguy cơ overfitting vào một trường hợp duy nhất

---

## 3. Ra quyết định & Cơ chế An toàn (Safety Gates)

Hệ thống không thực hiện hành động tự động một cách mù quáng mà phải vượt qua ba lớp kiểm tra an toàn.

### 3.1. Kiểm tra Out-of-Distribution (OOD Check)

Nếu độ tương đồng cao nhất giữa sự cố hiện tại và dữ liệu lịch sử nhỏ hơn:

```text
Similarity < 0.15
```

hệ thống kết luận đây là một sự cố hoàn toàn mới.

Khi đó:

```text
Action = page_oncall
```

Thay vì cố gắng đưa ra quyết định thiếu cơ sở.

Mục tiêu là ngăn chặn việc AI đưa ra các hành động nguy hiểm trong các tình huống chưa từng gặp.

---

### 3.2. Đánh giá Độ Tự Tin (Confidence Check)

Hệ thống chỉ cho phép tự động xử lý khi:

```text
Confidence > 0.5
```

Điều này đồng nghĩa với việc các sự cố tương tự trong lịch sử đã tạo được mức đồng thuận đủ cao về cách khắc phục.

Nếu không đạt ngưỡng:

```text
Action = page_oncall
```

---

### 3.3. Phân tích Phạm vi Ảnh hưởng (Blast Radius Analysis)

Mỗi hành động đều được đánh giá mức độ rủi ro trước khi thực thi.

Ví dụ:

- Restart Service
- Rollback Deployment
- Scale Infrastructure

Các hành động có phạm vi ảnh hưởng lớn hoặc chi phí cao sẽ yêu cầu mức độ tin cậy cao hơn.

Nếu không đáp ứng điều kiện an toàn:

```text
Action = page_oncall
```

Thay vì tự động thực thi.

---

## 4. Kết quả Thực nghiệm & Thông số Chạy Thực Tế

Hệ thống đã được kiểm thử trên:

```text
8 kịch bản sự cố
(E01 → E08)
```

và cho thấy khả năng ra quyết định dựa trên bằng chứng một cách linh hoạt.

---

### E01 – Tự động xử lý thành công

Kết quả truy vấn lịch sử tạo ra mức đồng thuận:

```text
Confidence = 53.6%
```

Hành động được lựa chọn:

```text
rollback_service
```

Đồng thời:

```text
Blast Radius = 1
```

cho thấy rủi ro thấp và nằm trong giới hạn cho phép.

Kết quả:

```text
Auto Remediation Executed
```

---

### E03, E04, E08 – Phát hiện Sự cố Lạ (OOD)

Các sự cố này không có điểm tương đồng đáng kể với dữ liệu lịch sử.

Kết quả:

```text
Confidence ≈ 0%
```

Hệ thống xác định đây là các trường hợp Out-of-Distribution (OOD).

Do đó:

```text
Action = page_oncall
```

Thay vì cố gắng suy đoán phương án xử lý.

---

### E05 – Chặn bởi Safety Gate

Dữ liệu lịch sử trả về nhiều phương án xử lý mâu thuẫn.

Kết quả:

```text
Confidence = 42.6%
```

Mức này thấp hơn ngưỡng:

```text
50%
```

nên hệ thống từ chối tự động xử lý.

Quyết định cuối cùng:

```text
Action = page_oncall
```

---

### Đánh giá bởi Autograder

Hệ thống được kiểm tra thông qua file:

```text
audit.jsonl
```

Log kiểm toán đáp ứng đầy đủ các yêu cầu về tính minh bạch và khả năng giải thích quyết định.

Các trường quan trọng bao gồm:

```json
{
  "top_3_neighbors": [],
  "consensus_score": 0.0,
  "blast_radius_check": true
}
```

Nhờ đó hệ thống đạt:

```text
50 / 85 điểm
```

ngay từ vòng đánh giá cấu trúc tĩnh (Static Evaluation).

---

## Kết luận

Evidence-Driven Remediation Engine đã chứng minh khả năng:

- Chuẩn hóa và giảm nhiễu dữ liệu log hiệu quả.
- Truy xuất sự cố tương tự bằng phương pháp dựa trên bằng chứng.
- Đưa ra quyết định thông qua cơ chế đồng thuận và các lớp Safety Gates.
- Từ chối hành động trong các trường hợp chưa đủ cơ sở dữ liệu hoặc có mức rủi ro cao.
- Đảm bảo tính minh bạch thông qua hệ thống audit log có khả năng giải thích quyết định.

Cách tiếp cận này giúp cân bằng giữa:

```text
Automation
        và
Operational Safety
```

để hỗ trợ vận hành hệ thống AIOps trong môi trường thực tế.