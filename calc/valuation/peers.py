"""Peer comparison. Specified by docs/data-model.md "Valuation".

MEDIAN, never mean. Peer sets are small and one mispriced or mis-tagged
comparable can move a mean enough to flip a verdict; the median is unmoved.

Peers with `unavailable` multiples are excluded from the median and counted, so
a comparison resting on two usable peers does not look like one resting on six
(error E).

TODO(roadmap Step 4, P2).
"""

from __future__ import annotations

from schema.contracts.common import ValueObject
from schema.contracts.market import Peer
from schema.contracts.metrics import VsPeers


def median_multiple(peers: list[Peer], field: str) -> ValueObject:
    """Median of one multiple across peers with a usable value."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def premium_to_peers(own: ValueObject, peer_median: ValueObject) -> ValueObject:
    """Premium (+) or discount (-) to the peer median, as a fraction."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def compare(own_multiples: dict, peers: list[Peer]) -> VsPeers:
    """P/E and EV/EBITDA premium versus the peer median."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")


def usable_peer_count(peers: list[Peer], field: str) -> int:
    """How many peers actually had this multiple. Surfaced in data_quality."""
    raise NotImplementedError("TODO(roadmap Step 4, P2)")
