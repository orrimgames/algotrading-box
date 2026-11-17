"""Hyperliquid order-book snapshots and 1-minute candles around 01:00 / 07:00 / 13:00 / 19:00 UTC.
Read-only public endpoint, no key, stdlib only. Research data (how resting limit orders would have filled), nothing trades.

The box fires every ~5 minutes. Around each of the four hours above, from 5 minutes before to 60 minutes after:
  - every fire writes one snapshot: top-5 bid/ask levels of the 120 most traded HL perps (list fixed at the first snapshot)
        -> data/hl_book/<cycle>/book_<HHMMSS>.csv.gz     ts_ms, coin, bids, asks   ("px:sz|px:sz|..." best first)
  - the first fire after the window writes the 1-minute candles of those coins for the window
        -> data/hl_book/<cycle>/candles.csv.gz           t_ms, coin, o, h, l, c, v, n
<cycle> = YYYYmmdd_HH (UTC). One file per snapshot so that git stores every byte once (~15 KB each, ~25 MB per month).
Same columns as the copy logged on Daniel's PC (every 3 minutes there); this one fills the gaps while that PC sleeps."""
import gzip, json, os, time, urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "hl_book")
URL = "https://api.hyperliquid.xyz/info"
HOURS = (1, 7, 13, 19)
N_COINS, LEVELS = 120, 5
LEAD, SPAN = 5 * 60, 60 * 60          # window: hour - 5 min ... hour + 60 min
PACE_BOOK, PACE_CANDLE = 0.2, 1.5     # l2Book weighs 2, candleSnapshot ~21; both stay well under 1200 weight / minute
CANDLE_TRIES = 3


def post(body, timeout=15):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "algotrading-box"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def window(now):
    """(cycle id, trade-hour unix time) if `now` is inside a logging window, else None."""
    h = int(now + LEAD) // 3600 * 3600
    for t_hour in (h, h - 3600):
        g = time.gmtime(t_hour)
        if g.tm_hour in HOURS and t_hour - LEAD <= now < t_hour + SPAN:
            return time.strftime("%Y%m%d_%H", g), t_hour
    return None


def side(levels):
    return "|".join(f"{x['px']}:{x['sz']}" for x in levels[:LEVELS])


def snapshot(state, log, now, cycle, t_hour):
    if state.get("cycle") != cycle:
        meta, ctx = post({"type": "metaAndAssetCtxs"}, 30)
        vol = sorted(((float(c.get("dayNtlVlm") or 0), u["name"]) for u, c in zip(meta["universe"], ctx)
                      if not u.get("isDelisted")), reverse=True)
        state.update(cycle=cycle, t_hour=t_hour, t_start=int(now), coins=[n for _, n in vol[:N_COINS]],
                     snaps=0, rows=0, errs=0, candles="pending", candle_tries=0)
    d = os.path.join(OUT, cycle)
    os.makedirs(d, exist_ok=True)
    lines, errs = [], 0
    for c in state["coins"]:
        try:
            b = post({"type": "l2Book", "coin": c}, 10)
            lines.append(f"{b['time']},{c},{side(b['levels'][0])},{side(b['levels'][1])}")
        except Exception:
            errs += 1
        time.sleep(PACE_BOOK)
    state["errs"] += errs
    if not lines:
        raise RuntimeError(f"cycle {cycle}: snapshot got no books ({errs} errors)")
    name = "book_" + time.strftime("%H%M%S", time.gmtime(now)) + ".csv.gz"
    with gzip.open(os.path.join(d, name), "wt", encoding="utf-8", newline="\n") as f:
        f.write("ts_ms,coin,bids,asks\n" + "\n".join(lines) + "\n")
    state["snaps"] += 1
    state["rows"] += len(lines)
    log(f"cycle {cycle}: snapshot {state['snaps']}, {len(lines)} books, {errs} errors")


def candles(state, log):
    cycle = state["cycle"]
    state["candle_tries"] = state.get("candle_tries", 0) + 1
    t0, t1 = (state["t_start"] - 60) * 1000, (state["t_hour"] + SPAN + 60) * 1000
    lines, errs = [], 0
    for c in state["coins"]:
        try:
            for x in post({"type": "candleSnapshot", "req": {"coin": c, "interval": "1m", "startTime": t0, "endTime": t1}}, 20):
                lines.append(f"{x['t']},{c},{x['o']},{x['h']},{x['l']},{x['c']},{x['v']},{x['n']}")
        except Exception:
            errs += 1
        time.sleep(PACE_CANDLE)
    if errs > len(state["coins"]) // 4 and state["candle_tries"] < CANDLE_TRIES:
        raise RuntimeError(f"cycle {cycle}: candles failed for {errs} coins, will retry")   # HL keeps 1m candles for days
    d = os.path.join(OUT, cycle)
    os.makedirs(d, exist_ok=True)
    with gzip.open(os.path.join(d, "candles.csv.gz"), "wt", encoding="utf-8", newline="\n") as f:
        f.write("t_ms,coin,o,h,l,c,v,n\n" + "\n".join(lines) + "\n")
    state["candles"] = "done"
    state["errs"] += errs
    state["last_done"] = (f"{cycle}: {state['snaps']} snapshots, {state['rows']} book rows, {len(lines)} candle rows, "
                          f"{state['errs']} errors")
    log("finished " + state["last_done"])


def step(state, log, now):
    w = window(now)
    if w:
        snapshot(state, log, now, *w)
    elif state.get("candles") == "pending" and now >= state["t_hour"] + SPAN + 90:
        candles(state, log)


def run(state, log):
    step(state, log, time.time())
