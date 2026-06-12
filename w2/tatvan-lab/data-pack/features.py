import re
import numpy as np
from collections import defaultdict

def extract_features(incident: dict) -> dict:
    affected_services = set()
    
    trigger = incident.get('trigger_alert', {})
    if trigger:
        affected_services.add(trigger.get('service'))
        
    log_counts = defaultdict(int)
    for log in incident.get('logs', []):
        if log.get('level') in ['ERROR', 'WARN', 'FATAL', 'WARNING']:
            svc = log.get('svc')
            if svc: 
                affected_services.add(svc)
            
            msg = log.get('msg', '')
            msg = re.sub(r'\b\d+\b', '<NUM>', msg) 
            msg = re.sub(r'\b[0-9a-fA-F\-]{36}\b', '<UUID>', msg) 
            msg = re.sub(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', '<IP>', msg) 
            
            words = [w.lower() for w in re.findall(r'[a-zA-Z]+', msg)]
            signature = " ".join(words[:10]) 
            
            if signature:
                log_counts[signature] += 1
                
    top_logs = sorted(log_counts.items(), key=lambda x: -x[1])[:10]
    log_signatures = [msg for msg, _ in top_logs]
    
    trace_sigs = []
    trace_agg = defaultdict(lambda: {'count': 0, 'error_count': 0, 'p99_max': 0})
    
    for t in incident.get('traces', []):
        k = (t.get('from'), t.get('to'))
        trace_agg[k]['count'] += t.get('count', 0)
        trace_agg[k]['error_count'] += t.get('error_count', 0)
        trace_agg[k]['p99_max'] = max(trace_agg[k]['p99_max'], t.get('p99_ms', 0))
        
    for (src, dst), agg in trace_agg.items():
        err_rate = agg['error_count'] / max(1, agg['count'])
        if err_rate > 0.05 or agg['p99_max'] > 1000:
            affected_services.add(src)
            affected_services.add(dst)
            trace_sigs.append({
                "from": src,
                "to": dst,
                "error_rate": err_rate,
                "p99_ms": agg['p99_max']
            })
            
    metric_sigs = []
    samples = incident.get('metrics_window', {}).get('samples', {})
    
    for series_name, data in samples.items():
        if not data or '.' not in series_name: continue
        svc, metric = series_name.split('.', 1)
        vals = [v for ts, v in data]
        if len(vals) < 10: continue
        
        baseline_len = max(1, len(vals) // 3)
        baseline = np.mean(vals[:baseline_len])
        std = max(np.std(vals[:baseline_len]), 1e-6)
        
        peak = np.max(vals)
        if peak > baseline * 1.5 or peak > baseline + 3 * std:
            affected_services.add(svc)
            metric_sigs.append({
                "service": svc,
                "metric": metric,
                "delta_ratio": peak / max(baseline, 1e-6)
            })

    return {
        "affected_services": list(affected_services),
        "log_signatures": log_signatures,
        "trace_signatures": trace_sigs,
        "metric_signatures": metric_sigs,
        "trigger": trigger
    }
