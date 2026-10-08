import base64
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import Installation, handler_for, settings_from
from models import DemoModels, VISION_INSTRUCTION, vision_payload


class RecordingModels(DemoModels):
    def __init__(self):
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
        self.assertIn("RGB", model.describe(path.read_bytes(), {}, 1))

    def test_validation(self):
        for config in ({"interval": -1}, {"limit": 1.2}, {"seed": True}, {"steps": 50},
                       {"interval": float("nan")}, {"vision_model": "other"}):
            with self.assertRaises(ValueError): settings_from(config)
        with self.assertRaises(ValueError): self.app.start({"prompt": " "})
        with self.assertRaises(ValueError): self.app.run_folder("../sources")

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
