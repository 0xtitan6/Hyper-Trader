"""P0c criterion 4: how does the selected set change when the solvency gate
reads every clearinghouse instead of the base dex only?

Read-only. Re-screens the SAME 60 wallets under both equity reads.
"""
import json, sys
from hyperliquid.info import Info
from src.config import load_config
from src.leaders import _base_equity_usd, _perp_equity_usd, hip3_dex_names

cfg = load_config("config.yaml")
info = Info(base_url="https://api.hyperliquid.xyz", skip_ws=True)
thr = cfg.discovery.min_leader_equity_usd
names = hip3_dex_names(info)
data = json.load(open("/tmp/screen_perdex.json"))

rows = []
for c in data["detail"]:
    addr = c["address"]
    base = _base_equity_usd(info, addr.lower())
    new = _perp_equity_usd(info, addr.lower(), min_usd=thr, dex_names=names)
    # The gate's own rule, both ways: reject only on a KNOWN under-threshold read.
    old_rej = base is not None and base < thr
    new_rej = new is not None and new < thr
    rows.append((addr, base, new, old_rej, new_rej))

flipped = [r for r in rows if r[3] and not r[4]]
print(f"threshold = ${thr:,.0f}   HIP-3 clearinghouses = {names}")
print(f"wallets screened: {len(rows)}")
print(f"rejected as insolvent  BEFORE (base-only): {sum(1 for r in rows if r[3])}")
print(f"rejected as insolvent  AFTER  (per-dex)  : {sum(1 for r in rows if r[4])}")
print(f"\nNO LONGER wrongly rejected ({len(flipped)}):")
for addr, base, new, _, _ in sorted(flipped, key=lambda r: -(r[2] or 0)):
    print(f"  {addr[:12]}  base ${base:>12,.2f}  ->  best-dex ${new:>14,.2f}")
still = [r for r in rows if r[4]]
print(f"\nstill rejected (genuinely under ${thr:,.0f} on every clearinghouse): {len(still)}")
for addr, base, new, _, _ in sorted(still, key=lambda r: -(r[2] or 0))[:6]:
    print(f"  {addr[:12]}  base ${base:>12,.2f}  ->  best-dex ${new:>12,.2f}")
unknown = [r for r in rows if r[2] is None]
print(f"\nUNKNOWN after (not rejected, INV 4): {len(unknown)}")
