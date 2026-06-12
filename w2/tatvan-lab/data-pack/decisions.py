# File: decision.py

def parse_action(raw_action_str: str, catalog_dict: dict) -> dict:
    """Hàm Helper: Chuyển đổi chuỗi lệnh thành Dictionary chuẩn"""
    parts = raw_action_str.split(":")
    name = parts[0]
    
    if name not in catalog_dict:
        return {"name": "page_oncall", "params": {}}
        
    action_def = catalog_dict[name]
    param_names = action_def.get('params', [])
    
    params = {}
    for i, p_name in enumerate(param_names):
        if len(parts) > i + 1:
            val = parts[i + 1]
            # Riêng action rollback, ta không biết version cũ là gì nên gán cứng là 'previous'
            if p_name == 'target_version':
                val = 'previous'
            params[p_name] = val
        else:
            params[p_name] = 'previous' if p_name == 'target_version' else 'auto'
                
    return {"name": name, "params": params}

def select_action(retrieval_output: dict, actions_catalog: list[dict]) -> dict:
    """Layer 3: Tính độ Tự tin (Confidence) và Phân tích Cấp độ Phá hoại (Blast-radius)"""
    
    # Biến danh sách action từ yaml thành thư viện dict để dễ tra cứu
    catalog_dict = {a['name']: a for a in actions_catalog}
    
    candidates = retrieval_output.get('candidates', [])
    max_sim = retrieval_output.get('max_similarity', 0.0)
    top_3 = retrieval_output.get('top_3_neighbors', [])
    
    # ====================================================
    # RULE 1: OOD Check (Kiểm tra xem sự cố có quá Mới Lạ không?)
    # ====================================================
    if max_sim < 0.15: # Ngưỡng an toàn (Có thể tinh chỉnh)
        return {
            "selected_action": "page_oncall",
            "params": {"team": "platform"},
            "confidence": 0.0,
            "consensus_score": 0.0,
            "top_3_neighbors": top_3,
            "blast_radius_check": "OOD (Out-of-Distribution) - Sự cố mới tinh, AI không dám đoán bừa.",
            "evidence": f"Max similarity {max_sim:.2f} quá thấp (< 0.15)."
        }
        
    # ====================================================
    # TÍNH TOÁN ĐỘ TỰ TIN (Confidence Scoring)
    # ====================================================
    # Chỉ tính tổng các phiếu bầu DƯƠNG (Những lệnh từng thành công)
    total_positive_score = sum(score for action, score in candidates if score > 0)
    
    if total_positive_score <= 0 or not candidates:
        return {
            "selected_action": "page_oncall",
            "params": {"team": "platform"},
            "confidence": 0.0,
            "consensus_score": 0.0,
            "top_3_neighbors": top_3,
            "blast_radius_check": "Tất cả các hành động trong quá khứ đều Thất Bại.",
            "evidence": "Total positive score = 0."
        }
        
    top_action_str, top_score = candidates[0]
    
    # Điểm tự tin = (Điểm của Top 1) / (Tổng điểm của các lệnh tốt)
    confidence = top_score / total_positive_score
    
    # Chuyển đổi định dạng Action
    parsed = parse_action(top_action_str, catalog_dict)
    action_name = parsed['name']
    
    # ====================================================
    # RULE 2: Cổng Gác An Toàn (Safety Gate / Blast-radius)
    # ====================================================
    if action_name == "page_oncall":
        reason = "Lịch sử khuyên gọi con người."
        
    elif confidence < 0.5:
        action_name = "page_oncall"
        parsed['params'] = {"team": "platform"}
        reason = f"Độ tự tin {confidence:.2f} thấp hơn 50%. Tự động chuyển qua gọi người."
        
    else:
        # Kiểm tra Hậu quả (Blast Radius) từ file actions.yaml
        meta = catalog_dict.get(action_name, {})
        blast_radius = meta.get('blast_radius_services', 0)
        
        # Nếu hành động này gây ảnh hưởng diện rộng (>=3 service)
        # Thì AI phải cực kỳ chắc chắn (Confidence >= 80%) mới được phép chạy.
        if blast_radius >= 3 and confidence < 0.8:
            action_name = "page_oncall"
            parsed['params'] = {"team": "platform"}
            reason = f"Lệnh rủi ro cao (Blast Radius {blast_radius}) nhưng độ tự tin {confidence:.2f} < 0.8. Đã chặn lại!"
        else:
            reason = f"Độ tự tin {confidence:.2f} đạt chuẩn. Mức độ rủi ro ({blast_radius}) nằm trong tầm kiểm soát."

    # ====================================================
    # TRẢ VỀ KẾT QUẢ ĐỂ GHI VÀO AUDIT LOG
    # ====================================================
    return {
        "selected_action": action_name,
        "params": parsed.get('params', {}),
        "confidence": round(confidence, 3),
        "consensus_score": round(confidence, 3),
        "top_3_neighbors": top_3,
        "blast_radius_check": reason,
        "evidence": f"Top Candidate ({top_action_str}) có điểm {top_score:.2f}. " + reason
    }
