"""Liveness: records each beat; the status page shows the box is alive."""
def run(state, log):
    beats = state.get("beats", 0) + 1
    state["beats"] = beats
    log(f"beat {beats}")
