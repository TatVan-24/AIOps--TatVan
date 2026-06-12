# File: retrieval.py

def jaccard_sim(list1: list, list2: list) -> float:
    """Hàm tính Jaccard: Độ trùng lặp giữa 2 mảng (Giao chia Hợp)"""
    set1, set2 = set(list1), set(list2)
    if not set1 and not set2: return 1.0 # Cả 2 đều rỗng -> Giống hệt nhau
    if not set1 or not set2: return 0.0  # 1 cái rỗng, 1 cái có -> Khác hoàn toàn
    return len(set1 & set2) / len(set1 | set2)

def calculate_similarity(vec_live: dict, vec_hist: dict) -> float:
    """Tính điểm giống nhau (0.0 -> 1.0) giữa sự cố Live và 1 sự cố History"""
    
    # 1. So sánh Dịch vụ bị ảnh hưởng (Trọng số 0.3)
    sim_svc = jaccard_sim(
        vec_live.get('affected_services', []), 
        vec_hist.get('affected_services', [])
    )
    
    # 2. So sánh Metrics (Trọng số 0.2)
    # Nối tên service và metric lại (VD: t24-service_db_pool_used) để so sánh
    mets_live = [f"{m['service']}_{m['metric']}" for m in vec_live.get('metric_signatures', [])]
    mets_hist = [f"{m['service']}_{m['metric']}" for m in vec_hist.get('metric_signatures', [])]
    sim_metrics = jaccard_sim(mets_live, mets_hist)
    
    # 3. So sánh Traces (Trọng số 0.2)
    traces_live = [f"{t['from']}->{t['to']}" for t in vec_live.get('trace_signatures', [])]
    traces_hist = [f"{t['from']}->{t['to']}" for t in vec_hist.get('trace_signatures', [])]
    sim_traces = jaccard_sim(traces_live, traces_hist)

    # 4. So sánh Logs (Trọng số 0.3)
    # Đập vỡ tất cả các câu log thành từng từ đơn lẻ để tìm tỷ lệ trùng từ vựng
    live_words = " ".join(vec_live.get('log_signatures', [])).lower().split()
    hist_words = " ".join(vec_hist.get('log_signatures', [])).lower().split()
    sim_logs = jaccard_sim(live_words, hist_words)
    
    # Tổng điểm
    return (0.3 * sim_svc) + (0.2 * sim_metrics) + (0.2 * sim_traces) + (0.3 * sim_logs)

def retrieve_and_vote(live_incident_vec: dict, history_list: list, top_k: int = 3) -> dict:
    """K-Nearest Neighbors kết hợp Bầu chọn có Phạt (Weighted Voting)"""
    
    # 1. Chấm điểm tương đồng cho toàn bộ 30 sự cố lịch sử
    scored_history = []
    for hist_entry in history_list:
        score = calculate_similarity(live_incident_vec, hist_entry)
        scored_history.append((score, hist_entry))
        
    # 2. K-Nearest: Lấy ra Top K (3) sự cố có điểm cao nhất
    scored_history.sort(key=lambda x: x[0], reverse=True)
    top_neighbors = scored_history[:top_k]
    
    # 3. Outcome-weighted Voting (Bầu chọn dựa trên kết quả thành/bại)
    action_scores = {}
    
    for sim_score, hist_entry in top_neighbors:
        outcome = hist_entry.get('outcome', 'failed')
        
        # Thiết lập luật Thưởng / Phạt
        if outcome == 'success':
            weight = 1.0
        elif outcome == 'partial':
            weight = 0.5
        else:
            weight = -1.0 # Hành động thất bại -> Trừ điểm để AI không học theo
            
        # Cộng/Trừ điểm cho các hành động đã thực hiện
        for action_raw in hist_entry.get('actions_taken', []):
            if action_raw not in action_scores:
                action_scores[action_raw] = 0.0
            
            # Phiếu bầu = Độ giống nhau của kịch bản * Trọng số thành công
            action_scores[action_raw] += (sim_score * weight)
            
    # 4. Đóng gói danh sách ứng viên (Sắp xếp từ điểm cao xuống thấp)
    sorted_candidates = sorted(action_scores.items(), key=lambda x: x[1], reverse=True)
    
    return {
        "top_3_neighbors": [{"id": entry['id'], "sim_score": round(score, 3)} for score, entry in top_neighbors],
        "candidates": sorted_candidates,
        "max_similarity": top_neighbors[0][0] if top_neighbors else 0.0
    }

# Thêm vào cuối file retrieval.py

def visualize_retrieval(retrieval_result: dict, query_incident_id: str = "LIVE_INCIDENT"):
    print(f"\n{'-'*60}")
    print(f"[REPORT] RETRIEVAL FOR: {query_incident_id}")
    print(f"{'-'*60}")
    
    # In ra Top 3 Láng giềng
    print("\n[INFO] TOP 3 NEIGHBORS:")
    for rank, neighbor in enumerate(retrieval_result.get('top_3_neighbors', []), 1):
        bar_length = int(neighbor['sim_score'] * 10)
        bar = "#" * bar_length + "-" * (10 - bar_length)
        print(f"  {rank}. [{neighbor['id']}]")
        print(f"     Score: {neighbor['sim_score']:.2f} | {bar}")

    # In ra kết quả Bầu chọn Hành động
    print("\n[INFO] ACTION VOTING RESULTS:")
    candidates = retrieval_result.get('candidates', [])
    if not candidates:
        print("  [WARN] Khong co ung vien phu hop!")
    else:
        for action, score in candidates:
            if score < 0:
                flag = "[DANGER] Tung that bai"
            elif score > 0.5:
                flag = "[RECOMMENDED] Ty le thanh cong cao"
            else:
                flag = "[WARNING] Hieu qua thap"
                
            print(f"  -> Lenh: {action:<40}")
            print(f"     Diem: {score:+.2f} \t| {flag}")
            
    print(f"{'-'*60}\n")



if __name__ == "__main__":
    # Test mộc với Data giả
    mock_result = {
        'top_3_neighbors': [
            {'id': 'INC-2025-11-08', 'sim_score': 0.85},
            {'id': 'INC-2024-03-12', 'sim_score': 0.42},
            {'id': 'INC-2025-01-01', 'sim_score': 0.15}
        ],
        'candidates': [
            ('rollback_service:payment-svc:v3.1', 1.27),
            ('restart_pod:payment-svc', 0.85),
            ('drop_database:payment-db', -0.42) # Kẻ xúi bậy bị âm điểm
        ],
        'max_similarity': 0.85
    }
    visualize_retrieval(mock_result)
