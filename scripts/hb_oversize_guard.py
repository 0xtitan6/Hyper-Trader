#!/usr/bin/env python3
"""HB oversize guard: watch actual HL positions vs each HB's config cap.

Runs every 2 min via systemd timer. For each hyper-hip4-mm-*.service:
  1. Read its config.yaml for max_inventory_usd + trading_pair
  2. Query HL for actual position in that coin
  3. If actual_notional > max_inventory_usd * 1.5:
     - STOP the service
     - Journal state/hb_oversize.jsonl
     - Set state/ESCALATE so operator sees it next cycle

Why 1.5x: real market makers naturally run slightly over cap due to fill timing.
2x+ is the smoking gun that cap enforcement is broken.
"""
from __future__ import annotations
import json, os, subprocess, sys, time, re, yaml
from pathlib import Path

sys.path.insert(0, "/home/ec2-user/.openclaw/workspace/hyper-trader")
import glob
for sp in glob.glob("/home/ec2-user/.openclaw/workspace/hyper-trader/.venv/lib/python*/site-packages"):
    sys.path.insert(0, sp)

from src.config import load_config
from hyperliquid.info import Info

HB_CONF_DIR = Path("/home/ec2-user/.openclaw/workspace/hummingbot-fork/conf")
JOURNAL = Path(__file__).resolve().parent.parent / "state" / "hb_oversize.jsonl"
ESCALATE = Path(__file__).resolve().parent.parent / "state" / "ESCALATE"
OVERSIZE_MULT = 1.5

def load_hb_configs() -> list[tuple[str, str, float]]:
    """Return [(service_slug, coin, max_inv_usd), ...]"""
    out = []
    for f in HB_CONF_DIR.glob("hip4_live_nfl_*.yml"):
        try:
            c = yaml.safe_load(f.read_text())
            slug = f.stem.replace("hip4_live_nfl_", "")
            tp = c.get("trading_pair", "")  # "#117990-USDC"
            coin = tp.split("-")[0] if "-" in tp else tp
            cap = float(c.get("max_inventory_usd", 100))
            out.append((slug, coin, cap))
        except Exception as e:
            print(f"skip {f}: {e}", file=sys.stderr)
    return out


def check_one(info, slug: str, coin: str, cap_usd: float) -> dict:
    """Query HL, return finding dict."""
    try:
        bal = info.post("/info", {"type": "spotClearinghouseState",
                                  "user": load_config().account_address})
        balances = bal.get("balances", []) if isinstance(bal, dict) else []
        # config trading_pair uses perp notation ("#118010") but
        # spotClearinghouseState returns spot notation ("+118010"). Match on the
        # numeric core so the guard actually sees inventory. Without this the
        # lookup never matched and every check reported sz=0 (2026-10-18).
        want = coin.lstrip("#+@")
        for b in balances:
            if str(b.get("coin", "")).lstrip("#+@") == want:
                sz = float(b.get("total", 0))
                # need price — try l2Book
                try:
                    book = info.post("/info", {"type": "l2Book", "coin": coin})
                    bid = float(book["levels"][0][0]["px"]) if book else 0
                    notional = sz * bid
                except Exception:
                    notional = sz * 0.5  # worst-case midpoint fallback
                over = notional > cap_usd * OVERSIZE_MULT
                return {"slug": slug, "coin": coin, "sz": sz,
                        "notional": notional, "cap": cap_usd, "oversize": over}
        return {"slug": slug, "coin": coin, "sz": 0, "notional": 0,
                "cap": cap_usd, "oversize": False}
    except Exception as e:
        return {"slug": slug, "coin": coin, "err": str(e)[:120]}


def stop_hb(slug: str) -> str:
    r = subprocess.run(["systemctl", "--user", "stop", f"hyper-hip4-mm-{slug}.service"],
                       capture_output=True, text=True, timeout=20)
    return "stopped" if r.returncode == 0 else f"stop_err: {r.stderr[:120]}"


def journal(record: dict) -> None:
    record["ts"] = int(time.time())
    JOURNAL.parent.mkdir(exist_ok=True)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    cfg = load_config()
    info = Info(cfg.hyperliquid_api_url, skip_ws=True)
    configs = load_hb_configs()
    print(f"watching {len(configs)} HB makers", file=sys.stderr)
    any_action = False
    for slug, coin, cap in configs:
        f = check_one(info, slug, coin, cap)
        print(f"  {slug}: {coin} sz={f.get('sz',0):.1f} notional=${f.get('notional',0):.2f} cap=${cap}", file=sys.stderr)
        if f.get("oversize"):
            action = stop_hb(slug)
            f["action"] = action
            journal(f)
            # trigger operator next cycle
            with ESCALATE.open("a") as e:
                e.write(f"HB oversize: {slug} {f['notional']:.0f} vs {cap} cap -> {action}\n")
            any_action = True
            print(f"  OVERSIZE on {slug}: ${f['notional']:.0f} vs cap ${cap}. {action}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
