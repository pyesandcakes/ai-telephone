import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from capture import plate, srt_time


class CaptureTests(unittest.TestCase):
    def test_timestamp_rounding(self):
        self.assertEqual(srt_time(59.9996), "00:01:00,000")

    def test_long_caption_and_mock_label_render(self):
        result = plate(caption="Unusually " * 400, mock=True)
        self.assertEqual(result.size, (1920, 1080))
        self.assertEqual(result.mode, "RGB")

    def test_complete_live_mock_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            res = subprocess.run([sys.executable, "capture.py", "--mock", "--no-browser",
                "--iterations", "3", "--hold", "1", "--port", "0", "--output", temp],
                cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=40)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            session = next(Path(temp).glob("*-capture-*"))
            result = json.loads((session / "result.json").read_text())
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["encoder_exit"], 0)
            self.assertGreater(result["video_seconds"], 5)
            self.assertGreater((session / "live-recording.mp4").stat().st_size, 10000)
            assets = Path(result["assets"])
            self.assertEqual(len(list(assets.glob("pair-*.png"))), 3)
            self.assertTrue((assets / "poster-contact-sheet.png").is_file())
            records = json.loads((assets / "iterations.json").read_text())
            self.assertEqual(len(records), 3)
            self.assertEqual(records[1]["input"], records[0]["caption"])
            timeline = json.loads((session / "timeline.json").read_text())
            self.assertEqual([item["iteration"] for item in timeline], [1, 2, 3])
            import imageio_ffmpeg
            decoded = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i",
                str(session / "live-recording.mp4"), "-f", "null", "-"], capture_output=True, timeout=15)
            self.assertEqual(decoded.returncode, 0, decoded.stderr.decode())


if __name__ == "__main__":
    unittest.main()
