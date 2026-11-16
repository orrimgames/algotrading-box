# algotrading-box

A free, always-on-ish compute box for algotrading, built on GitHub Actions.
No card, no cost, no expiry. Lives at `danielharkin21/algotrading-box`.

## What it is
- A GitHub Actions workflow fires **every 5 minutes** (cron `*/5 * * * *`).
- Each fire boots a fresh Linux runner (2 vCPU, 7 GB RAM), runs every python
  module in `jobs/`, then commits its state back to this repo.
- State persists across runs in `state/` (JSON) and `data/` (append-only logs).
- `STATUS.md` shows the last run time - the liveness tell, since cron can lag.

## Honest limits
- **Cadence**: nominally 5 min; under GitHub load, scheduled runs can lag
  minutes to tens of minutes. Good for scanning/polling, not for
  sub-minute reaction.
- **Not SSH**: no interactive shell; jobs are code in `jobs/`.
- **6 h max per run**, 10 min configured timeout here.
- **Public repo**: never commit secrets. Read-only API keys go in
  Settings > Secrets > Actions, referenced as env vars.
- Public repo = Actions minutes are free and unlimited on standard runners.
- Scheduled workflows keep running as long as the repo has activity;
  the box's own commits count as activity.

## Add a job
Drop `jobs/myjob.py` in with:
```python
def run(state, log):
    # state: dict persisted across runs (state["jobs"]["myjob"])
    # log(msg): prints + lands in the Actions log
    ...
```
It runs on the next fire. A crashing job is recorded in status and never
stops the other jobs.

## Included jobs
- `heartbeat.py` - liveness counter.
- `price_ticker.py` - BTC/ETH/SOL spot every run into `data/prices.jsonl`
  (rolling 20k lines, ~9 weeks). Proof the box polls the world on its own.

## Kill switch
Actions tab > algotrading-box > `...` > Disable workflow. Or delete the file.
