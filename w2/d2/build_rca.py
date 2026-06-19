import json
import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def main():
    with open('../d1/results/cluster_summary.json', 'r') as f:
        cluster_summary = json.load(f)

    with open('dataset/services.json', 'r') as f:
        services_data = json.load(f)
        
    with open('dataset/alerts_sample.jsonl', 'r') as f:
        alerts = [json.loads(line) for line in f if line.strip()]

    with open('dataset/incidents_history.json', 'r') as f:
        incidents = json.load(f)['incidents']

    # Build graph
    G = nx.DiGraph()
    for svc in services_data['services']:
        G.add_node(svc['name'], type='service')
    for store in services_data['stores']:
        G.add_node(store['name'], type='store')
    for edge in services_data['edges']:
        G.add_edge(edge['from'], edge['to'], type=edge['type'])

    # Temporal info
    from collections import defaultdict
    alert_times = defaultdict(list)
    for a in alerts:
        alert_times[a['service']].append(a['ts'])
    for k in alert_times:
        alert_times[k].sort()

    results = []
    
    # Setup for TF-IDF retrieval
    inc_docs = [" ".join(inc['services_involved']) for inc in incidents]
    vectorizer = TfidfVectorizer()
    if inc_docs:
        tfidf_matrix = vectorizer.fit_transform(inc_docs)

    for cluster in cluster_summary['clusters']:
        cluster_services = cluster['services']
        if not cluster_services:
            continue
        
        # 1. Graph + Temporal Scorer
        first_times = {svc: alert_times[svc][0] for svc in cluster_services if svc in alert_times}
        sorted_by_time = sorted(first_times.keys(), key=lambda k: first_times[k])
        
        subgraph = G.subgraph(cluster_services)
        scores = {}
        for i, svc in enumerate(sorted_by_time):
            temporal_score = len(sorted_by_time) - i 
            graph_score = subgraph.in_degree(svc) if svc in subgraph else 0
            scores[svc] = temporal_score + graph_score * 2
            
        total_score = sum(scores.values()) or 1
        top_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        graph_top3 = [[k, round(v/total_score, 2)] for k, v in top_candidates[:3]]
        root_cause = graph_top3[0][0] if graph_top3 else None
        
        # 2. Retrieval top-3 similar
        cluster_doc = " ".join(cluster_services)
        query_vec = vectorizer.transform([cluster_doc])
        sims = cosine_similarity(query_vec, tfidf_matrix)[0]
        
        # Get top indices
        top_indices = sims.argsort()[::-1][:3]
        
        top3_similar = [incidents[i]['id'] for i in top_indices]
        top1_inc = incidents[top_indices[0]] if len(top_indices) > 0 else None
        top1_sim = sims[top_indices[0]] if len(top_indices) > 0 else 0.0
        
        if top1_inc:
            pred_class = top1_inc['root_cause_class']
            pred_actions = top1_inc['remediation'].split('. ')
            confidence = round(float(top1_sim), 2)
        else:
            pred_class = "unknown"
            pred_actions = []
            confidence = 0.0
            
        results.append({
            "cluster_id": cluster['cluster_id'],
            "graph_top3": graph_top3,
            "root_cause": root_cause,
            "class": pred_class,
            "confidence": confidence,
            "actions": [a.strip() for a in pred_actions if a.strip()],
            "reasoning": f"Service {root_cause} has high topological and temporal scores. Retrieved historical incident {top1_inc['id']} with similarity {confidence}.",
            "similar_incidents": top3_similar,
            "method": "graph+tfidf_retrieval"
        })

    output = {
        "clusters_analyzed": len(results),
        "results": results
    }

    import os
    os.makedirs('results', exist_ok=True)
    with open('results/rca_output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print("rca_output.json generated!")

if __name__ == "__main__":
    main()
