"""AI Telephone host: Python 3.11+, standard-library server, local-only controls."""
import argparse
import base64
import io
import warnings
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
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from models import DemoModels, LocalModels, RecordedModels, VISION_INSTRUCTION

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
    def __init__(self, root, demo=False, adapter=None, default_mode="live-demo"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.default_mode = default_mode
        self.demo = demo
        self.adapter = adapter or (DemoModels() if demo else LocalModels())
        self.recorded = isinstance(self.adapter, RecordedModels)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.phase = "idle"
        self.current = None
        self.published = None
        self.error = None
        self.token = secrets.token_urlsafe(32)
        self.events = []
        self.iteration = 0
        self.completed = 0
        self.playback = False
        self.playback_total = 0
        self.presentation_prompt = None

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
        input_type = data.get("input_type", "text")
        if input_type not in ("text", "photo"):
            raise ValueError("Choose Text or Photo")
        photo = None
        if input_type == "photo":
            if self.recorded or (self.demo and type(self.adapter) is DemoModels):
                raise ValueError("Photo starts require live models")
            from PIL import Image, ImageOps
            try:
                encoded = data.get("photo", "")
                if not isinstance(encoded, str) or len(encoded) > 14_000_000:
                    raise ValueError("Choose an image up to 10 MB")
                raw = base64.b64decode(encoded, validate=True)
                if not raw or len(raw) > 10 * 1024 * 1024:
                    raise ValueError("Choose an image up to 10 MB")
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as image:
                        if image.format not in ("JPEG", "PNG", "WEBP"):
                            raise ValueError("Choose a JPEG, PNG, or WebP image")
                        image = ImageOps.exif_transpose(image).convert("RGB")
                        image.thumbnail((2048, 2048))
                        output = io.BytesIO()
                        image.save(output, format="PNG")
                        photo = output.getvalue()
            except (ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ValueError("Choose a valid JPEG, PNG, or WebP image up to 10 MB") from exc
            prompt = ""
        elif not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise ValueError("Enter a prompt of 1–4000 characters")
        settings = settings_from(data)
        run_mode = data.get("mode")
        if run_mode not in (None, "live-demo", "live-testing"):
            raise ValueError("Choose Live demo or Continuous testing")
        if run_mode and (self.demo or self.recorded):
            raise ValueError("Live modes require the real-model server")
        if run_mode == "live-demo":
            settings["limit"] = settings["limit"] or 18
        elif run_mode == "live-testing":
            settings["limit"] = 0
        if self.demo and type(self.adapter) is DemoModels:
            prompt = self.adapter.sequence["prompt"]
            settings["limit"] = min(settings["limit"] or 18, 18)
        if self.recorded:
            self.adapter.index = 0
            prompt = self.adapter.manifest["original_prompt"]
            settings["limit"] = min(settings["limit"] or len(self.adapter.frames), len(self.adapter.frames))
            settings["seed"] = self.adapter.frames[0]["seed"]
        with self.lock:
            if self.active():
                raise ValueError("A run is already active; stop it first")
            self.stop_event.clear()
            self.playback = False
            run_id = uuid.uuid4().hex
            folder = self.root / run_id
            folder.mkdir()
            if photo is not None:
                (folder / "initial.png").write_bytes(photo)
            self.current = {"input_type": input_type, "initial_image": "initial.png" if photo is not None else None, "id": run_id, "created": now(), "original_prompt": prompt.strip(),
                            "settings": settings, "mode": run_mode, "demo": self.demo, "status": "running",
                            "python": platform.python_version(), "platform": platform.platform(),
                            "vision_instruction": VISION_INSTRUCTION,
                            "recorded": self.recorded, "source_run": self.adapter.manifest["id"] if self.recorded else None,
                            "provenance": "Recorded real-model outputs; replay, no new inference" if self.recorded else "Simulated artwork and scripted interpretations; no model inference" if self.demo else "Local model inference"}
            save_json(folder / "manifest.json", self.current)
            (folder / "prompts.txt").write_text(
                f"AI Telephone — run {run_id}\n{self.current['provenance']}\n" +
                (f"Original photo: initial.png\nLoop: photo → interpretation → image → …\n\n" if photo is not None else f"Original prompt:\n{prompt.strip()}\n\n") +
                "Each completed image is listed below with its exact generation prompt "
                "and vision interpretation.\n\n", encoding="utf-8")
            (folder / "prompts.jsonl").touch()
            self.error = None
            self.iteration = 0
            self.completed = 0
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
                if not self.playback:
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
            if not self.demo and not self.recorded:
                from prepare import environment, ensure_vision_model
                self.set_phase("checking models")
                run["environment"] = environment()
                available = {model["name"] for model in run["environment"]["models"]}
                if settings["vision_model"] not in available:
                    self.set_phase("downloading vision model")
                    ensure_vision_model(settings["vision_model"])
                    run["environment"] = environment()
                save_json(folder / "manifest.json", run)
            while not self.stop_event.is_set():
                count += 1
                with self.lock:
                    self.iteration = count
                seed = (settings["seed"] + count - 1) % (2**31)
                started = time.monotonic()
                temp_image = folder / "pending.png"
                uploaded = count == 1 and run.get("input_type") == "photo"
                if uploaded:
                    temp_image.write_bytes((folder / "initial.png").read_bytes())
                else:
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
                          "input": prompt, "source": "upload" if uploaded else "generated", "caption": caption, "image": filename,
                          "demo": self.demo, "recorded": self.recorded, "provenance": run["provenance"],
                          "source_iteration": self.adapter.frames[count-1] if self.recorded else None,
                          "sha256": hashlib.sha256((folder / filename).read_bytes()).hexdigest(),
                          "seconds": round(time.monotonic() - started, 3)}
                # An iteration is committed by its JSON file. Incomplete PNGs are ignored.
                save_json(folder / f"{count:06d}.json", record)
                # Incremental exports retain completed work on Stop or later model errors.
                # Exact prompts remain host-only; these files are never public routes.
                with (folder / "prompts.jsonl").open("a", encoding="utf-8") as export:
                    export.write(json.dumps(record, ensure_ascii=False) + "\n")
                with (folder / "prompts.txt").open("a", encoding="utf-8") as export:
                    export.write(f"Iteration {count:06d} — {filename}\nSeed: {seed}\n"
                                 f"Image input:\n{'Uploaded photo (initial.png)' if uploaded else prompt}\n\n"
                                 f"Image interpretation / next prompt:\n{caption}\n\n"
                                 "----------------------------------------\n\n")
                with self.lock:
                    self.presentation_prompt = run["original_prompt"]
                    self.completed = count
                    self.published = {"run": run["id"], "iteration": count,
                                      "demo": self.demo, "recorded": self.recorded, "caption": caption, "image": f"/images/{run['id']}/{filename}"}
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

    def reset(self):
        with self.lock:
            if self.active():
                raise ValueError("Stop the run before resetting the displays")
            self.event("displays_reset")
            self.published = None
            self.presentation_prompt = None
            self.current = None
            self.playback = False
            self.playback_total = 0
            self.error = None
            self.iteration = 0
            self.completed = 0
            self.phase = "idle"

    def public_state(self, include_prompt=False):
        with self.lock:
            # Explicit allowlist: prompts, history, logs and raw errors stay private.
            state = {"phase": self.phase, "demo": self.demo, "recorded": self.recorded,
                    "frame": copy.deepcopy(self.published), "active": self.active(), "playback": self.playback,
                    "progress": {"iteration": self.iteration, "completed": self.completed,
                                 "limit": self.playback_total if self.playback else self.current["settings"]["limit"] if self.current else 0}}
            if include_prompt:
                state["original_prompt"] = self.current["original_prompt"] if self.active() and self.current and not self.playback else self.presentation_prompt
            return state

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
                # macOS File Provider can evict cloud files. Avoid blocking the controller
                # while OneDrive hydrates old archives; they reappear when available.
                if getattr(path.stat(), "st_flags", 0) & 0x40000000:
                    continue
                run = json.loads(path.read_text(encoding="utf-8"))
                if run["status"] == "running" and (not self.current or run["id"] != self.current["id"]):
                    run["status"] = "interrupted"
                result.append(run)
            except (ValueError, OSError, KeyError):
                continue
        return sorted(result, key=lambda r: r["created"], reverse=True)

    def replay_run(self, run_id, interval=None, repeat=False):
        if interval is not None and (isinstance(interval, bool) or not isinstance(interval, (int, float)) or not 0.5 <= interval <= 3600):
            raise ValueError("Playback hold must be 0.5–3600 seconds")
        if not isinstance(repeat, bool):
            raise ValueError("Loop playback must be true or false")
        with self.lock:
            if self.active():
                raise ValueError("Stop the current run before playback")
            folder = self.run_folder(run_id)
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            frames = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(folder.glob("[0-9]" * 6 + ".json"))]
            if not frames:
                raise ValueError("This run has no completed iterations")
            for frame in frames:
                if not re.fullmatch(r"[0-9]{6}\.png", frame["image"]):
                    raise ValueError("Invalid recorded image filename")
                if hashlib.sha256((folder / frame["image"]).read_bytes()).hexdigest() != frame["sha256"]:
                    raise ValueError("Saved image checksum mismatch")
            self.stop_event.clear()
            # Playback never writes into the original inference records or manifest.
            self.current = None
            self.playback = True
            self.presentation_prompt = manifest["original_prompt"]
            self.playback_total = len(frames)
            self.completed = 0
            self.iteration = 0
            self.error = None
            self.phase = "playing saved run"
            self.thread = threading.Thread(target=self.playback_loop,
                args=(run_id, frames, manifest, interval, repeat), daemon=True)
            self.thread.start()

    def playback_loop(self, run_id, frames, manifest, interval, repeat):
        try:
            while not self.stop_event.is_set():
                for index, frame in enumerate(frames):
                    if self.stop_event.is_set():
                        break
                    with self.lock:
                        self.iteration = frame["iteration"]
                        self.completed = index + 1
                        self.phase = "playing saved run"
                        self.published = {"run": run_id, "iteration": frame["iteration"],
                            "demo": manifest.get("demo", False), "recorded": True,
                            "caption": frame["caption"], "image": f"/images/{run_id}/{frame['image']}"}
                    hold = interval
                    if hold is None:
                        hold = max(12, len(frame["caption"].split()) / 2.5 + 3)
                        if index == 0:
                            hold += len(manifest["original_prompt"].split()) / 2.5
                    self.stop_event.wait(hold)
                if not repeat:
                    break
            with self.lock:
                self.phase = "stopped" if self.stop_event.is_set() else "playback completed"
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.phase = "error"

    def replay(self, run_id, iteration):
        with self.lock:
            if self.active():
                raise ValueError("Stop the loop before replaying history")
            folder = self.run_folder(run_id)
            if not isinstance(iteration, int) or not 1 <= iteration <= 999999:
                raise ValueError("Invalid iteration")
            record = json.loads((folder / f"{iteration:06d}.json").read_text(encoding="utf-8"))
            self.presentation_prompt = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["original_prompt"]
            self.published = {"run": run_id, "iteration": iteration,
                              "demo": json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["demo"],
                              "recorded": json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("recorded", False), "caption": record["caption"],
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
                if path == "/api/combined-state":
                    return self.send(200, installation.public_state(include_prompt=True))
                if path == "/api/state":
                    return self.send(200, installation.public_state())
                if path == "/api/admin":
                    if not self.admin(): return
                    runs = installation.runs()
                    with installation.lock:
                        return self.send(200, {**installation.public_state(), "active": installation.active(),
                                               "error": installation.error, "events": installation.events[-30:],
                                               "runs": runs, "default_mode": installation.default_mode,
                                               "default_vision_model": DEFAULTS["vision_model"],
                                               "recorded_prompt": installation.adapter.manifest["original_prompt"] if installation.recorded else None})
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
                if not 0 < length <= (14_100_000 if urlparse(self.path).path == "/api/start" else 16384):
                    raise ValueError("Request too large or empty")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict): raise ValueError("Expected a JSON object")
                path = urlparse(self.path).path
                if path == "/api/start":
                    return self.send(200, {"run": installation.start(data)})
                if path == "/api/reset":
                    installation.reset()
                    return self.send(200, {"ok": True})
                if path == "/api/stop":
                    installation.stop()
                    return self.send(200, {"ok": True})
                if path == "/api/replay-run":
                    installation.replay_run(data.get("run", ""), data.get("interval"), data.get("repeat", False))
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--demo", action="store_true", help="Live real-model demo with your own prompt")
    modes.add_argument("--testing", action="store_true", help="Continuous real-model testing until Stop")
    modes.add_argument("--simulated-demo", action="store_true", help="Explicit simulated wiring test; no inference")
    parser.add_argument("--recorded-demo", type=Path, help="Replay an original real-model run folder")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runs", type=Path, default=BASE / "runs")
    parser.add_argument("--open-browser", action="store_true", help="Open authenticated controls automatically")
    args = parser.parse_args()
    if (args.demo or args.testing or args.simulated_demo) and args.recorded_demo:
        parser.error("Choose one live, simulated, or recorded mode")
    installation = Installation(args.runs, args.simulated_demo, RecordedModels(args.recorded_demo) if args.recorded_demo else None, default_mode="live-testing" if args.testing else "live-demo")
    server = ThreadingHTTPServer((args.bind, args.port), handler_for(installation))
    print(f"Controls: http://127.0.0.1:{server.server_port}/#token={installation.token}", flush=True)
    print(f"Displays: http://<host-LAN-IP>:{server.server_port}/image and /text", flush=True)
    print(f"One laptop: http://127.0.0.1:{server.server_port}/combined", flush=True)
    print("SIMULATED TEST — no AI models" if args.simulated_demo else "LOCAL MODE — SD-Turbo + Ollama", flush=True)
    if args.open_browser:
        threading.Timer(0.5, webbrowser.open,
                        args=(f"http://127.0.0.1:{server.server_port}/#token={installation.token}",)).start()
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
