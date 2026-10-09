"""Generate a real local 18-frame feedback chain and preserve original provenance."""
import json
import time
from app import BASE, Installation

def main():
    app = Installation(BASE / "runs")
    run = app.start({"prompt": "A red umbrella floating above an empty swimming pool at night, cinematic light, photographic detail", "limit": 18, "interval": 0, "steps": 4})
    seen = 0
    while app.active():
        frame = app.public_state()["frame"]
        if frame and frame["iteration"] != seen:
            seen = frame["iteration"]
            print(f"Completed {seen}/18: {frame['caption']}", flush=True)
        time.sleep(2)
    if app.error:
        raise RuntimeError(app.error)
    if app.history(run)["total"] != 18:
        raise RuntimeError("Incomplete chain")
    (BASE / "real-demo.json").write_text(json.dumps({"run": run, "folder": str(BASE / "runs" / run)}, indent=2))
    print(f"Saved original real-model chain: {run}", flush=True)

if __name__ == "__main__":
    main()
