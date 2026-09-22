import json, time, urllib.request
INFO="https://api.hyperliquid.xyz/info"
def post(body, url=INFO):
    req=urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out=json.loads(r.read().decode())
            time.sleep(0.08)
            return out
        except Exception as e:
            if attempt==4: raise
            time.sleep(1.5*(attempt+1))
