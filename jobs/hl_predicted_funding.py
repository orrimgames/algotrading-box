"""Hourly snapshot of Hyperliquid `predictedFundings` (current predicted funding for Binance, Bybit and Hyperliquid perps).
Read-only public endpoint, no key, stdlib only. Research data, nothing trades on it.

The box fires every ~5 minutes; this job writes one snapshot per hour, at the first fire at or after minute :45 (funding
settles on the hour, so a late-in-the-hour value is the useful one). If that window is missed (GitHub cron lag), it catches
up as soon as the last snapshot is more than 75 minutes old.

Output: data/hl_predicted/YYYY-MM-DD.csv.gz (gzip members concatenate; pandas reads the file as one CSV)
    ts (unix s, request time), coin, venue, rate, next_time (unix s), interval_h
Same format as the copy logged on Daniel's PC; this one fills the gaps while that PC sleeps."""
import gzip, json, os, time, urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "hl_predicted")
URL = "https://api.hyperliquid.xyz/info"


def fetch():
    req = urllib.request.Request(URL, data=json.dumps({"type": "predictedFundings"}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "algotrading-box"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def due(now, last):
    if not last:
        return True
    age = now - last
    return (time.gmtime(now).tm_min >= 45 and age >= 50 * 60) or age >= 75 * 60


def run(state, log):
    ts = int(time.time())
    if not due(ts, state.get("last_ts")):
        return
    err = None
    for _ in range(3):
        try:
            data = fetch()
            break
        except Exception as e:
            err = e
            time.sleep(10)
    else:
        state["fails"] = state.get("fails", 0) + 1
        raise RuntimeError(f"predictedFundings failed 3x: {type(err).__name__}: {err}")
    rows = []
    for coin, venues in data:
        for venue, v in venues or []:
            if not v or v.get("fundingRate") is None:
                continue
            rows.append(f"{ts},{coin},{venue},{v['fundingRate']},{int(v.get('nextFundingTime') or 0) // 1000},"
                        f"{v.get('fundingIntervalHours') or ''}")
    if not rows:
        raise RuntimeError("predictedFundings returned no rows")
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, time.strftime("%Y-%m-%d", time.gmtime(ts)) + ".csv.gz")
    new = not os.path.exists(path)
    with gzip.open(path, "at", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("ts,coin,venue,rate,next_time,interval_h\n")
        f.write("\n".join(rows) + "\n")
    state["last_ts"] = ts
    state["last_rows"] = len(rows)
    state["snapshots"] = state.get("snapshots", 0) + 1
    log(f"snapshot {len(rows)} rows -> {os.path.basename(path)}")
