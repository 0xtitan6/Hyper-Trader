"""How many of the 60 hold ANY money on a HIP-3 dex? Explains 9 vs '18-21'."""
import json
from hyperliquid.info import Info
from src.leaders import _base_equity_usd, _dex_equity_usd, hip3_dex_names

info = Info(base_url="https://api.hyperliquid.xyz", skip_ws=True)
names = hip3_dex_names(info)
addrs = [c["address"] for c in json.load(open("/tmp/screen_perdex.json"))["detail"]]
any_hip3 = base_zero_any_hip3 = 0
for a in addrs:
    base = _base_equity_usd(info, a.lower()) or 0.0
    best = max((_dex_equity_usd(info, a.lower(), d) or 0.0) for d in names)
    if best > 0:
        any_hip3 += 1
        if base == 0:
            base_zero_any_hip3 += 1
print(f"of {len(addrs)}: hold ANY HIP-3 equity > $0        : {any_hip3}")
print(f"           base $0 AND some HIP-3 equity > $0: {base_zero_any_hip3}")
