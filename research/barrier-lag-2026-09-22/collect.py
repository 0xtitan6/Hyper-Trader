"""Synchronised barrier-book / underlying collector for the lead-lag question.

Clocks: every record carries `lt` = local receive time. That is the ONLY clock
used for lead-lag; server `time` fields come from different subsystems.

Sources:
  ws  activeAssetCtx BTC,HYPE   -> markPx (the barrier's settlement reference), ~1/s periodic
  ws  trades BTC,HYPE           -> event-driven perp prints, sub-second underlying clock
  ws  l2Book #barriers          -> periodic ~5.3s snapshot (backstop only)
  ws  trades #barriers          -> barrier prints
  rest l2Book #barriers         -> ~1.2s polled book, the real book clock
"""
import json, sys, time, threading
import requests, websocket

OUT, DUR = sys.argv[1], float(sys.argv[2])
BARRIERS = ["#12090", "#12120", "#12130"]   # HYPE100, BTC95k, BTC90k -- YES legs
UNDER = ["BTC", "HYPE"]
INFO = "https://api.hyperliquid.xyz/info"

f = open(OUT, "w"); lock = threading.Lock()
n = {"book": 0, "ctx": 0, "utrade": 0, "btrade": 0, "rest": 0, "err": 0}
stop = threading.Event()

def w(rec):
    with lock:
        f.write(json.dumps(rec) + "\n")

def poller():
    s = requests.Session()
    while not stop.is_set():
        for c in BARRIERS:
            if stop.is_set(): break
            try:
                t0 = time.time()
                r = s.post(INFO, json={"type": "l2Book", "coin": c}, timeout=10)
                lt = time.time()
                if r.status_code == 429:
                    n["err"] += 1; time.sleep(5); continue
                d = r.json(); lv = d.get("levels", [[], []])
                bids, asks = (list(lv) + [[], []])[:2]
                w({"k": "rest", "lt": lt, "rtt": round(lt - t0, 4), "st": d.get("time"), "coin": c,
                   "b": [[x["px"], x["sz"]] for x in bids[:5]],
                   "a": [[x["px"], x["sz"]] for x in asks[:5]]})
                n["rest"] += 1
            except Exception:
                n["err"] += 1
            time.sleep(0.12)
        stop.wait(0.9)

def on_open(ws):
    for c in BARRIERS:
        ws.send(json.dumps({"method":"subscribe","subscription":{"type":"l2Book","coin":c}}))
        ws.send(json.dumps({"method":"subscribe","subscription":{"type":"trades","coin":c}}))
    for u in UNDER:
        ws.send(json.dumps({"method":"subscribe","subscription":{"type":"activeAssetCtx","coin":u}}))
        ws.send(json.dumps({"method":"subscribe","subscription":{"type":"trades","coin":u}}))
    print("subscribed", flush=True)

def on_message(_ws, msg):
    lt = time.time()
    try: m = json.loads(msg)
    except Exception: return
    ch, d = m.get("channel"), m.get("data")
    if ch == "l2Book" and isinstance(d, dict):
        lv = d.get("levels", [[], []]); bids, asks = (list(lv)+[[],[]])[:2]
        w({"k":"book","lt":lt,"st":d.get("time"),"coin":d.get("coin"),
           "b":[[x["px"],x["sz"]] for x in bids[:5]], "a":[[x["px"],x["sz"]] for x in asks[:5]]})
        n["book"] += 1
    elif ch == "activeAssetCtx" and isinstance(d, dict):
        ctx = d.get("ctx") or {}
        w({"k":"ctx","lt":lt,"coin":d.get("coin"),"mark":ctx.get("markPx"),
           "oracle":ctx.get("oraclePx"),"mid":ctx.get("midPx")})
        n["ctx"] += 1
    elif ch == "trades" and isinstance(d, list):
        for t in d:
            c = t.get("coin")
            kind = "btrade" if str(c).startswith("#") else "utrade"
            w({"k":kind,"lt":lt,"st":t.get("time"),"coin":c,"px":t.get("px"),
               "sz":t.get("sz"),"side":t.get("side")})
            n[kind] += 1

ws = websocket.WebSocketApp("wss://api.hyperliquid.xyz/ws", on_open=on_open, on_message=on_message,
                            on_error=lambda _w,e: print("ERR",e,flush=True))
threading.Thread(target=lambda: ws.run_forever(ping_interval=20), daemon=True).start()
threading.Thread(target=poller, daemon=True).start()
t0 = time.time(); end = t0 + DUR
while time.time() < end:
    time.sleep(30)
    print(f"t={time.time()-t0:.0f}s {n}", flush=True)
stop.set(); ws.close(); time.sleep(1.0); f.flush(); f.close()
print("DONE", n, flush=True)
