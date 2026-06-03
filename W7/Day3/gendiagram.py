from diagrams import Cluster, Diagram
from diagrams.onprem.analytics import Flink
from diagrams.onprem.queue import Kafka
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.database import PostgreSQL
from diagrams.programming.language import Go

# Tên file xuất ra sẽ là "architecture.png"
with Diagram("Payment Anomaly Detection Pipeline", show=False, filename="architecture", direction="LR"):
    
    with Cluster("Service Layer"):
        service = Go("Payment API")

    with Cluster("Collection Layer"):
        # Dùng tạm icon Prometheus đại diện cho OTel SDK (do thư viện chưa có OTel)
        collector = Prometheus("OTel SDK")

    with Cluster("Transport Layer"):
        queue = Kafka("Kafka Buffer")

    with Cluster("Processing Layer"):
        engine = Flink("Flink Stateful")

    with Cluster("Storage Layer"):
        # Dùng icon DB đại diện cho VictoriaMetrics
        storage = PostgreSQL("VictoriaMetrics")

    with Cluster("Query & ML Layer"):
        dashboard = Grafana("Grafana Alert")

    # Mũi tên chỉ luồng dữ liệu
    service >> collector >> queue >> engine >> storage >> dashboard