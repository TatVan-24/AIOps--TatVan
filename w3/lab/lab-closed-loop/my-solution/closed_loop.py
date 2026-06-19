import time
import requests
import yaml
import json
import logging
import subprocess # Nhớ thêm dòng này lên đầu file

def run_runbook(script_path, service, dry_run=True):
    """
    Thực thi một bash script dưới OS.
    Trả về True nếu thành công (Exit code 0), False nếu thất bại.
    """
    # 1. Lắp ráp câu lệnh mảng (an toàn hơn ghép chuỗi)
    # Ví dụ: bash runbooks/restart_service.sh --service payment-svc
    cmd = ["bash", script_path, "--service", service]
    
    # 2. Cơ chế an toàn Dry-run
    if dry_run:
        cmd.append("--dry-run")
        
    logging.info(f"Đang thực thi lệnh: {' '.join(cmd)}")
    
    try:
        # 3. Bắn lệnh xuống OS, cài đặt thời gian chờ tối đa (timeout)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
        
        # 4. Kiểm tra mã lỗi trả về từ OS
        if result.returncode == 0:
            logging.info(f"Thành công! Output: {result.stdout.strip()}")
            return True
        else:
            logging.error(f"Thất bại! Mã lỗi: {result.returncode}, Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        logging.error(f"Thảm họa: Script [{script_path}] bị treo quá 30 giây!")
        return False
    except Exception as e:
        logging.error(f"Lỗi hệ thống khi gọi subprocess: {e}")
        return False

# Cấu hình logging cơ bản
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_config(path="config.yaml"):
    with open(path, "r", encoding='utf-8') as f:
        return yaml.safe_load(f)

def fetch_active_alerts(alertmanager_url):
    """
    TODO 1: Viết hàm gọi API Alertmanager để lấy danh sách các Alert đang báo lỗi.
    Gợi ý: 
    - Gọi GET request tới: {alertmanager_url}/api/v2/alerts
    - Thêm query parameters: ?active=true&silenced=false&inhibited=false
    - Trả về danh sách JSON chứa các alerts. Nếu lỗi thì trả về [] (list rỗng).
    """
    try:
        url = f"{alertmanager_url}/api/v2/alerts"
        params = {"active": "true", "silenced": "false", "inhibited": "false"}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        return response.json()

    except Exception as e:
        return []

def decide_runbook(alert, config):
    # 1. Trích xuất nhãn (labels). Dùng .get() để chống lỗi nếu gói tin bị rỗng
    labels = alert.get("labels", {})
    
    # 2. Lấy tên lỗi và tên service
    alertname = labels.get("alertname", "Unknown")
    service = labels.get("service", labels.get("job", "Unknown"))
    
    # 3. Lấy bản đồ runbook từ config
    runbook_map = config.get("runbook_map", {})
    
    # 4. Tra cứu xem lỗi này thì dùng script nào
    runbook_script = runbook_map.get(alertname)
    
    # 5. Trả về kết quả
    if runbook_script:
        return service, runbook_script
    else:
        logging.warning(f"Cảnh báo: Không tìm thấy kịch bản sửa lỗi cho Alert: {alertname}")
        return None

# Biến toàn cục lưu số lần đã restart của mỗi service (Lưu ý: Cách này dễ mất trí nhớ nếu OOM)
restart_counters = {}

def check_blast_radius(service, limit):
    """
    Kiểm tra xem service đã bị đấm (restart) quá số lần cho phép chưa.
    Trả về True nếu còn trong giới hạn, False nếu đã vượt ngưỡng.
    """
    count = restart_counters.get(service, 0)
    if count >= limit:
        logging.critical(f"BLAST RADIUS: Service [{service}] đã bị restart {count} lần. Bỏ qua để tránh sập dây chuyền!")
        return False
    
    # Nếu an toàn, tăng biến đếm lên 1
    restart_counters[service] = count + 1
    return True

def verify_service(prometheus_url, service, timeout_s=60):
    logging.info(f"VERIFY: Bắt đầu đếm ngược {timeout_s}s để metric ổn định...")
    time.sleep(timeout_s) # Chờ Prometheus cào metric mới
    
    query = f'up{{service="{service}"}}'
    url = f"{prometheus_url}/api/v1/query"
    params = {"query": query}
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        # Bóc tách JSON
        response_json = response.json()
        data = response_json.get("data", {}).get("result", [])
        
        # Nếu mảng rỗng -> Không lấy được trạng thái -> Mặc định là Chết
        if not data:
            return False
            
        # Giá trị trả về nằm ở value[1]. Ví dụ: [1700000000, "1"]
        status_value = data[0]["value"][1]
        
        if status_value == "1":
            return True   # Khỏe
        else:
            return False  # Vẫn chết
            
    except Exception as e:
        logging.error(f"Lỗi khi Verify với Prometheus: {e}")
        return False



def main():
    config = load_config()
    logging.info("Khởi động Orchestrator...")
    
    # Tập hợp (set) để nhớ những alert đã xử lý trong vòng lặp này, tránh xử lý trùng.
    seen_fingerprints = set()

    consecutive_failures = 0
    while True:

        if consecutive_failures >= config["circuit_breaker"]["consecutive_failure_threshold"]:
            logging.critical("CIRCUIT OPEN: Hệ thống đã thất bại liên tục 3 lần. Tạm dừng toàn bộ Auto-remediation!")
            time.sleep(config["poll_interval_seconds"])
            continue # Nhảy qua vòng lặp, không gọi API Alertmanager nữa

        logging.info("Đang kiểm tra Alertmanager...")
        
        # Gọi hàm lấy alerts
        alerts = fetch_active_alerts(config["alertmanager_url"])
        
        # Nếu chưa viết code ở hàm fetch_active_alerts, alerts sẽ là None. Cần check.
        if alerts:
            for alert in alerts:
                fingerprint = alert.get("fingerprint", "")
                
                # Nếu đã xử lý rồi thì bỏ qua
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                
                logging.info(f"Phát hiện Alert mới: {alert}")
                
                # Quyết định hành động
                # 1. Quyết định hành động (Decide)
                decision = decide_runbook(alert, config)

                if decision:
                    # Lấy thông tin từ decision
                    service, runbook = decision
                    
                    # Bóc tách thêm alertname để dành lát nữa gọi Rollback
                    alertname = alert.get("labels", {}).get("alertname", "Unknown")

                    # 2. Kiểm tra khiên bảo vệ
                    limit = config["blast_radius"]["max_restarts_per_service_per_hour"]
                    check_blast = check_blast_radius(service, limit)
                    
                    if check_blast:
                        logging.info(f"Quyết định: Sẽ chạy script [{runbook}] cho service [{service}]")
                        
                        dry_run_success = run_runbook(runbook, service, dry_run=True)
                        
                        if dry_run_success:
                            # 3. Hành động thật (Act)
                            logging.warning(f"Dry-run an toàn! Bắt đầu chém thật service [{service}]")
                            run_runbook(runbook, service, dry_run=False)
                            
                            # 4. KÍCH HOẠT PHASE 3: Đặt khối Verify & Rollback Ở ĐÂY
                            # Chờ 60s và kiểm tra lại
                            is_healthy = verify_service(config["prometheus_url"], service)
                            
                            if is_healthy:
                                logging.info(f"Thành công: Service [{service}] đã phục hồi!")
                            else:
                                logging.error(f"Thất bại: Service [{service}] vẫn lỗi. KÍCH HOẠT ROLLBACK!")
                                consecutive_failures += 1
                                
                                # Tìm đường dẫn script Rollback dựa vào biến alertname vừa lấy ở trên
                                rollback_script = config.get("rollback_map", {}).get(alertname)
                                if rollback_script:
                                    logging.warning(f"Đang chạy Rollback script: {rollback_script}")
                                    # Thực thi Rollback 
                                    run_runbook(rollback_script, service, dry_run=False)
                        else:
                            logging.error("Dry-run thất bại, từ chối chạy thật!")

                                
        time.sleep(config["poll_interval_seconds"])

if __name__ == "__main__":
    main()




# import time
# import requests
# import yaml
# import json
# import logging

# # Cấu hình logging cơ bản
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# def load_config(path="config.yaml"):
#     with open(path, "r") as f:
#         return yaml.safe_load(f)

# def fetch_active_alerts(alertmanager_url):
#     """
#     TODO 1: Viết hàm gọi API Alertmanager để lấy danh sách các Alert đang báo lỗi.
#     Gợi ý: 
#     - Gọi GET request tới: {alertmanager_url}/api/v2/alerts
#     - Thêm query parameters: ?active=true&silenced=false&inhibited=false
#     - Trả về danh sách JSON chứa các alerts. Nếu lỗi thì trả về [] (list rỗng).
#     """
#     pass

# def decide_runbook(alert, config):
#     """
#     TODO 2: Từ gói tin Alert (JSON), tìm xem nó bị lỗi gì (alertname) và ở đâu (service).
#     Sau đó đối chiếu với runbook_map trong config để tìm script phù hợp.
    
#     Gợi ý:
#     - Lấy `alertname` từ: alert["labels"]["alertname"]
#     - Lấy `service` từ: alert["labels"]["service"] (hoặc "job")
#     - Trả về 2 giá trị: (service_name, runbook_script)
#     """
#     pass

# def main():
#     config = load_config()
#     logging.info("Khởi động Orchestrator...")
    
#     # Tập hợp (set) để nhớ những alert đã xử lý trong vòng lặp này, tránh xử lý trùng.
#     seen_fingerprints = set()

#     while True:
#         logging.info("Đang kiểm tra Alertmanager...")
        
#         # Gọi hàm lấy alerts
#         alerts = fetch_active_alerts(config["alertmanager_url"])
        
#         # Nếu chưa viết code ở hàm fetch_active_alerts, alerts sẽ là None. Cần check.
#         if alerts:
#             for alert in alerts:
#                 fingerprint = alert.get("fingerprint", "")
                
#                 # Nếu đã xử lý rồi thì bỏ qua
#                 if fingerprint in seen_fingerprints:
#                     continue
#                 seen_fingerprints.add(fingerprint)
                
#                 logging.info(f"Phát hiện Alert mới: {alert}")
                
#                 # Quyết định hành động
#                 decision = decide_runbook(alert, config)
#                 if decision:
#                     service, runbook = decision
#                     logging.info(f"Quyết định: Sẽ chạy script [{runbook}] cho service [{service}]")
                    
#                     # TODO 3: [Sẽ làm ở Phase 2] Chạy thử lệnh bash (Dry-run)
                    
#         time.sleep(config["poll_interval_seconds"])

# if __name__ == "__main__":
#     main()
