"""Validate evidence independently of executing the agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .boundary import GENESIS, Divergence, canon, chain_link

if TYPE_CHECKING:
    from .boundary import Cassette


def validate(cassette: Cassette) -> None:
    """Check sequence, every link, and the terminal fingerprint. Not a signature."""
    previous = GENESIS
    for index, boundary in enumerate(cassette.boundaries):
        if boundary.seq != index:
            raise Divergence(index, "non-contiguous boundary sequence")
        previous = chain_link(
            previous,
            canon([boundary.kind, boundary.key, boundary.request]),
            canon(boundary.response),
            cassette.chain_algorithm,
        )
        if previous != boundary.chain_hash:
            raise Divergence(index, "hash-chain mismatch — recording corrupted")
    if previous != cassette.fingerprint:
        raise Divergence(len(cassette.boundaries), "terminal fingerprint mismatch")
