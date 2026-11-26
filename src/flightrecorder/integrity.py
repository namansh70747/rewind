"""Validate evidence independently of executing the agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .boundary import GENESIS, Divergence, canon, chain_link

if TYPE_CHECKING:
    from .boundary import Cassette


class IntegrityError(Divergence):
    """Recorded evidence is damaged or cannot be validated."""


def validate(cassette: Cassette) -> None:
    """Check sequence, every link, and the terminal fingerprint. Not a signature."""
    if cassette.chain_algorithm not in {"blake2b", "blake3"}:
        raise IntegrityError(0, "unsupported recording chain algorithm")
    previous = GENESIS
    for index, boundary in enumerate(cassette.boundaries):
        if boundary.seq != index:
            raise IntegrityError(index, "non-contiguous boundary sequence")
        previous = chain_link(
            previous,
            canon([boundary.kind, boundary.key, boundary.request]),
            canon(boundary.response),
            cassette.chain_algorithm,
        )
        if previous != boundary.chain_hash:
            raise IntegrityError(index, "hash-chain mismatch — recording corrupted")
    if previous != cassette.fingerprint:
        raise IntegrityError(len(cassette.boundaries), "terminal fingerprint mismatch")
