"""Toy ledgers with hand-computable answers."""
from __future__ import annotations

import pandas as pd

from src.ledger import BACKLOG_FIELDS, EDGE_FIELDS


def edge(src, tgt, etype, low, high=None, *, status="definitive", tier="T1",
         basis="notional", term_start="", term_end="", acc="0000000000-00-000000",
         quote="toy row", notes=""):
    return {
        "edge_id": f"{src}__{tgt}__{etype}", "as_of_date": "2026-01-01",
        "source_node": src, "target_node": tgt, "edge_type": etype,
        "amount_usd_low": float(low), "amount_usd_high": float(high if high is not None else low),
        "amount_basis": basis, "term_start": term_start, "term_end": term_end,
        "status": status, "conditions_text": "", "evidence_tier": tier,
        "source_url": "https://example.test/doc", "accession_no": acc,
        "quote_snippet": quote, "notes": notes,
    }


def backlog(node, amount, metric="rpo", low=None):
    return {
        "node": node, "as_of_date": "2026-01-01", "metric": metric,
        "amount_usd_low": float(low if low is not None else amount),
        "amount_usd_high": float(amount), "evidence_tier": "T1",
        "source_url": "https://example.test/doc", "accession_no": "0000000000-00-000000",
        "quote_snippet": "toy backlog", "notes": "",
    }


def frames(edges, backlogs):
    e = pd.DataFrame(edges)[EDGE_FIELDS]
    b = pd.DataFrame(backlogs)[BACKLOG_FIELDS]
    return e, b


def perfect_round_trip():
    """A invests 10 in B; B commits 10 of purchases to A; A's backlog is 10.

    Direct round-trip share must be 100% on every bound:
      D[A, B] = 10 / 10 = 1
      LOWER provenance  = funding(A->B) / commitment(B->A) = 10/10 = 1
      CENTRAL provenance = A's share of B's documented funding = 10/10 = 1
      UPPER provenance   = 1 (A funds B at all)
    """
    return frames(
        [edge("A", "B", "equity_investment", 10), edge("B", "A", "purchase_commitment", 10)],
        [backlog("A", 10)],
    )


def half_funded():
    """A and C each put 10 into B; B commits 20 to A; A's backlog is 20.

      D[A, B] = 20/20 = 1
      LOWER   = funding(A->B)/commitment(B->A) = 10/20 = 0.5
      CENTRAL = A's share of B's documented funding = 10/20 = 0.5
      UPPER   = 1
    """
    return frames(
        [edge("A", "B", "equity_investment", 10),
         edge("C", "B", "equity_investment", 10),
         edge("B", "A", "purchase_commitment", 20)],
        [backlog("A", 20)],
    )


def two_hop():
    """A funds M, M funds B, B buys from A. No direct A->B funding edge.

    LOWER must be 0 (direct only). CENTRAL must pick the path up through the
    damped multi-hop term: S[A,M]=1, S[M,B]=1, so (alpha*S)^2[A,B] = alpha^2.
    """
    return frames(
        [edge("A", "M", "equity_investment", 10),
         edge("M", "B", "equity_investment", 10),
         edge("B", "A", "purchase_commitment", 10)],
        [backlog("A", 10)],
    )


def tiered():
    """Same as perfect_round_trip but the funding leg is T3 media reporting."""
    return frames(
        [edge("A", "B", "equity_investment", 10, tier="T3", acc=""),
         edge("B", "A", "purchase_commitment", 10)],
        [backlog("A", 10)],
    )


def t4_only():
    return frames(
        [edge("A", "B", "equity_investment", 10, tier="T4", acc=""),
         edge("B", "A", "purchase_commitment", 10)],
        [backlog("A", 10)],
    )
