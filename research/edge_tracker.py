"""Edge/maker metric tracker — turns the one-shot analyses into a weekly trend.

Runs the two core analyses on the CURRENT accumulated data and appends a dated
record so we can watch the go/no-go metrics converge (or not) over the dry-run week:
  - within-market flow->forward-move rho  (edge_analysis; ~0 = no directional alpha)
  - maker-replay NET P&L + adverse-selection %  (maker_replay; the profitability gate)
  - sample counts (data maturity)

Appends one line to research/edge_track.jsonl. Re-run daily. Read-only on the data.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone

REPO = "/home/ec2-user/.openclaw/workspace/hyper-trader"
PY = f"{REPO}/.venv/bin/python"
OUT = f"{REPO}/research/edge_track.jsonl"


def grab(script):
    try:
        return subprocess.run([PY, f"{REPO}/research/{script}"], capture_output=True,
                              text=True, timeout=300, cwd=REPO).stdout
    except Exception as e:
        return f"ERR {e}"


def num_after(text, marker, cast=float):
    """value that immediately follows a marker token in the output."""
    for line in text.splitlines():
        if marker in line:
            tail = line.split(marker, 1)[1].strip()
            tok = tail.replace("=", " ").replace("$", " ").replace("%", " ").split()[0]
            try:
                return cast(tok)
            except Exception:
                pass
    return None


def main():
    ea = grab("edge_analysis.py")
    mr = grab("maker_replay.py")
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "within_market_rho": num_after(ea, "WITHIN-market weighted-mean rho ="),
        "aligned_samples": num_after(ea, "aligned samples:", int),
        "maker_net": num_after(mr, "NET maker P&L:"),
        "maker_fills": num_after(mr, "real HL tape:", int),
        "advsel_pct_of_spread": num_after(mr, "adv-sel as % of spread:"),
    }
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
