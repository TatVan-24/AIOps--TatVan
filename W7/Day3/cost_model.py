import pandas as pd
from streamlit import metric
from sympy import sec

tiers = {
    "Small": {"services": 10, "log_volume": 50, "events_per_sec": "100K"},
    "Medium": {"services": 100, "log_volume": 500, "events_per_sec": "1M"},
    "Large": {"services": 1000, "log_volume": 5000, "events_per_sec": "10M"}
}

def compute_cost(tier_name, parms):
    ratio = parms['services'] / 100

    kafka_cost = max(1000, 2500 * ratio) ## $2,500 is kafka cost for 100K msg/sec
    flink_cost = max (500, 1200 * ratio) ## $1,200 is flink cost for 100K msg/sec

    build_costs = {
        "Metric (VictoriaMetrics)": 2000 * ratio,
        "Log (Loki + S3)": 4500 * ratio,
        "Trace (Jaeger)": 1500 * ratio,
        "Transport (Kafka)": kafka_cost,
        "Compute (Flink)": flink_cost,
    }

    total_cost = sum(build_costs.values())

    total_buy = 40000 * ratio

    return {
        "Tier": tier_name,
        "Storage & Ingest": f"${build_costs['Metric (VictoriaMetrics)'] + build_costs['Log (Loki + S3)'] + build_costs['Trace (Jaeger)'] :,.0f}",
        "Network (Kafka)": f"${build_costs['Transport (Kafka)'] :,.0f}",
        "Compute (Flink)": f"${build_costs['Compute (Flink)'] :,.0f}",
        "Total BUILD (Self-host)": f"${total_cost :,.0f}",
        "Total BUY (Datadog SaaS)": f"${total_buy :,.0f}"
    }


cost_data = [compute_cost(name, params) for name, params in tiers.items()]
df_costs = pd.DataFrame(cost_data)

print(f'Complete to predict the cost')
print(df_costs.to_markdown(index=False))