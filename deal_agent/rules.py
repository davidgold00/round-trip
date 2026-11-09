"""Thin, label-blind adapter for the original candidate extractor.

The $50M floor, first-money match, verb order and guessed direction are retained.
News tagging produces relevance flags, not directed edges, so it is not unioned
into edge predictions. This baseline measures the original extraction rules.
"""
from types import SimpleNamespace

from src.entities import alias_map
from src.extract import extract_from_text

from .verify import verify
from .models import Deal, parse_json
import json

RULE_TYPES = {
    "equity_investment": "equity_investment",
    "convertible_or_debt": "debt_or_loan",
    "loan_or_guarantee": "debt_or_loan",
    "vendor_financing": "gpu_backed_financing",
    "warrants": "warrants_or_options",
    "cloud_capacity_contract": "cloud_services_contract",
    "purchase_commitment": "chip_purchase",
    "offtake_or_rpo": "compute_purchase_commitment",
    "lease": "other",
}


class Rules:
    def __init__(self, pipeline):
        self.resolver, self.trace, self.agent = pipeline.resolver, pipeline.trace, pipeline.agent
        self.provider = SimpleNamespace(model="original-rules")
        self.cfg = pipeline.cfg

    def process_text(self, text, meta):
        candidates, _, _ = extract_from_text(text, {
            "node": meta["company"], "filing_date": meta["published_date"],
            "doc_url": meta["source_url"], "accession_no": meta.get("accession_no", ""),
            "form": meta["doc_type"],
        }, alias_map())
        edges = []
        for row in candidates:
            deal = {
                "source_entity": row["source_node"], "target_entity": row["target_node"],
                "deal_type": RULE_TYPES[row["edge_type"]], "consideration_type": "unknown",
                "amount_usd": row["amount_usd_high"], "amount_text": row["extracted_amount_text"],
                "term_or_duration": None, "announced_date": meta["published_date"],
                "source_url": meta["source_url"], "evidence_quote": row["context_window"],
                "confidence": 0.0, "rationale": row["notes"],
            }
            checked = verify(parse_json(json.dumps(deal), Deal), text, self.resolver,
                             meta["source_url"], meta["company"])
            edges.append({"deal": deal, "verification": checked})
        return {"relevant": bool(candidates), "edges": edges, "errors": []}
