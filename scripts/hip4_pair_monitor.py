#!/usr/bin/env python3
"""HIP-4 one-touch / European-digital pair monitor.

HIP-4 can list two instruments on the same perp, level, expiry and TWAP window:

  template:priceTouch   American barrier — Yes if the mark EVER touches the level
  template:binaryPrice  European digital — Yes only if ABOVE the level at expiry

The barrier strictly dominates the digital and under a driftless model is worth
about 2x it. Buying the barrier plus the digital's NO leg pays 2 in exactly one
state: touch, then close below. Everywhere else it pays 1.

Semantics are read verbatim from the on-chain registry ({"type":"outcomeTemplates"},
undocumented, 18 templates) rather than inferred from names.

WHY THE TRIGGER IS NOT THE OBVIOUS RATIO
----------------------------------------
The tempting implementation prices the structure off vol backed out of the
digital itself:

    iv  = implied_vol(digital_ask, ...)
    p   = onetouch_px(..., iv) - digital_px(..., iv)      # WRONG

`digital_px(..., iv) == digital_ask` by construction, so that ratio collapses to
`(OT(iv) - d_ask) / (touch_ask - d_ask)` — a well-posed measure of how cheap the
touch is RELATIVE to the digital, and completely invariant to both legs being
rich by the same factor. It cannot tell you whether the trade makes money.

The structure's EV is ABSOLUTE. You are long the touch and long the digital's NO
leg; the only paying state is touch-then-close-below, where BOTH legs pay, so
being long the NO leg does not hedge you there. EV = P_true(touch & below) -
premium, and P_true needs REALISED vol.

Measured 2026-09-19 on the live BTC K=100000 pair: relative gap 8.4x, absolute
ratio 0.10x. An ~80x divergence, and the wrong one is the flattering one.

Realised BTC vol ran 32.9-39.7% across standard windows against a 38.0%
breakeven, so the sign flips with the lookback. This uses min() across windows —
the conservative end — precisely because it flips.

Exit codes: 0 actionable, 1 no pairs exist, 2 pairs exist but none qualify.
Read-only. No API key. Stdlib only.
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import datetime, timezone

API = "https://api.hyperliquid.xyz/info"

MIN_EV_RATIO = 3.0        # applied to ABSOLUTE P_true/premium, never the relative gap
MAX_PREMIUM = 0.01        # never pay >1% of notional for the touch-and-reverse state
MAX_UNITS = 2000          # depth-constrained: cost ran 1.00108 -> 1.00974 by 5,000u
RV_WINDOWS_D = (14, 30, 60, 90)


def post(body: dict, timeout: int = 25):
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def parse_kv(desc: str) -> dict:
    out = {}
    for part in str(desc).split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def find_pairs(outcomes: list) -> list[dict]:
    """Match on ALL FIVE of perp, level, expiry, TWAP seconds, price source.

    Matching on fewer pairs contracts that settle off a different price source or
    TWAP window — which is a different trade wearing the same strike.
    """
    touch, dig = {}, {}
    for o in outcomes:
        m = parse_kv(o.get("description", ""))
        perp, t, sec, src = m.get("perp"), m.get("time"), m.get("seconds"), m.get("priceDescription")
        if not perp:
            continue
        if o.get("name") == "template:priceTouch" and m.get("target"):
            touch[(perp, float(m["target"]), t, sec, src)] = o["outcome"]
        elif o.get("name") == "template:binaryPrice" and m.get("threshold"):
            dig[(perp, float(m["threshold"]), t, sec, src)] = o["outcome"]
    return [{"key": k, "touch": touch[k], "digital": dig[k]} for k in touch.keys() & dig.keys()]


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def digital_px(F: float, K: float, T: float, s: float) -> float:
    return norm_cdf((math.log(F / K) - 0.5 * s * s * T) / (s * math.sqrt(T)))


def onetouch_px(F: float, K: float, T: float, s: float) -> float:
    """Undiscounted one-touch. Verified against the reflection principle: the
    ratio to its own digital converges to 2.0 for far barriers (2.018 at
    K=100k/38% vs 2*digital), and never prints below the digital."""
    b = math.log(K / F)
    sq = s * math.sqrt(T)
    if b > 0:
        return norm_cdf((-b - 0.5 * s * s * T) / sq) + (F / K) * norm_cdf((-b + 0.5 * s * s * T) / sq)
    b = -b
    return norm_cdf((-b + 0.5 * s * s * T) / sq) + (K / F) * norm_cdf((-b - 0.5 * s * s * T) / sq)


def implied_vol(price: float, F: float, K: float, T: float, fn) -> float:
    lo, hi = 1e-3, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if fn(F, K, T, mid) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def realised_vol(perp: str) -> tuple[float, dict]:
    """Annualised realised vol from hourly candles. Returns (min, all windows).

    min() is deliberate: the EV sign flips across lookbacks, so the conservative
    window is the one that decides.
    """
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    out = {}
    for d in RV_WINDOWS_D:
        try:
            c = post({"type": "candleSnapshot", "req": {
                "coin": perp, "interval": "1h",
                "startTime": now_ms - d * 86400000, "endTime": now_ms}})
        except Exception:  # noqa: BLE001
            continue
        px = [float(x["c"]) for x in (c or []) if float(x.get("c", 0)) > 0]
        if len(px) < 48:
            continue
        rets = [math.log(px[i + 1] / px[i]) for i in range(len(px) - 1)]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        out[d] = math.sqrt(var) * math.sqrt(24 * 365)
    return (min(out.values()) if out else 0.0), out


def walk(levels: list, n: float) -> tuple[float, float]:
    """Cost of taking n units through the real book. Top-of-book lies: depth
    thinned from 1.00108 to 1.00974 between 2,000 and 5,000 units in testing."""
    got = cost = 0.0
    for lv in levels:
        take = min(n - got, float(lv["sz"]))
        cost += take * float(lv["px"])
        got += take
        if got >= n:
            break
    return cost, got


def mark_for(perp: str) -> float | None:
    dex = perp.split(":")[0] if ":" in perp else None
    body = {"type": "metaAndAssetCtxs"}
    if dex:
        body["dex"] = dex
    meta, ctxs = post(body)
    for u, c in zip(meta["universe"], ctxs):
        if u["name"] == perp and c.get("markPx"):
            return float(c["markPx"])
    return None


def main() -> int:
    pairs = find_pairs(post({"type": "outcomeMeta"})["outcomes"])
    if not pairs:
        print("no matched touch/digital pairs in the live universe")
        return 1

    actionable = []
    for p in pairs:
        perp, K, exp, sec, _src = p["key"]
        try:
            tb = post({"type": "l2Book", "coin": f"#{p['touch'] * 10}"})["levels"]
            db = post({"type": "l2Book", "coin": f"#{p['digital'] * 10}"})["levels"]
            dnb = post({"type": "l2Book", "coin": f"#{p['digital'] * 10 + 1}"})["levels"]
        except Exception as e:  # noqa: BLE001
            print(f"skip  {perp} K={K:g}: book fetch failed ({type(e).__name__})")
            continue
        if not (tb[1] and db[0] and db[1] and dnb[1]):
            continue

        ot_ask, d_bid, d_ask = float(tb[1][0]["px"]), float(db[0][0]["px"]), float(db[1][0]["px"])

        # --- TIER A: model-free. A barrier cannot be worth less than its own
        # European digital at the same strike and expiry. Immune to every vol
        # argument below, which is why it is checked first and unconditionally.
        if ot_ask < d_bid:
            print(f"*** HARD ARB {perp} K={K:g} {exp}: touch ask {ot_ask} < digital bid {d_bid}")
            actionable.append((p, "hard_arb"))
            continue

        T = (datetime.strptime(exp, "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
             - datetime.now(tz=timezone.utc)).total_seconds() / (365.25 * 86400)
        if T <= 0:
            continue
        F = mark_for(perp)
        if F is None:
            continue

        c1, g1 = walk(tb[1], MAX_UNITS)
        c2, g2 = walk(dnb[1], MAX_UNITS)
        n = min(g1, g2)
        if n <= 0:
            continue
        c1, _ = walk(tb[1], n)
        c2, _ = walk(dnb[1], n)
        premium = (c1 + c2) / n - 1.0
        if premium <= 0:
            print(f"*** COST<=PAR {perp} K={K:g} {exp}: structure costs {1 + premium:.5f}")
            actionable.append((p, "cost_below_par"))
            continue

        rv, windows = realised_vol(perp)
        iv_d = implied_vol(d_ask, F, K, T, digital_px)

        # ABSOLUTE probability of the only paying state, at REALISED vol.
        p_true = onetouch_px(F, K, T, rv) - digital_px(F, K, T, rv) if rv > 0 else 0.0
        ev = p_true - premium
        ratio = p_true / premium if premium > 0 else float("inf")

        # Reported for monitoring only. This is the number that flatters; if you
        # ever find yourself wiring it to the trigger, re-read the docstring.
        rel_only = ((onetouch_px(F, K, T, iv_d) - d_ask) / (ot_ask - d_ask)
                    if ot_ask > d_ask else float("inf"))

        verdict = "TRADE" if (ratio >= MIN_EV_RATIO and premium <= MAX_PREMIUM and ev > 0) else "skip"
        wins = " ".join(f"{d}d={v * 100:.1f}%" for d, v in sorted(windows.items()))
        print(f"{verdict:5} {perp} K={K:g} {exp} {T * 365.25:5.1f}d | "
              f"premium {premium:.5f} P_true {p_true:.5f} EV {ev:+.5f} ratio {ratio:4.2f}x | "
              f"{n:.0f}u ${c1 + c2:,.0f} | rv {rv * 100:.1f}% ivD {iv_d * 100:.1f}% "
              f"(rel-only {rel_only:.1f}x) [{wins}]")
        if verdict == "TRADE":
            actionable.append((p, "structure"))

    return 0 if actionable else 2


if __name__ == "__main__":
    sys.exit(main())
