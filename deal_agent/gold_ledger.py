"""Read-only agreement checks against reviewed ledger direction and taxonomy."""
from .models import LEGACY_TYPE
from .reconcile import read_csv
from .config import path_for


def check_gold_ledger(documents, cfg, resolver):
    graph = read_csv(path_for(cfg, "graph_file"))
    by_id = {row["edge_id"]: row for row in graph}
    result = {"matched": [], "mismatches": [], "ambiguous": [], "unlinked": []}
    for item in documents:
        for index, edge in enumerate(item["expected_edges"]):
            key = {"document": item["id"], "edge_index": index}
            source = resolver.resolve(edge["source_entity"]) or edge["source_entity"]
            target = resolver.resolve(edge["target_entity"]) or edge["target_entity"]
            mapped = LEGACY_TYPE.get(edge["deal_type"])
            explicit = item.get("ledger_edge_ids", {}).get(str(index)) or (item.get("ledger_edge_id") if len(item["expected_edges"]) == 1 else None)
            if explicit:
                candidates = [by_id[explicit]] if explicit in by_id else []
                if not candidates:
                    result["mismatches"].append({**key, "ledger_edge_id": explicit, "reason": "Referenced reviewed edge does not exist"})
                    continue
            else:
                candidates = [r for r in graph if
                              r["source_url"].rstrip("/") == item["source_url"].rstrip("/") and
                              {r["source_node"], r["target_node"]} == {source, target}]
                if not candidates:
                    result["unlinked"].append(key)
                    continue
                # A shared release can describe several instruments. Only narrow
                # by mapped type when one instrument unambiguously matches it.
                typed = [r for r in candidates if r["edge_type"] == mapped]
                if len(typed) == 1:
                    candidates = typed
            if len(candidates) != 1:
                result["ambiguous"].append({**key, "ledger_edge_ids": [r["edge_id"] for r in candidates],
                                            "reason": "Shared source/pair needs an explicit ledger_edge_id"})
                continue
            row = candidates[0]
            problems = []
            if (source, target) != (row["source_node"], row["target_node"]):
                problems.append("direction")
            if mapped != row["edge_type"]:
                problems.append("type mapping")
            entry = {**key, "ledger_edge_id": row["edge_id"]}
            if problems:
                entry.update(reason=", ".join(problems), gold_direction=[source, target],
                             ledger_direction=[row["source_node"], row["target_node"]],
                             gold_legacy_type=mapped, ledger_type=row["edge_type"])
                result["mismatches"].append(entry)
            else:
                result["matched"].append(entry)
    return result
