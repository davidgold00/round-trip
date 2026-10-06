"""XBRL companyfacts parsing: pull the specific concepts the metrics need."""
from __future__ import annotations

from typing import Any

from .util import get_logger

LOG = get_logger("xbrl")

# concept -> field group. us-gaap taxonomy unless noted.
CONCEPTS: dict[str, list[str]] = {
    "rpo": [
        "RevenueRemainingPerformanceObligation",
    ],
    "rpo_pct_expected": [
        "RevenueRemainingPerformanceObligationPercentage",
    ],
    "purchase_obligations": [
        "UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount",
        "UnrecordedUnconditionalPurchaseObligationDueWithinOneYear",
        "PurchaseObligation",
        "ContractualObligation",
        "UnrecordedUnconditionalPurchaseObligation",
    ],
    "related_party": [
        "RelatedPartyTransactionAmountsOfTransaction",
        "RelatedPartyTransactionDueFromToRelatedParty",
        "DueFromRelatedPartiesCurrent",
        "DueToRelatedPartiesCurrent",
        "RevenueFromRelatedParties",
        "EquityMethodInvestments",
        "EquityMethodInvestmentOtherThanTemporaryImpairment",
    ],
    "concentration": [
        "ConcentrationRiskPercentage1",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "leases_not_commenced": [
        "LesseeOperatingLeaseLiabilityPaymentsDue",
        "LesseeFinanceLeaseLiabilityPaymentsDue",
        "OperatingAndFinanceLeaseNotYetCommencedAmount",
        "LesseeOperatingLeaseLeaseNotYetCommencedPaymentsDue",
    ],
    "debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "DebtInstrumentFaceAmount",
        "LongTermDebtCurrent",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerAndOtherSources",
    ],
    "nonmarketable_investments": [
        "OtherLongTermInvestments",
        "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
        "PaymentsToAcquireEquitySecuritiesFVNI",
        "PaymentsToAcquireOtherInvestments",
    ],
}

FLAT_CONCEPTS = {c: g for g, cs in CONCEPTS.items() for c in cs}


def _best_units(fact: dict) -> tuple[str, list[dict]]:
    units = fact.get("units", {})
    for key in ("USD", "pure", "USD/shares"):
        if key in units:
            return key, units[key]
    if units:
        k = next(iter(units))
        return k, units[k]
    return "", []


def extract_facts(companyfacts: dict | None, node: str) -> list[dict]:
    """Flatten the concepts of interest into tidy rows."""
    if not companyfacts:
        return []
    rows: list[dict] = []
    facts = companyfacts.get("facts", {})
    for taxonomy, concepts in facts.items():
        for concept, payload in concepts.items():
            group = FLAT_CONCEPTS.get(concept)
            if not group:
                continue
            unit, observations = _best_units(payload)
            for ob in observations:
                rows.append({
                    "node": node,
                    "taxonomy": taxonomy,
                    "concept": concept,
                    "group": group,
                    "label": payload.get("label", ""),
                    "unit": unit,
                    "value": ob.get("val"),
                    "start": ob.get("start", ""),
                    "end": ob.get("end", ""),
                    "fy": ob.get("fy"),
                    "fp": ob.get("fp", ""),
                    "form": ob.get("form", ""),
                    "filed": ob.get("filed", ""),
                    "accession_no": ob.get("accn", ""),
                    "frame": ob.get("frame", ""),
                })
    return rows


def latest_in_group(rows: list[dict], node: str, group: str,
                    forms: tuple[str, ...] = ("10-K", "10-Q", "20-F", "S-1")) -> dict | None:
    """Most recently filed observation for a node/group, preferring longer periods."""
    cands = [r for r in rows
             if r["node"] == node and r["group"] == group
             and r.get("form") in forms and isinstance(r.get("value"), (int, float))]
    if not cands:
        return None
    cands.sort(key=lambda r: (str(r.get("end") or ""), str(r.get("filed") or "")))
    return cands[-1]


def coverage(rows: list[dict], nodes: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for n in nodes:
        out[n] = {g: 0 for g in CONCEPTS}
    for r in rows:
        if r["node"] in out:
            out[r["node"]][r["group"]] = out[r["node"]].get(r["group"], 0) + 1
    return out
