"""Check each structured proposal against the saved source and canonical companies.
The pipeline supplies the proposed deal, original text and source attribution.
Return explicit findings for a bounded retry, the pending queue and human review.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .models import Deal


def whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Dollar symbols, USD/US$ and spelled-out US dollars. A bare '160 million
# shares', GPU count, percentage or exercise price must not become deal value.
MONEY = re.compile(
    r"(?:US\s*\$|USD\s*|\$)\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(trillion|billion|million|thousand|bn|mm|[bmk])?\b|"
    r"(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand)?\s*"
    r"(?:U\.?S\.?\s+dollars|USD)\b",
    re.I,
)
SCALE = {
    "": 1,
    "thousand": 1000,
    "k": 1000,
    "million": 10**6,
    "mm": 10**6,
    "m": 10**6,
    "billion": 10**9,
    "bn": 10**9,
    "b": 10**9,
    "trillion": 10**12,
}


def dollars(text: str) -> set[Decimal]:
    result = set()
    for match in MONEY.finditer(whitespace(text)):
        number, scale = (
            (match[1], match[2]) if match[1] is not None else (match[3], match[4])
        )
        result.add(Decimal(number.replace(",", "")) * SCALE[(scale or "").lower()])
    return result


def instrument_advisory(deal):
    """Flag a proposed equity instrument when the quote describes a convertible note."""
    if deal["deal_type"] != "equity_investment":
        return None
    quote = whitespace(deal["evidence_quote"])
    if re.search(r"\bconvertible(?: senior)? notes?\b|\bnotes?\b[^.!?]{0,160}\bconvertible into equity\b", quote, re.I):
        return "The quote describes a convertible note. Check whether the funding instrument is debt before conversion."
    return None


def verify(
    deal: Deal, text: str, resolver, source_url: str, company: str | None = None
) -> dict:
    details = {}

    def record(name, failures, applicable=True):
        details[name] = {"result": ("skip" if not applicable else "fail" if failures else "pass"),
                         "errors": failures}

    quote = whitespace(deal.evidence_quote)
    record("verbatim_quote", [] if quote and quote in whitespace(text) else
           ["evidence_quote is not verbatim in source (whitespace normalisation only)"])
    source, target = resolver.resolve(deal.source_entity), resolver.resolve(deal.target_entity)
    node_errors = []
    if not source:
        node_errors.append(f"unknown source entity: {deal.source_entity}")
    if not target:
        node_errors.append(f"unknown target entity: {deal.target_entity}")
    if source and source == target:
        node_errors.append("source and target resolve to the same node")
    record("known_nodes", node_errors)
    record("source_url", [] if deal.source_url == source_url else
           ["source_url differs from fetched document URL"])
    mentioned = resolver.mentioned(text)
    publisher = resolver.resolve(company or "")
    if publisher:
        mentioned.add(publisher)
    record("entities_in_text_or_filer_metadata", [f"entity absent from document text: {node}"
           for node in (source, target) if node and node not in mentioned])
    money_errors = []
    if deal.amount_usd is not None:
        if Decimal(str(deal.amount_usd)) not in dollars(quote):
            money_errors.append("amount_usd does not appear as an explicit USD amount in evidence_quote")
        if not deal.amount_text or whitespace(deal.amount_text) not in quote:
            money_errors.append("amount_text is missing from evidence_quote")
    record("USD_amount", money_errors, applicable=deal.amount_usd is not None)
    errors = [error for check in details.values() for error in check["errors"]]
    return {"passed": not errors, "errors": errors, "source_node": source, "target_node": target,
            "checks": ["verbatim_quote", "USD_amount", "known_nodes", "entities_in_text_or_filer_metadata", "source_url"],
            "details": details}
