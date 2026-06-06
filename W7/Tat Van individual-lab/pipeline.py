import json
import math
import time
from collections import deque
from fastapi import FastAPI, Request
import uvicorn

# ==========================================
# LAYER 2: STATEFUL MATH LAYER
# ==========================================
class MetricTracker:
    """Theo dõi Z-score với kỹ thuật Shifted Baseline (O(1) updates)"""
    def __init__(self, ref_size=20, target_size=2):
        self.ref_size = ref_size
        self.target_size = target_size
        self.ref_window = deque(maxlen=ref_size)
        self.target_window = deque(maxlen=target_size)
        
        # Biến duy trì O(1) cho Mean và Variance
        self.ref_sum = 0.0
        self.ref_sum_sq = 0.0

    def update_and_get_zscore(self, value: float) -> float:
        value = float(value)
        z_score = 0.0

        # Tính Z-score dựa trên reference_window HIỆN TẠI (trước khi nhận data mới)
        n = len(self.ref_window)
        if n > 1:
            mean = self.ref_sum / n
            variance = (self.ref_sum_sq / n) - (mean ** 2)
            # Tránh chia cho 0 bằng BVA
            std_dev = math.sqrt(variance) if variance > 1e-9 else 1e-9
            z_score = abs(value - mean) / std_dev

        # Trượt cửa sổ (Sliding Window)
        self.target_window.append(value)

        # Đẩy dữ liệu cũ nhất từ target sang reference
        if len(self.target_window) == self.target_size:
            oldest_target = self.target_window[0]
            
            # Nếu reference đầy, nhả điểm cũ nhất ra khỏi các biến tổng O(1)
            if len(self.ref_window) == self.ref_size:
                oldest_ref = self.ref_window.popleft()
                self.ref_sum -= oldest_ref
                self.ref_sum_sq -= (oldest_ref ** 2)

            # Nạp target cũ vào reference
            self.ref_window.append(oldest_target)
            self.ref_sum += oldest_target
            self.ref_sum_sq += (oldest_target ** 2)

        return z_score

class StateTracker:
    """Singleton duy trì trạng thái toàn hệ thống"""
    def __init__(self):
        self.ewma_memory = None
        self.alpha = 0.05  # Nhớ lâu để bắt memory leak chậm
        
        # Trackers cho các metric đột ngột
        self.req_tracker = MetricTracker(ref_size=20, target_size=2)
        self.timeout_tracker = MetricTracker(ref_size=20, target_size=2)
        
    def process(self, metrics: dict) -> dict:
        # 1. Update EWMA (O(1))
        mem_val = float(metrics.get("memory_usage_bytes", 0))
        if self.ewma_memory is None:
            self.ewma_memory = mem_val
        else:
            self.ewma_memory = self.alpha * mem_val + (1.0 - self.alpha) * self.ewma_memory

        # 2. Update Z-scores (O(1))
        req_val = float(metrics.get("http_requests_per_sec", 0))
        req_z = self.req_tracker.update_and_get_zscore(req_val)

        timeout_val = float(metrics.get("upstream_timeout_rate", 0))
        timeout_z = self.timeout_tracker.update_and_get_zscore(timeout_val)

        return {
            "ewma_memory": self.ewma_memory,
            "req_z": req_z,
            "timeout_z": timeout_z
        }

# ==========================================
# LAYER 3: RULE ENGINE & ALERTING LAYER
# ==========================================
class RuleEngine:
    def __init__(self, alert_file="alerts.jsonl"):
        self.alert_file = alert_file
        self.cooldowns = {}
        self.cooldown_seconds = 300  # 5 phút chặn spam

    def _can_alert(self, fault_type: str, current_time: float) -> bool:
        """Cơ chế Alert Cooldown"""
        if fault_type in self.cooldowns:
            if current_time - self.cooldowns[fault_type] < self.cooldown_seconds:
                return False
        return True

    def _fire_alert(self, fault_type: str, severity: str, message: str, timestamp_str: str, current_time: float):
        """Ghi JSON ra file alerts.jsonl"""
        alert = {
            "timestamp": timestamp_str,
            "type": fault_type,
            "severity": severity,
            "message": message
        }
        with open(self.alert_file, "a") as f:
            f.write(json.dumps(alert) + "\n")
        self.cooldowns[fault_type] = current_time
        print(f"[ALERT FIRED] {fault_type} | {message}")

    def evaluate(self, timestamp_str: str, metrics: dict, logs: list, stats: dict):
        current_time = time.time()
        
        # Gom message log lại để search keyword cho lẹ
        log_text = " | ".join([log.get("message", "") for log in logs])

        # --- Rule 1: Memory Leak ---
        mem_val = float(metrics.get("memory_usage_bytes", 0))
        mem_limit = float(metrics.get("memory_limit_bytes", 2000000000))
        mem_ratio = mem_val / mem_limit
        
        # Sử dụng BVA trên số thực (float)
        has_mem_log = "GC pause exceeded threshold" in log_text or "OutOfMemoryWarning" in log_text
        if mem_ratio > 0.795 and has_mem_log:
            if self._can_alert("memory_leak", current_time):
                msg = f"Memory usage at {mem_ratio*100:.1f}%. Log evidence found."
                self._fire_alert("memory_leak", "critical", msg, timestamp_str, current_time)

        # --- Rule 2: Traffic Spike ---
        req_z = stats.get("req_z", 0.0)
        has_queue_log = "Queue depth high" in log_text or "server overloaded" in log_text
        if req_z > 3.0 and has_queue_log:
            if self._can_alert("traffic_spike", current_time):
                msg = f"Request rate Z-score: {req_z:.2f}. Queue depth is high."
                self._fire_alert("traffic_spike", "critical", msg, timestamp_str, current_time)

        # --- Rule 3: Dependency Timeout (Bonus từ Generator) ---
        timeout_z = stats.get("timeout_z", 0.0)
        has_timeout_log = "Upstream timeout rate" in log_text or "Circuit breaker OPEN" in log_text
        if timeout_z > 3.0 and has_timeout_log:
            if self._can_alert("dependency_timeout", current_time):
                msg = f"Upstream timeout Z-score: {timeout_z:.2f}. Breaker OPEN."
                self._fire_alert("dependency_timeout", "critical", msg, timestamp_str, current_time)

# ==========================================
# LAYER 1: INGEST LAYER (FASTAPI)
# ==========================================
app = FastAPI()
state_tracker = StateTracker()
rule_engine = RuleEngine()

@app.post("/ingest")
async def ingest_endpoint(request: Request):
    """Điểm tiếp nhận Non-blocking O(1)"""
    try:
        payload = await request.json()
        timestamp = payload.get("timestamp")
        metrics = payload.get("metrics", {})
        logs = payload.get("logs", [])

        # 1. State update
        stats = state_tracker.process(metrics)

        # 2. Cross-signal correlation & Alerting
        rule_engine.evaluate(timestamp, metrics, logs, stats)

        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)