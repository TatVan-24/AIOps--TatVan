## Screenshot architecture diagram


## Bảng cost estimate (copy từ output cost_model.py)

| Tier   | Storage & Ingest   | Network (Kafka)   | Compute (Flink)   | Total BUILD (Self-host)   | Total BUY (Datadog SaaS)   |
|:-------|:-------------------|:------------------|:------------------|:--------------------------|:---------------------------|
| Small  | $800               | $1,000            | $500              | $2,300                    | $4,000                     |
| Medium | $8,000             | $2,500            | $1,200            | $11,700                   | $40,000                    |
| Large  | $80,000            | $25,000           | $12,000           | $117,000                  | $400,000                   |

## Tóm tắt ADR decision

Em chọn Kafka làm Transport Layer trong kiến trúc Anomaly Detection cho Payment Service. Vì Kafka sẽ đóng vai trò là Buffer giữa OpenTelemetry Collector và Flink Processing Engine, giúp tách biệt producer và consumer. So với việc đẩy dữ liệu trực tiếp vào storage, Kafka cung cấp khả năng replay dữ liệu, hỗ trợ nhiều consumer đọc cùng một stream và tăng khả năng mở rộng khi lưu lượng telemetry tăng cao.

## Reflection: nếu bạn được hire làm Platform Engineer cho startup 50-service vừa raise Series A, bạn sẽ recommend build hay buy? Tại sao?

**Bối cảnh:** Nếu được thuê làm Platform Engineer cho một startup có 50 services vừa raise được Series A.

**Đề xuất của em:** Ưu tiên chọn giải pháp **BUY** (mua SaaS như Datadog hoặc New Relic) thay vì tự **BUILD** (Self-host mã nguồn mở).

**Vì sao? - (Dựa trên Build vs Buy Framework):**
* **Thời gian đem lại giá trị (Time to first value):** Startup ở giai đoạn Series A cực kỳ cần tốc độ để chứng minh mô hình kinh doanh. Dùng Datadog chỉ mất **1-2 tuần** là hệ thống Observability đã chạy trơn tru, trong khi tự Build phải mất từ **3-6 tháng** setup và tinh chỉnh.
* **Nguồn lực nhân sự (Team need):** Giải pháp mua ngoài yêu cầu **0 dedicated SRE**, điều này cực kỳ quan trọng với team dev còn mỏng. Nếu tự Build, công ty sẽ phải tuyển và trả lương cho **2-3 SRE chuyên trách** chỉ để đi vận hành stack (giữ cho Kafka/Flink/DB không sập). Em muốn dồn toàn bộ chất xám của kỹ sư vào việc làm ra các core features cho Product thay vì đi "nuôi" hạ tầng.
* **Điểm rơi quy mô (Scale Economics):** Với quy mô 50 services (và công ty **< 500 engineers**), dù phí subscription của SaaS khá cao ($30-50K/tháng) so với phí server thuần túy ($10-15K/tháng), nhưng bù lại tiết kiệm được thời gian vận hành và chi phí quỹ lương cho SRE. Việc tự Build chỉ mang lại lợi ích kinh tế (scale economics) và khả năng tùy biến sâu (customization needs) khi công ty đã vươn tầm Big Tech (**> 1000 engineers**).