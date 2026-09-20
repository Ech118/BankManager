"""Peer comparison. Specified by docs/data-model.md "Valuation".

MEDIAN, never mean. Peer sets are small and one mispriced or mis-tagged
comparable can move a mean enough to flip a verdict; the median is unmoved.

Peers with `unavailable` multiples are excluded from the median and counted, so
a comparison resting on two usable peers does not look like one resting on six
(error E).

Two ways a peer multiple can arrive, and both are handled:

1. **published** - P1 put `pe` / `ev_ebitda` / `ev_revenue` / `fcf_yield` on the
   `Peer`. Used as-is, with the peer's own source_id.
2. **computed** - P1 put the raw fields on the `Peer` instead (`revenue`,
   `net_income`, `total_debt`, `cash`, `ebitda`, `total_equity`, ...). calc/
   computes the multiple from them, because the peer's own filing is a better
   source than a vendor ratio.

Today the real recordings carry a market cap and nothing else, so every peer
median is `unavailable` **with the reason**, and `usable` says 0 of 6. That is
the honest output, and it is why the count is published next to the median.
"""

from __future__ import annotations

from calc import config
from calc.facts import Ledger
from calc.value import div, median, ratio_minus_one, sub, value

PEER_FIELDS = ("pe", "ev_ebitda", "ev_revenue", "p_fcf", "p_s", "p_b", "fcf_yield")
"""The multiples a peer comparison covers. `p_s` and `p_b` are additive."""

NO_DATA = (
    "no peer carries this multiple, and the raw fields to compute it are not on "
    "the factsheet's peers either"
)
TOO_FEW = "only {n} peer(s) carry this multiple, below the minimum of {k} for a median"


def _vo_num(peer: dict, field: str) -> float | None:
    vo = peer.get(field)
    if not isinstance(vo, dict) or vo.get("status") != "ok":
        return None
    val = vo.get("value")
    return None if val is None else float(val)


def peer_multiple(peer: dict, field: str) -> tuple[float | None, str]:
    """One peer's multiple, and how it was obtained ("published"/"computed"/"none")."""
    published = _vo_num(peer, field)
    if published is not None:
        return published, "published"

    cap = _vo_num(peer, "market_cap")
    revenue = _vo_num(peer, "revenue")
    net_income = _vo_num(peer, "net_income")
    ebitda = _vo_num(peer, "ebitda")
    debt = _vo_num(peer, "total_debt")
    cash = _vo_num(peer, "cash")
    equity = _vo_num(peer, "total_equity")
    fcf = _vo_num(peer, "fcf")
    if fcf is None:
        fcf = sub(_vo_num(peer, "op_cash_flow"), _vo_num(peer, "capex"))
    ev = None
    if cap is not None and debt is not None and cash is not None:
        ev = cap + debt - cash

    computed = {
        "pe": div(cap, net_income),
        "ev_ebitda": div(ev, ebitda),
        "ev_revenue": div(ev, revenue),
        "p_fcf": div(cap, fcf),
        "p_s": div(cap, revenue),
        "p_b": div(cap, equity),
        "fcf_yield": div(fcf, cap),
    }.get(field)
    return (computed, "computed") if computed is not None else (None, "none")


def peer_table(ledger: Ledger, fields: tuple[str, ...] = PEER_FIELDS) -> dict:
    """Every peer's multiples, plus the median and how many peers backed it."""
    peers = ledger.factsheet.get("peers") or []
    rows = []
    for peer in peers:
        row: dict = {
            "ticker": peer.get("ticker"),
            "company_name": peer.get("company_name"),
            "selection_reason": peer.get("selection_reason"),
            "market_cap": peer.get("market_cap"),
            "multiples": {},
        }
        for field in fields:
            num, how = peer_multiple(peer, field)
            row["multiples"][field] = value(
                num,
                "fraction" if field == "fcf_yield" else "multiple",
                "fact",
                source_id=(peer.get(field) or {}).get("source_id") if how == "published" else None,
                derived_from=[f"peers.{peer.get('ticker')}.{field}"],
                reason=NO_DATA if how == "none" else None,
            )
            row["multiples"][field]["basis"] = how
        rows.append(row)

    medians: dict = {}
    for field in fields:
        values = [
            row["multiples"][field]["value"]
            for row in rows
            if row["multiples"][field]["value"] is not None
        ]
        usable = len(values)
        unit = "fraction" if field == "fcf_yield" else "multiple"
        med = median(values) if usable >= config.PEER_MIN_SAMPLE else None
        medians[field] = value(
            med,
            unit,
            "fact",
            derived_from=[f"peers[*].{field}"],
            reason=(NO_DATA if usable == 0 else TOO_FEW.format(n=usable, k=config.PEER_MIN_SAMPLE)),
        )
        medians[field]["usable_peers"] = usable
        medians[field]["peer_count"] = len(rows)
    return {"peers": rows, "median": medians}


def usable_peer_count(peers: list[dict], field: str) -> int:
    """How many peers actually had this multiple. Surfaced in data_quality."""
    return sum(1 for peer in peers if peer_multiple(peer, field)[0] is not None)


def compare(ledger: Ledger, own: dict, table: dict, fields: tuple[str, ...] = PEER_FIELDS) -> dict:
    """This company's premium (+) or discount (-) to each peer median."""
    out: dict = {}
    for field in fields:
        if field not in own:
            continue
        own_vo = own[field]
        med = table["median"][field]["value"]
        own_ref = ledger.derived_ref(own_vo, field)
        reason = None
        if med is None:
            reason = table["median"][field].get("unavailable_reason") or NO_DATA
        elif own_vo.get("value") is None:
            reason = own_vo.get("unavailable_reason") or f"this company's {field} is unavailable"
        elif own_ref is None:
            reason = f"this company's {field} carries no derived fact to compare"
        out[f"{field}_premium"] = ledger.emit(
            ratio_minus_one(own_vo.get("value"), med) if reason is None else None,
            metric=f"{field}_premium_vs_peers",
            period=ledger.latest_annual_label() or ledger.as_of,
            unit="fraction",
            formula=f"{field} / {med!r} - 1",
            inputs={field: own_ref} if own_ref else {},
            paths=[f"valuation.{field}", f"peers[*].{field}"],
            period_type="instant",
            reason=reason,
            not_applicable=bool(own_vo.get("not_applicable")),
            derivation_extra={
                "peer_median": med,
                "usable_peers": table["median"][field]["usable_peers"],
            },
        )
    return out
