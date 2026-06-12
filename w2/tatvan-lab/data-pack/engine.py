# File: engine.py
import argparse
import json
import yaml
from datetime import datetime, timezone
from features import extract_features
from retrieval import retrieve_and_vote
from decisions import select_action  

def main():
    parser = argparse.ArgumentParser(description="Evidence-Driven Remediation Engine")
    parser.add_argument("command", choices=["decide"], help="Lệnh thực thi")
    parser.add_argument("--incident", required=True, help="Đường dẫn đến file Live Incident")
    parser.add_argument("--history", required=True, help="Đường dẫn đến file History")
    parser.add_argument("--actions", required=True, help="Đường dẫn đến file Actions Catalog")
    
    args = parser.parse_args()
    
    if args.command == "decide":
        with open(args.incident, 'r') as f:
            live_incident = json.load(f)
            
        with open(args.history, 'r') as f:
            history_data = json.load(f)
            
        with open(args.actions, 'r') as f:
            actions_catalog = yaml.safe_load(f)
            
        incident_id = live_incident.get('incident_id', 'UNKNOWN_INCIDENT')
        
        # 3. THỰC THI QUA 3 LAYER
        
        # Layer 1: Lọc rác (Trích xuất đặc trưng)
        live_vector = extract_features(live_incident)
        
        # Layer 2: Tìm hàng xóm & Bầu chọn
        retrieval_result = retrieve_and_vote(live_vector, history_data, top_k=3)
        
        # Layer 3: Cổng gác an toàn (Quyết định)
        decision = select_action(retrieval_result, actions_catalog)
        
        # 4. Đóng gói Output theo chuẩn của Autograder
        audit_record = {
            "incident_id": incident_id, # Lưu ý: nhớ thêm .split('-')[0] ở dòng 29 để ID là E01 chứ không phải E01-2026...
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "selected_action": decision["selected_action"],
            "params": decision["params"],
            "confidence": decision["confidence"],
            "top_3_neighbors": decision["top_3_neighbors"],
            "consensus_score": decision["consensus_score"],
            "blast_radius_check": decision["blast_radius_check"]
        }
        
        # 5. Ghi nối (Append) vào file audit.jsonl
        audit_file = "audit.jsonl"
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_record, ensure_ascii=False) + "\n")
            
                # In ra màn hình chuẩn System Log
        print(f"[SUCCESS] Xử lý xong: {incident_id}")
        print(f"  - Lệnh chốt: {decision['selected_action']}")
        print(f"  - Độ tự tin: {decision['confidence'] * 100:.1f}%")
        print(f"  - Lý do: {decision['blast_radius_check']}\n")

if __name__ == "__main__":
    main()
