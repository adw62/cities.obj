"""Distribution-aware sampler.

Wraps a seeded random.Random and provides uniform/gumbel/normal sampling
all mapped to a target [lo, hi] range via the inverse-CDF method.

  uniform  – equal probability across the range
  gumbel   – right-skewed; mode near lo, long tail toward hi
              great for building heights: mostly short, rare tall ones
  normal   – bell curve centred in the range, clipped at the edges
"""

import math
import random


_GUMBEL_LO = -1.0   # ~6th percentile of standard Gumbel
_GUMBEL_HI =  4.5   # ~99th percentile of standard Gumbel


def _gumbel_01(rng: random.Random) -> float:
    """Sample from standard Gumbel, map to [0, 1] via a fixed percentile window."""
    u = max(1e-9, min(1 - 1e-9, rng.random()))
    g = -math.log(-math.log(u))                    # standard Gumbel sample
    t = (g - _GUMBEL_LO) / (_GUMBEL_HI - _GUMBEL_LO)
    return max(0.0, min(1.0, t))


def _normal_01(rng: random.Random) -> float:
    """Sample from Normal(0.5, 0.18), clipped to [0, 1]."""
    return max(0.0, min(1.0, rng.gauss(0.5, 0.18)))


class Sampler:
    """Thin wrapper around random.Random that applies a chosen distribution."""

    def __init__(self, rng: random.Random, dist: str = "uniform"):
        if dist not in ("uniform", "gumbel", "normal"):
            raise ValueError(f"Unknown distribution '{dist}'; choose uniform/gumbel/normal")
        self.rng = rng
        self.dist = dist

    def _sample_01(self) -> float:
        if self.dist == "gumbel":
            return _gumbel_01(self.rng)
        if self.dist == "normal":
            return _normal_01(self.rng)
        return self.rng.random()  # uniform

    def uniform(self, lo: float, hi: float) -> float:
        return lo + self._sample_01() * (hi - lo)

    def randint(self, lo: int, hi: int) -> int:
        """Inclusive randint using the configured distribution."""
        return lo + int(self._sample_01() * (hi - lo + 1 - 1e-9))

    # Pass-through helpers that don't need distribution shaping
    def choice(self, seq):
        return self.rng.choice(seq)

    def choices(self, seq, weights=None, k=1):
        return self.rng.choices(seq, weights=weights, k=k)

    def random(self) -> float:
        return self.rng.random()
