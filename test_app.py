import base64
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import Installation, handler_for, settings_from
from models import DemoModels, RecordedModels, VISION_INSTRUCTION, vision_payload


class RecordingModels(DemoModels):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.pixels = []

    def generate(self, prompt, destination, settings, seed, log_path):
        self.inputs.append(prompt)
        super().generate(prompt, destination, settings, seed, log_path)

    def describe(self, png_bytes, settings, seed):
        self.pixels.append(png_bytes)
        return f"Description {len(self.pixels)}"


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.adapter = RecordingModels()
        self.app = Installation(self.tmp.name, demo=True, adapter=self.adapter)

    def tearDown(self):
        self.app.stop()
        if self.app.thread: self.app.thread.join(3)
        self.tmp.cleanup()

    def run_chain(self, **settings):
        run = self.app.start({"prompt": "SECRET_ORIGINAL_PROMPT", "interval": 0, "limit": 3, **settings})
        self.app.thread.join(3)
        self.assertFalse(self.app.active())
        return run

    def test_photo_starts_with_vision_then_feeds_generation_and_replays(self):
        photo = (self.adapter.folder / self.adapter.sequence["frames"][0]["image"]).read_bytes()
        run = self.app.start({"input_type": "photo", "photo": base64.b64encode(photo).decode(),
                              "prompt": "Must not reach either model", "limit": 3, "interval": 0})
        self.app.thread.join(3)
        self.assertEqual(self.app.phase, "completed", self.app.error)
        self.assertEqual(self.adapter.inputs, ["Description 1", "Description 2"])
        folder = Path(self.tmp.name) / run
        self.assertEqual(self.adapter.pixels[0], (folder / "initial.png").read_bytes())
        self.assertEqual(self.adapter.pixels[0], (folder / "000001.png").read_bytes())
        first = json.loads((folder / "000001.json").read_text())
        self.assertEqual(first["source"], "upload")
        self.assertEqual(first["input"], "")
        self.assertEqual(self.app.current["original_prompt"], "")
        self.app.replay(run, 1)
        self.assertEqual(self.app.published["caption"], "Description 1")

    def test_invalid_photo_does_not_create_run(self):
        for value in ("", "invalid!", base64.b64encode(b"not an image").decode()):
            with self.assertRaises(ValueError):
                self.app.start({"input_type": "photo", "photo": value})
        self.assertEqual(self.app.runs(), [])
        with self.assertRaises(ValueError):
            self.app.start({"input_type": "unknown", "prompt": "hello"})
        simulated = Installation(self.tmp.name, demo=True)
        with self.assertRaises(ValueError):
            simulated.start({"input_type": "photo", "photo": ""})

    def test_feedback_and_seed_sequence(self):
        run = self.run_chain()
        self.assertEqual(self.adapter.inputs, ["SECRET_ORIGINAL_PROMPT", "Description 1", "Description 2"])
        history = self.app.history(run)
        self.assertEqual([r["seed"] for r in history["items"]], [44, 43, 42])
        self.assertEqual(self.app.phase, "completed")
        self.assertNotIn("SECRET_ORIGINAL_PROMPT", json.dumps(self.app.public_state()))

    def test_vision_boundary(self):
        self.run_chain(limit=1)
        payload = vision_payload(self.adapter.pixels[0], "qwen2.5vl:3b", 42)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["content"], VISION_INSTRUCTION)
        self.assertNotIn("SECRET_ORIGINAL_PROMPT", json.dumps(payload))
        decoded = base64.b64decode(payload["messages"][0]["images"][0])
        self.assertEqual(decoded, self.adapter.pixels[0])
        self.assertNotIn(b"SECRET_ORIGINAL_PROMPT", decoded)
        self.assertEqual(payload["keep_alive"], 0)

    def test_persistence_and_replay(self):
        run = self.run_chain()
        reopened = Installation(self.tmp.name, demo=True)
        self.assertEqual(reopened.runs()[0]["id"], run)
        reopened.replay(run, 1)
        self.assertEqual(reopened.public_state()["frame"]["caption"], "Description 1")

    def test_stop_discards_unfinished_pair_and_prevents_overlap(self):
        entered, release = threading.Event(), threading.Event()
        original = self.adapter.generate
        def blocked(*args):
            entered.set()
            release.wait(2)
            original(*args)
        self.adapter.generate = blocked
        run = self.app.start({"prompt": "secret", "limit": 0, "interval": 0})
        self.assertTrue(entered.wait(1))
        try:
            with self.assertRaises(ValueError): self.app.start({"prompt": "second"})
            self.app.stop()
            self.assertEqual(self.app.phase, "stopping")
        finally:
            release.set()
        self.app.thread.join(3)
        self.assertEqual(self.app.history(run)["total"], 0)
        self.assertEqual(self.adapter.pixels, [])
        self.assertIsNone(self.app.published)

    def test_failure_preserves_previous_pair(self):
        self.run_chain(limit=1)
        old = self.app.public_state()["frame"]
        def failure(*args): raise RuntimeError("test model failure")
        self.adapter.describe = failure
        self.run_chain(limit=1)
        self.assertEqual(self.app.phase, "error")
        self.assertEqual(old, self.app.public_state()["frame"])
        self.assertNotIn("test model failure", json.dumps(self.app.public_state()))

    def test_demo_decodes_pixels(self):
        model = DemoModels()
        path = Path(self.tmp.name) / "demo.png"
        model.generate("hello", path, {}, 1, None)
        self.assertIn("luminous red ring", model.describe(path.read_bytes(), {}, 1))

    def test_full_demo_sequence(self):
        app = Installation(self.tmp.name, demo=True)
        run = app.start({"prompt": "ignored demo input", "interval": 0})
        app.thread.join(10)
        self.assertEqual(app.phase, "completed", app.error)
        items = list(reversed(app.history(run)["items"]))
        self.assertEqual(len(items), 18)
        self.assertEqual(len({i["sha256"] for i in items}), 18)
        for previous, current in zip(items, items[1:]):
            self.assertEqual(current["input"], previous["caption"])
        self.assertTrue(all(i["demo"] for i in items))
        app.replay(run, 1)
        self.assertTrue(app.public_state()["frame"]["demo"])

    def test_recorded_playback_integrity(self):
        run = self.run_chain()
        folder = Path(self.tmp.name) / run
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        with self.assertRaises(ValueError): RecordedModels(folder)
        # Fixture only: exercise validation without claiming these pixels are real inference.
        manifest["demo"] = False
        manifest_path.write_text(json.dumps(manifest))
        adapter = RecordedModels(folder)
        replay = Installation(self.tmp.name, adapter=adapter)
        played = replay.start({"prompt": "ignored", "interval": 0})
        replay.thread.join(3)
        self.assertEqual(replay.phase, "completed", replay.error)
        self.assertEqual(replay.history(played)["total"], 3)
        self.assertTrue(replay.public_state()["frame"]["recorded"])
        self.assertFalse(replay.public_state()["frame"]["demo"])
        replay.replay(played, 1)
        self.assertTrue(replay.public_state()["frame"]["recorded"])
        (folder / "000001.png").write_bytes(b"corrupted")
        with self.assertRaises(ValueError): RecordedModels(folder)

    def test_live_modes_preserve_custom_prompts_and_stop(self):
        for mode, supplied_limit, expected_limit in (("live-demo", 2, 2), ("live-testing", 1, 0)):
            adapter = RecordingModels()
            app = Installation(self.tmp.name, adapter=adapter)
            # Test double only; real inference is validated separately.
            with patch("prepare.environment", return_value={"models": [{"name": "qwen2.5vl:3b"}]}):
                run = app.start({"prompt": "My own starting prompt", "mode": mode,
                                 "limit": supplied_limit, "interval": 0.02})
                deadline = time.monotonic() + 3
                while app.history(run)["total"] < (2 if mode == "live-demo" else 3) and time.monotonic() < deadline:
                    time.sleep(0.01)
                if mode == "live-testing":
                    self.assertTrue(app.active())
                    app.stop()
                app.thread.join(3)
            self.assertEqual(app.current["original_prompt"], "My own starting prompt")
            self.assertEqual(app.current["settings"]["limit"], expected_limit)
            self.assertEqual(adapter.inputs[0], "My own starting prompt")
            self.assertEqual(app.phase, "completed" if mode == "live-demo" else "stopped")
            self.assertFalse(app.current["demo"])
            self.assertFalse(app.current["recorded"])
            exported = [json.loads(line) for line in (Path(self.tmp.name) / run / "prompts.jsonl").read_text().splitlines()]
            self.assertEqual(len(exported), app.history(run)["total"])
            self.assertEqual(exported[0]["input"], "My own starting prompt")

    def test_images_and_prompt_exports_persist_on_stop_and_error(self):
        custom = 'An orange boat, a "blue" moon, and café lights.\nSecond line.'
        run = self.app.start({
            "prompt": custom, "limit": 3, "interval": 0})
        self.app.thread.join(3)
        folder = Path(self.tmp.name) / run
        records = [json.loads(line) for line in (folder / "prompts.jsonl").read_text().splitlines()]
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["input"], custom)
        self.assertEqual(records[1]["input"], records[0]["caption"])
        text = (folder / "prompts.txt").read_text()
        self.assertIn(custom, text)
        for item in records:
            self.assertIn(item["image"], text)
            self.assertIn(item["caption"], text)
            self.assertTrue((folder / item["image"]).is_file())
        original = self.adapter.describe
        def fail_second(*args):
            if len(self.adapter.pixels) > 3:
                raise RuntimeError("later inference failed")
            return original(*args)
        self.adapter.describe = fail_second
        failed = self.app.start({"prompt": custom, "limit": 3, "interval": 0})
        self.app.thread.join(3)
        self.assertEqual(self.app.phase, "error")
        saved = Path(self.tmp.name) / failed
        self.assertEqual(len((saved / "prompts.jsonl").read_text().splitlines()), 1)
        self.assertTrue((saved / "000001.png").exists())
        self.assertFalse((saved / "pending.png").exists())

    def test_reset_preserves_archive_and_progress(self):
        run = self.run_chain(limit=2)
        state = self.app.public_state()
        self.assertEqual(state["progress"], {"iteration": 2, "completed": 2, "limit": 2})
        self.assertFalse(state["active"])
        self.app.reset()
        self.assertIsNone(self.app.public_state()["frame"])
        self.assertEqual(self.app.phase, "idle")
        self.assertEqual(self.app.history(run)["total"], 2)
        self.assertTrue((Path(self.tmp.name) / run / "prompts.txt").exists())
        self.app.replay(run, 1)
        self.assertIsNotNone(self.app.public_state()["frame"])

    def test_reset_rejected_during_generation(self):
        entered, release = threading.Event(), threading.Event()
        original = self.adapter.generate
        def blocked(*args):
            entered.set(); release.wait(3); original(*args)
        self.adapter.generate = blocked
        self.app.start({"prompt": "private prompt", "limit": 1, "interval": 0})
        self.assertTrue(entered.wait(1))
        try:
            self.assertTrue(self.app.public_state()["active"])
            self.assertEqual(self.app.public_state()["progress"]["iteration"], 1)
            with self.assertRaises(ValueError): self.app.reset()
        finally:
            self.app.stop(); release.set(); self.app.thread.join(3)

    def test_whole_run_playback_never_calls_models_or_changes_archive(self):
        run = self.run_chain(limit=2)
        folder = Path(self.tmp.name) / run
        before = {f.name: f.read_bytes() for f in folder.iterdir()}
        def forbidden(*args): raise AssertionError("Playback called a model")
        self.adapter.generate = forbidden
        self.adapter.describe = forbidden
        self.app.replay_run(run, interval=0.5)
        with self.assertRaises(ValueError): self.app.start({"prompt": "overlap"})
        self.app.thread.join(3)
        self.assertEqual(self.app.phase, "playback completed")
        self.assertEqual(self.app.public_state()["frame"]["iteration"], 2)
        self.assertTrue(self.app.public_state()["frame"]["recorded"])
        self.assertEqual(before, {f.name: f.read_bytes() for f in folder.iterdir()})
        self.app.replay_run(run, interval=0.5, repeat=True)
        time.sleep(1.1)
        self.assertTrue(self.app.active())
        self.app.stop(); self.app.thread.join(2)
        self.assertEqual(self.app.phase, "stopped")
        self.assertEqual(before, {f.name: f.read_bytes() for f in folder.iterdir()})

    def test_original_prompt_visible_only_in_combined_state(self):
        run = self.run_chain(limit=1)
        self.assertNotIn("original_prompt", self.app.public_state())
        self.assertEqual(self.app.public_state(include_prompt=True)["original_prompt"], "SECRET_ORIGINAL_PROMPT")
        self.app.reset()
        self.assertIsNone(self.app.public_state(include_prompt=True)["original_prompt"])
        self.app.replay(run, 1)
        self.assertEqual(self.app.public_state(include_prompt=True)["original_prompt"], "SECRET_ORIGINAL_PROMPT")

    def test_reading_pace_accounts_for_caption_and_original(self):
        run = self.run_chain(limit=1)
        with patch.object(self.app.stop_event, "wait", return_value=False) as wait:
            self.app.replay_run(run)
            self.app.thread.join(3)
        self.assertEqual(self.app.phase, "playback completed")
        self.assertGreaterEqual(wait.call_args[0][0], 12)
        self.assertNotIn("original_prompt", self.app.public_state())

    def test_validation(self):
        for config in ({"interval": -1}, {"limit": 1.2}, {"seed": True}, {"steps": 50},
                       {"interval": float("nan")}, {"vision_model": "other"}):
            with self.assertRaises(ValueError): settings_from(config)
        with self.assertRaises(ValueError): self.app.start({"prompt": " "})
        with self.assertRaises(ValueError): self.app.run_folder("../sources")

    def test_missing_selected_vision_model_downloads_before_generation(self):
        app = Installation(self.tmp.name, adapter=RecordingModels())
        with patch("prepare.environment", side_effect=[{"models": []}, {"models": [{"name": "qwen2.5vl:7b"}]}]), patch("prepare.ensure_vision_model") as download:
            app.start({"prompt": "A quiet café by the sea", "limit": 1, "vision_model": "qwen2.5vl:7b"})
            app.thread.join(3)
        download.assert_called_once_with("qwen2.5vl:7b")
        self.assertEqual(app.phase, "completed", app.error)
        self.assertEqual(app.current["environment"]["models"][0]["name"], "qwen2.5vl:7b")

    def test_unicode_prompts_survive_saved_replay(self):
        prompt = "Café — 雨の街 🌙"
        run = self.app.start({"prompt": prompt, "limit": 1})
        self.app.thread.join(3)
        self.app.replay(run, 1)
        self.assertEqual(self.app.public_state(include_prompt=True)["original_prompt"], prompt)
        self.app.replay_run(run, interval=0.5)
        self.app.thread.join(3)
        self.assertEqual(self.app.phase, "playback completed", self.app.error)
        self.assertEqual(self.app.public_state(include_prompt=True)["original_prompt"], prompt)

    def test_http_privacy_and_routes(self):
        run = self.run_chain(limit=1)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{server.server_port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(path, auth=False):
            req = urllib.request.Request(root + path, headers={"Authorization": "Bearer " + self.app.token} if auth else {})
            return opener.open(req, timeout=3)
        try:
            for path in ("/", "/image", "/text", "/combined", "/app.js", "/style.css", "/api/state", self.app.published["image"]):
                with get(path) as response: self.assertEqual(response.status, 200)
            for path in ("/api/admin", f"/api/history?run={run}"):
                with self.assertRaises(urllib.error.HTTPError) as error: get(path)
                self.assertEqual(error.exception.code, 401)
                error.exception.close()
            with get("/api/state") as response: self.assertNotIn(b"SECRET_ORIGINAL_PROMPT", response.read())
            with get(f"/api/history?run={run}", True) as response:
                self.assertIn(b"SECRET_ORIGINAL_PROMPT", response.read())
            for path in ("/runs/" + run + "/manifest.json", "/../app.py", "/sources", "/images/../../app.py"):
                with self.assertRaises(urllib.error.HTTPError) as error: get(path)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(2)


if __name__ == "__main__":
    unittest.main()
