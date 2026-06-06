# -*- coding: utf-8 -*-
import json

# Example input:
# {"max_iter": 50, "damping": 0.85, "top_k": 20}


def Process(db, input):
    # 1. Parse PageRank parameters.
    data = json.loads(input)
    max_iter = int(data.get("max_iter", 50))
    damping = float(data.get("damping", 0.85))
    top_k = int(data.get("top_k", 20))

    # 2. Create a read-only transaction.
    txn = db.CreateReadTxn()

    # 3. Collect vertices, transaction metadata, in-degrees and out-degrees.
    vids = []
    out_deg = {}
    in_deg = {}
    tx_meta = {}

    it = txn.GetVertexIterator()
    while it.IsValid():
        vid = it.GetId()
        vids.append(vid)
        out_deg[vid] = 0
        in_deg[vid] = 0

        try:
            tx_id = str(it.GetField("txId"))
        except Exception:
            tx_id = str(vid)
        try:
            tx_class = str(it.GetField("class"))
        except Exception:
            tx_class = ""
        tx_meta[vid] = {"txId": tx_id, "class": tx_class}
        it.Next()

    node_count = len(vids)
    if node_count == 0:
        txn.Abort()
        return (True, json.dumps([], ensure_ascii=False))

    it = txn.GetVertexIterator()
    while it.IsValid():
        vid = it.GetId()
        edge_it = it.GetOutEdgeIterator()
        while edge_it.IsValid():
            dst = edge_it.GetDst()
            out_deg[vid] = out_deg.get(vid, 0) + 1
            if dst in in_deg:
                in_deg[dst] += 1
            edge_it.Next()
        it.Next()

    # 4. Initialize every transaction with the same PageRank value.
    pr = {vid: 1.0 / node_count for vid in vids}

    # 5. Iteratively propagate PageRank along TRANSFER_TO edges.
    actual_iter = 0
    final_diff = 0.0
    for i in range(max_iter):
        actual_iter = i + 1
        new_pr = {vid: (1.0 - damping) / node_count for vid in vids}

        dangling_mass = sum(pr[vid] for vid in vids if out_deg[vid] == 0) * damping

        it = txn.GetVertexIterator()
        while it.IsValid():
            vid = it.GetId()
            if out_deg[vid] > 0:
                contrib = pr[vid] * damping / out_deg[vid]
                edge_it = it.GetOutEdgeIterator()
                while edge_it.IsValid():
                    dst = edge_it.GetDst()
                    if dst in new_pr:
                        new_pr[dst] += contrib
                    edge_it.Next()
            it.Next()

        if dangling_mass > 0:
            equal_share = dangling_mass / node_count
            for vid in vids:
                new_pr[vid] += equal_share

        final_diff = sum(abs(new_pr[vid] - pr[vid]) for vid in vids)
        pr = new_pr
        if final_diff < 1e-6:
            break

    # 6. Format top-k transactions with attributes that are useful for risk analysis.
    top_result = sorted(pr.items(), key=lambda x: x[1], reverse=True)[:top_k]
    result_list = []
    for rank, (vid, score) in enumerate(top_result, 1):
        result_list.append({
            "rank": rank,
            "vid": vid,
            "txId": tx_meta.get(vid, {}).get("txId", str(vid)),
            "class": tx_meta.get(vid, {}).get("class", ""),
            "pageRank": round(score, 10),
            "inDegree": in_deg.get(vid, 0),
            "outDegree": out_deg.get(vid, 0),
        })

    output = {
        "nodeCount": node_count,
        "iteration": actual_iter,
        "diff": round(final_diff, 10),
        "topK": result_list,
    }

    txn.Abort()
    return (True, json.dumps(output, ensure_ascii=False))
