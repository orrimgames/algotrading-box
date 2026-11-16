"""Sample job: poll BTC/ETH/SOL spot from Coinbase's public API (no key),
append to data/prices.jsonl, trim to the last 20k lines (~9 weeks at 5-min)."""
import json, os, urllib.request

COINS = ["BTC", "ETH", "SOL"]
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "prices.jsonl")
MAX_LINES = 20000

def spot(coin):
    url = f"https://api.coinbase.com/v2/prices/{coin}-USD/spot"
    req = urllib.request.Request(url, headers={"User-Agent": "algotrading-box"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return float(json.load(r)["data"]["amount"])

def run(state, log):
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {"ts": ts}
    for c in COINS:
        try:
            row[c] = spot(c)
        except Exception as e:
            log(f"{c} spot failed: {e}")
    if len(row) > 1:
        with open(DATA, "a") as f:
            f.write(json.dumps(row) + "\n")
        with open(DATA) as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            with open(DATA, "w") as f:
                f.writelines(lines[-MAX_LINES:])
        state["last_prices"] = row
        log("prices " + " ".join(f"{c}={row[c]}" for c in COINS if c in row))
