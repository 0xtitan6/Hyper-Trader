"""Process-wide token-bucket rate limiter for HL /info calls.

The problem (2026-10-01): the live engine was generating 168 HTTP 429s in 3
hours during normal operation. Root cause: discover_leaders fires ~960 serial
HL calls per 10-min cycle at ~16 req/s with 100 ms per-page delays, right at
HL's documented ~20 req/s per-IP cap, with no headroom for position reconcile
or book_logger. Any concurrent call tips over.

This module gives the trader a single global budget it must spend from. Call
`hl_token_bucket().acquire()` before any heavy /info call that would otherwise
free-run against the per-IP limit. The limiter blocks the caller just long
enough to keep the long-run average under `rate_per_sec`, with `burst`
tokens buffered for short spikes (startup, reconcile).

Not applied to: order placement (/exchange), WS messages (not rate-limited the
same way), or Kalshi/Polymarket pollers (different APIs, different IPs don't
matter — they're not throttled by HL). ONLY the paths we identified in logs as
the 429 generators.

Thread-safe. Process-local (no coordination across machines/processes — HL
counts per IP, so our one trader process owning the budget is the right scope).

Safe to call from anywhere; no HL state is touched, no HTTP is done here. If
the engine isn't rate-limiting its /info calls, this file is a no-op even if
imported. The caller must explicitly `.acquire()`.
"""

from __future__ import annotations

import threading
import time


class _TokenBucket:
    """Simple token-bucket. Not for direct use — see `hl_token_bucket()`."""

    def __init__(self, rate_per_sec: float, burst: int) -> None:
        if rate_per_sec <= 0:
            raise ValueError(f"rate_per_sec must be > 0, got {rate_per_sec}")
        if burst < 1:
            raise ValueError(f"burst must be >= 1, got {burst}")
        self._rate = float(rate_per_sec)
        self._burst = float(burst)
        self._tokens = float(burst)  # start full so startup doesn't block
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> float:
        """Block until `tokens` are available; return seconds slept.

        Returns 0.0 if the caller did not have to wait. Callers can use the
        return value to log "we're being rate-limited by our own gate."
        """
        if tokens <= 0:
            return 0.0
        with self._lock:
            now = time.monotonic()
            # Refill
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            # Need to wait for `tokens - self._tokens` more tokens to accrue.
            needed = tokens - self._tokens
            wait_s = needed / self._rate
            self._tokens = 0.0
            # Release lock while sleeping so other threads can refill estimate
            # when they return. We re-acquire implicitly through the `with`.
        time.sleep(wait_s)
        with self._lock:
            # Account for the fact that we're consuming the tokens we just
            # waited for — refill once more to reflect the sleep, then subtract.
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            # We already waited for exactly `wait_s`, which produces exactly
            # `needed` tokens. Consume them.
            self._tokens = max(0.0, self._tokens - needed)
        return wait_s


# Chosen for HL's documented ~1200 req/min (~20 req/s) per-IP cap on /info.
# 10 req/s long-run leaves ~50% headroom for position reconcile, book_logger,
# and ad-hoc user shell probes. Burst of 20 covers the natural "one leader's
# pagination + its clearinghouse calls" sequence (~15-30 calls back-to-back)
# without stalling on each one.
_DEFAULT_RATE_PER_SEC = 10.0
_DEFAULT_BURST = 20

_bucket: _TokenBucket | None = None
_bucket_lock = threading.Lock()


def hl_token_bucket(
    rate_per_sec: float = _DEFAULT_RATE_PER_SEC,
    burst: int = _DEFAULT_BURST,
) -> _TokenBucket:
    """Return the process-wide token bucket for HL /info calls.

    Lazily constructed on first access. Rate/burst arguments only apply on the
    FIRST call; subsequent calls return the same bucket regardless of what
    they pass (keeps the budget global). Tests that want a different budget
    should import and construct `_TokenBucket` directly.
    """
    global _bucket
    if _bucket is not None:
        return _bucket
    with _bucket_lock:
        if _bucket is None:
            _bucket = _TokenBucket(rate_per_sec=rate_per_sec, burst=burst)
    return _bucket
