"""Strict deterministic checks. Only whitespace is normalised in evidence."""

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


def verify(
    deal: Deal, text: str, resolver, source_url: str, company: str | None = None
) -> dict:
    errors = []
    quote = whitespace(deal.evidence_quote)
    if not quote or quote not in whitespace(text):
        errors.append(
            "evidence_quote is not verbatim in source (whitespace normalisation only)"
        )
    source, target = (
        resolver.resolve(deal.source_entity),
        resolver.resolve(deal.target_entity),
    )
    if not source:
        errors.append(f"unknown source entity: {deal.source_entity}")
    if not target:
        errors.append(f"unknown target entity: {deal.target_entity}")
    if source and source == target:
        errors.append("source and target resolve to the same node")
    if deal.source_url != source_url:
        errors.append("source_url differs from fetched document URL")
    # A known filing author supplies the first-person "we" context. Other
    # counterparties must appear in the source; metadata never creates nodes.
    mentioned = resolver.mentioned(text)
    publisher = resolver.resolve(company or "")
    if publisher:
        mentioned.add(publisher)
    for canonical in (source, target):
        if canonical and canonical not in mentioned:
            errors.append(f"entity absent from document text: {canonical}")
    if deal.amount_usd is not None:
        if Decimal(str(deal.amount_usd)) not in dollars(quote):
            errors.append(
                "amount_usd does not appear as an explicit USD amount in evidence_quote"
            )
        if not deal.amount_text or whitespace(deal.amount_text) not in quote:
            errors.append("amount_text is missing from evidence_quote")
    return {
        "passed": not errors,
        "errors": errors,
        "source_node": source,
        "target_node": target,
        "checks": [
            "verbatim_quote",
            "USD_amount",
            "known_nodes",
            "entities_in_text_or_filer_metadata",
            "source_url",
        ],
    }
