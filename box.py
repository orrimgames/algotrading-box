#!/usr/bin/env python3
"""algotrading-box: free always-on runner on GitHub Actions.

Fires every 5 minutes via cron (see .github/workflows/box.yml).
Each job in jobs/ is a python module with run(state, log) -> None.
State persists in the repo (state/ and data/), committed after every run.
A failing job never kills the box: it is caught and recorded in state/status.json.
"""
import json, os, time, traceback, importlib.util, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state")
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_state():
    p = os.path.join(STATE_DIR, "state.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"runs": 0, "first_run": now_iso(), "jobs": {}}

def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)

def run_job(name, path, state):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    def log(msg):
        print(f"[{now_iso()}] {name}: {msg}", flush=True)
    mod.run(state.setdefault("jobs", {}).setdefault(name, {}), log)

def main():
    state = load_state()
    state["runs"] = state.get("runs", 0) + 1
    state["last_run"] = now_iso()
    status = {"last_run": state["last_run"], "runs": state["runs"],
              "first_run": state["first_run"], "jobs": {}, "box": "alive"}
    jobs_dir = os.path.join(ROOT, "jobs")
    for fn in sorted(os.listdir(jobs_dir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        t0 = time.time()
        try:
            run_job(name, os.path.join(jobs_dir, fn), state)
            status["jobs"][name] = {"ok": True, "secs": round(time.time() - t0, 2)}
        except Exception as e:
            status["jobs"][name] = {"ok": False, "error": f"{type(e).__name__}: {e}",
                                    "secs": round(time.time() - t0, 2)}
            traceback.print_exc()
    save_json(os.path.join(STATE_DIR, "state.json"), state)
    save_json(os.path.join(STATE_DIR, "status.json"), status)
    with open(os.path.join(ROOT, "STATUS.md"), "w") as f:
        f.write(f"# algotrading-box status\n\n"
                f"- box last ran: **{status['last_run']}** (UTC)\n"
                f"- total runs: {status['runs']} since {status['first_run']}\n"
                f"- cadence target: every 5 min (GitHub cron can lag under load)\n\n"
                f"| job | ok | secs | error |\n|---|---|---|---|\n")
        for name, j in status["jobs"].items():
            f.write(f"| {name} | {j['ok']} | {j['secs']} | {j.get('error','')} |\n")
    print(f"run {state['runs']} done", flush=True)

if __name__ == "__main__":
    main()
