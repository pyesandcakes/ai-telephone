"""AI Telephone host: Python 3.11+, standard-library server, local-only controls."""
import argparse
import copy
import hashlib
import ipaddress
import json
import os
import platform
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from models import DemoModels, LocalModels, VISION_INSTRUCTION

BASE = Path(__file__).resolve().parent
DEFAULTS = {"interval": 5, "limit": 0, "seed": 42, "steps": 1,
            "image_model": "stabilityai/sd-turbo",
            "revision": "b261bac6fd2cf515557d5d0707481eafa0485ec2",
            "vision_model": "qwen2.5vl:3b"}


def now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def settings_from(data):
    result = dict(DEFAULTS)
    for key, low, high, cast in (("interval", 0, 3600, float), ("limit", 0, 10000, int),
                                 ("seed", 0, 2**31 - 1, int), ("steps", 1, 4, int)):
        value = data.get(key, result[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise ValueError(f"Invalid {key}")
        if cast is int and int(value) != value:
            raise ValueError(f"{key} must be a whole number")
        result[key] = cast(value)
    model = data.get("vision_model", result["vision_model"])
    if model not in ("qwen2.5vl:3b", "qwen2.5vl:7b"):
        raise ValueError("Choose Qwen2.5-VL 3B or 7B")
    result["vision_model"] = model
    return result


class Installation:
    def __init__(self, root, demo=False, adapter=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.demo = demo
        self.adapter = adapter or (DemoModels() if demo else LocalModels())
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.phase = "idle"
        self.current = None
        self.published = None
        self.error = None
        self.token = secrets.token_urlsafe(32)
        self.events = []

    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def event(self, name, **fields):
        with self.lock:
            item = {"time": now(), "event": name, **fields}
            self.events.append(item)
            self.events = self.events[-100:]
            if self.current:
                with (self.root / self.current["id"] / "events.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps(item) + "\n")

    def start(self, data):
        prompt = data.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise ValueError("Enter a prompt of 1–4000 characters")
        settings = settings_from(data)
        with self.lock:
            if self.active():
                raise ValueError("A run is already active; stop it first")
            self.stop_event.clear()
            run_id = uuid.uuid4().hex
            folder = self.root / run_id
            folder.mkdir()
            self.current = {"id": run_id, "created": now(), "original_prompt": prompt.strip(),
                            "settings": settings, "demo": self.demo, "status": "running",
                            "python": platform.python_version(), "platform": platform.platform(),
                            "vision_instruction": VISION_INSTRUCTION}
            save_json(folder / "manifest.json", self.current)
            self.error = None
            self.phase = "starting"
            self.event("started", run=run_id)
            self.thread = threading.Thread(target=self.loop, name="telephone-loop", daemon=True)
            self.thread.start()
            return run_id

    def stop(self):
        with self.lock:
            if self.active():
                self.stop_event.set()
                self.phase = "stopping"
                self.event("stop_requested")

    def set_phase(self, phase):
        with self.lock:
            self.phase = "stopping" if self.stop_event.is_set() else phase

    def loop(self):
        run = self.current
        folder = self.root / run["id"]
        settings = run["settings"]
        prompt = run["original_prompt"]
        count = 0
        try:
            if not self.demo:
                from prepare import environment
                run["environment"] = environment()
                available = {model["name"] for model in run["environment"]["models"]}
                if settings["vision_model"] not in available:
                    raise ValueError("Pull the selected vision model in Ollama before starting")
                save_json(folder / "manifest.json", run)
            while not self.stop_event.is_set():
                count += 1
                seed = (settings["seed"] + count - 1) % (2**31)
                started = time.monotonic()
                temp_image = folder / "pending.png"
                self.set_phase("generating image")
                self.event("image_started", iteration=count, seed=seed)
                self.adapter.generate(prompt, temp_image, settings, seed, folder / "worker.log")
                if self.stop_event.is_set():
                    break
                self.set_phase("interpreting image")
                self.event("vision_started", iteration=count)
                # Only pixels cross the vision adapter boundary. No run or prompt object.
                caption = self.adapter.describe(temp_image.read_bytes(), settings, seed)
                if self.stop_event.is_set():
                    break
                filename = f"{count:06d}.png"
                os.replace(temp_image, folder / filename)
                record = {"iteration": count, "time": now(), "seed": seed,
                          "input": prompt, "caption": caption, "image": filename,
                          "sha256": hashlib.sha256((folder / filename).read_bytes()).hexdigest(),
                          "seconds": round(time.monotonic() - started, 3)}
                # An iteration is committed by its JSON file. Incomplete PNGs are ignored.
                save_json(folder / f"{count:06d}.json", record)
                with self.lock:
                    self.published = {"run": run["id"], "iteration": count,
                                      "caption": caption, "image": f"/images/{run['id']}/{filename}"}
                self.event("iteration_completed", iteration=count, seconds=record["seconds"])
                prompt = caption
                if settings["limit"] and count >= settings["limit"]:
                    break
                self.set_phase("holding")
                self.stop_event.wait(settings["interval"])
            with self.lock:
                self.phase = "stopped" if self.stop_event.is_set() else "completed"
                run["status"] = self.phase
                self.event(self.phase)
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"
                self.phase = "error"
                run["status"] = "error"
                self.event("error", detail=self.error)
        finally:
            (folder / "pending.png").unlink(missing_ok=True)
            run["ended"] = now()
            save_json(folder / "manifest.json", run)

    def public_state(self):
        with self.lock:
            # Explicit allowlist: prompts, history, logs and raw errors stay private.
            return {"phase": self.phase, "demo": self.demo, "frame": copy.deepcopy(self.published)}

    def run_folder(self, run_id):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid run")
        folder = self.root / run_id
        if not folder.is_dir():
            raise ValueError("Run not found")
        return folder

    def history(self, run_id, offset=0):
        folder = self.run_folder(run_id)
        files = sorted(folder.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"), reverse=True)
        return {"total": len(files), "offset": offset,
                "items": [json.loads(p.read_text(encoding="utf-8")) for p in files[offset:offset + 50]]}

    def runs(self):
        result = []
        for path in self.root.glob("*/manifest.json"):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
                if run["status"] == "running" and (not self.current or run["id"] != self.current["id"]):
                    run["status"] = "interrupted"
                result.append(run)
            except (ValueError, OSError, KeyError):
                continue
        return sorted(result, key=lambda r: r["created"], reverse=True)

    def replay(self, run_id, iteration):
        with self.lock:
            if self.active():
                raise ValueError("Stop the loop before replaying history")
            folder = self.run_folder(run_id)
            if not isinstance(iteration, int) or not 1 <= iteration <= 999999:
                raise ValueError("Invalid iteration")
            record = json.loads((folder / f"{iteration:06d}.json").read_text(encoding="utf-8"))
            self.published = {"run": run_id, "iteration": iteration, "caption": record["caption"],
                              "image": f"/images/{run_id}/{record['image']}"}
            self.phase = "replay"


def handler_for(installation):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log tokens or prompts from requests.

        def send(self, code, body, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def admin(self):
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                self.send(403, {"error": "Controls are available on the host laptop only"})
                return False
            supplied = self.headers.get("Authorization", "")
            if not secrets.compare_digest(supplied, "Bearer " + installation.token):
                self.send(401, {"error": "Open the control link printed in the host terminal"})
                return False
            return True

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/state":
                    return self.send(200, installation.public_state())
                if path == "/api/admin":
                    if not self.admin(): return
                    with installation.lock:
                        return self.send(200, {**installation.public_state(), "active": installation.active(),
                                               "error": installation.error, "events": installation.events[-30:],
                                               "runs": installation.runs()})
                if path == "/api/history":
                    if not self.admin(): return
                    query = parse_qs(parsed.query)
                    offset = max(0, int(query.get("offset", ["0"])[0]))
                    return self.send(200, installation.history(query.get("run", [""])[0], offset))
                match = re.fullmatch(r"/images/([a-f0-9]{32})/([0-9]{6})\.png", path)
                if match:
                    folder = installation.run_folder(match[1])
                    # Only committed images may be served.
                    if not (folder / (match[2] + ".json")).is_file():
                        return self.send(404, {"error": "Image not found"})
                    return self.send(200, (folder / (match[2] + ".png")).read_bytes(), "image/png")
                static = {"/": "control.html", "/image": "display.html", "/text": "display.html", "/combined": "display.html",
                          "/app.js": "app.js", "/style.css": "style.css", "/gallery.css": "gallery.css"}
                if path in static:
                    name = static[path]
                    kind = "text/html; charset=utf-8" if name.endswith("html") else "text/css" if name.endswith("css") else "text/javascript"
                    return self.send(200, (BASE / "web" / name).read_bytes(), kind)
                self.send(404, {"error": "Not found"})
            except (ValueError, FileNotFoundError):
                self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.admin(): return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Request too large or empty")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict): raise ValueError("Expected a JSON object")
                path = urlparse(self.path).path
                if path == "/api/start":
                    return self.send(200, {"run": installation.start(data)})
                if path == "/api/stop":
                    installation.stop()
                    return self.send(200, {"ok": True})
                if path == "/api/replay":
                    installation.replay(data.get("run", ""), data.get("iteration"))
                    return self.send(200, {"ok": True})
                self.send(404, {"error": "Not found"})
            except (ValueError, TypeError, FileNotFoundError) as exc:
                self.send(400, {"error": str(exc)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Test displays without models")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runs", type=Path, default=BASE / "runs")
    args = parser.parse_args()
    installation = Installation(args.runs, args.demo)
    server = ThreadingHTTPServer((args.bind, args.port), handler_for(installation))
    print(f"Controls: http://127.0.0.1:{args.port}/#token={installation.token}", flush=True)
    print(f"Displays: http://<host-LAN-IP>:{args.port}/image and /text", flush=True)
    print(f"One laptop: http://127.0.0.1:{args.port}/combined", flush=True)
    print("DEMO MODE — no AI models" if args.demo else "LOCAL MODE — SD-Turbo + Ollama", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        installation.stop()
        print("Waiting for the current model call to finish (image ≤15 min; vision ≤5 min)...", flush=True)
        if installation.thread:
            installation.thread.join(timeout=910)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
