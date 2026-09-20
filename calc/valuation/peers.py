"""Peer comparison. Specified by docs/data-model.md "Valuation".

MEDIAN, never mean. Peer sets are small and one mispriced or mis-tagged
comparable can move a mean enough to flip a verdict; the median is unmoved.

Peers with `unavailable` multiples are excluded from the median and counted, so
a comparison resting on two usable peers does not look like one resting on six
(error E).
"""

from __future__ import annotations

from calc._util import median, num, ratio_minus_one
from calc.lineage import derived_value
from schema.contracts.common import ValueObject
from schema.contracts.market import Peer
from schema.contracts.metrics import VsPeers


def usable_peer_count(peers: list[Peer], field: str) -> int:
    """How many peers actually had this multiple. Surfaced in data_quality."""
    return sum(1 for p in peers if num(getattr(p, field)) is not None)


def median_multiple(peers: list[Peer], field: str) -> ValueObject:
    """Median of one multiple across peers with a usable value."""
    values = [num(getattr(p, field)) for p in peers]
    return derived_value(median(values), "multiple", [f"peers[*].{field}"])


def premium_to_peers(own: ValueObject, peer_median: ValueObject) -> ValueObject:
    """Premium (+) or discount (-) to the peer median, as a fraction."""
    return derived_value(ratio_minus_one(num(own), num(peer_median)), "fraction", [])


def compare(own_multiples: dict, peers: list[Peer]) -> VsPeers:
    """P/E and EV/EBITDA premium versus the peer median."""
    pe_median = median_multiple(peers, "pe")
    ev_ebitda_median = median_multiple(peers, "ev_ebitda")
    return VsPeers(
        pe_premium=derived_value(
            ratio_minus_one(own_multiples.get("pe"), num(pe_median)), "fraction",
            ["valuation.pe", "peers[*].pe"]),
        ev_ebitda_premium=derived_value(
            ratio_minus_one(own_multiples.get("ev_ebitda"), num(ev_ebitda_median)), "fraction",
            ["valuation.ev_ebitda", "peers[*].ev_ebitda"]),
    )
