"""Self-contained Black-Scholes greeks.

Replaces ``py_vollib`` (which drags in ``py_lets_be_rational``, a fragile native build on
recent Python). We only need the standard normal CDF, which ``math.erf`` gives us exactly,
so the whole thing is a few lines of pure stdlib + math.
"""

from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))


def delta(flag: str, S: float, K: float, T: float, r: float, sigma: float):
    """Black-Scholes delta.

    ``flag`` is ``"c"`` for calls or ``"p"`` for puts (matching py_vollib's convention).
    Returns ``None`` for degenerate inputs (non-positive vol/time/price) so callers can
    skip illiquid rows without crashing.
    """
    if sigma <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None
    d1 = _d1(S, K, T, r, sigma)
    if flag == "c":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


def bs_price(flag: str, S: float, K: float, T: float, r: float, sigma: float):
    """Black-Scholes theoretical option price. Returns ``None`` for degenerate inputs."""
    if sigma <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None
    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    disc = math.exp(-r * T)
    if flag == "c":
        return S * _norm_cdf(d1) - K * disc * _norm_cdf(d2)
    return K * disc * _norm_cdf(-d2) - S * _norm_cdf(-d1)
