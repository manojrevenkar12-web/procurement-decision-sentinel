"""Keyed randomness: the same (seed, key) always gives the same stream, whichever design asks."""

from __future__ import annotations

import hashlib

import numpy as np


def keyed(seed: int, *key: object) -> np.random.Generator:
    digest = hashlib.blake2b(repr((seed, *key)).encode(), digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(digest, "little"))
