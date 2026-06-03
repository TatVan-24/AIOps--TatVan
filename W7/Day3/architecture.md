## Anomaly detection trên payment service  

Workflow:
```
[Service] → [Collection] → [Transport] → [Processing] → [Storage] → [Query/AI]
```

Trong đó :

    +  **Service*: em dùng tool **Payment API** vì ``` nơi sinh ra data(tốc độ xử lí đơn, số lượng đơn thành công/thất bại, etc.).
    +  **Collection**: em chọn tool **OTel SDK** vì nó sẽ ``` embedded trực tiếp vào service```
    + **Transport**: em dùng **Kafka** vì nó sẽ là ```cầu nối lưu trữ giữa data và storage, tránh làm cho hệ thống break khi lượng traffic tăng đột biến.```
    + **Processing**: em dùng **Flink** vì ```Stateful streaming --> lưu trữ data trong quá khứ, exactly-once semantics vì là payment nên yêu cầu nó phải chính xác```
    + **Storage**: em chọn **VictoriaMetric** vì ```scale tốt hơn 10x, retention nhiều tháng/năm```
    + **Query/ML**: em chọn **Grafana + ML model** vì ```Grafana cho việc dashboard và model ML giúp detect```