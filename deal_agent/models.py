"""Strict wire schemas. Model output is data, never executable instructions."""

from __future__ import annotations

import json
import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DealType(str, Enum):
    equity_investment = "equity_investment"
    compute_purchase_commitment = "compute_purchase_commitment"
    chip_purchase = "chip_purchase"
    cloud_services_contract = "cloud_services_contract"
    debt_or_loan = "debt_or_loan"
    gpu_backed_financing = "gpu_backed_financing"
    warrants_or_options = "warrants_or_options"
    revenue_share = "revenue_share"
    other = "other"


class Deal(StrictModel):
    source_entity: str = Field(min_length=1)
    target_entity: str = Field(min_length=1)
    deal_type: DealType
    consideration_type: str = Field(
        pattern=r"^(cash|equity|compute_credits|mixed|unknown)$"
    )
    amount_usd: float | None = Field(ge=0)
    amount_text: str
    term_or_duration: str | None
    announced_date: date
    source_url: str = Field(pattern=r"^https?://")
    evidence_quote: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)

    @field_validator("rationale")
    @classmethod
    def one_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("rationale must be one line")
        return value


class Extraction(StrictModel):
    edges: list[Deal]


class Triage(StrictModel):
    relevant: bool
    reason: str = Field(min_length=1)


def parse_json(raw: str, schema: type[StrictModel]) -> StrictModel:
    """Accept JSON or one enclosing JSON fence; no guessing, trailing prose, or repairs."""
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    if fenced:
        text = fenced.group(1)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    # Reject duplicate keys and NaN before Pydantic's JSON-aware strict validation
    # (JSON dates/enums are intentionally allowed; coercing arbitrary Python is not).
    json.loads(
        text,
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    return schema.model_validate_json(text)


# The legacy taxonomy is deliberately preserved for metrics/browser parity.
# Unmapped types need an explicit analyst choice before publication.
LEGACY_TYPE = {
    "equity_investment": "equity_investment",
    "compute_purchase_commitment": "cloud_capacity_contract",
    "chip_purchase": "purchase_commitment",
    "cloud_services_contract": "cloud_capacity_contract",
    "debt_or_loan": "convertible_or_debt",
    "gpu_backed_financing": "vendor_financing",
    "warrants_or_options": "warrants",
}
