"""Setup regression tests; no package installation or model downloads."""
import io
import importlib.metadata
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch, Mock

import launch
import prepare


class LauncherTests(unittest.TestCase):
    def test_rejects_environment_copied_from_other_machine(self):
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / 'env' / 'bin' / 'python'
            with patch('launch.subprocess.run', return_value=Mock(returncode=0, stdout='/old/computer/env\n')):
                self.assertFalse(launch.usable_python(python))
            with patch('launch.subprocess.run', return_value=Mock(returncode=0, stdout=str(python.parent.parent) + '\n')):
                self.assertTrue(launch.usable_python(python))

    def test_check_does_not_create_environment(self):
        with tempfile.TemporaryDirectory() as folder, patch('launch.BASE', Path(folder)), patch('launch.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'No usable Python'):
                launch.choose_environment(check=True)
            run.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_nvidia_wheel_selection(self):
        with patch('launch.shutil.which', return_value='nvidia-smi'):
            for capability, expected in [('8.6\n', 'cu126'), ('12.0\n', 'cu128')]:
                with patch('launch.subprocess.run', return_value=Mock(stdout=capability)):
                    self.assertEqual(launch.nvidia_backend(), expected)
        with patch('launch.shutil.which', return_value=None):
            self.assertEqual(launch.nvidia_backend(), 'cpu')

    def test_dependencies_match_requested_workflow(self):
        self.assertNotIn('reportlab', launch.required_packages('live'))
        self.assertIn('imageio-ffmpeg', launch.required_packages('capture'))
        self.assertIn('reportlab', launch.required_packages('promo'))
        with patch('importlib.metadata.version', side_effect=importlib.metadata.PackageNotFoundError), patch('launch.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Dependencies need setup'):
                launch.ensure_packages(check=True)
            run.assert_not_called()

    def test_existing_environment_reused_without_modification(self):
        with tempfile.TemporaryDirectory() as folder, patch('launch.BASE', Path(folder)):
            runtime = Path(folder) / '.runtime' / (launch.platform.system().lower() + '-' + launch.platform.machine().lower())
            python = launch.environment_python(runtime)
            python.parent.mkdir(parents=True)
            python.touch()
            with patch('launch.usable_python', return_value=True), patch('launch.run') as run:
                self.assertEqual(launch.choose_environment(), python)
                run.assert_not_called()


    def test_simulated_launcher_serves_controls_and_completes_a_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.Popen([sys.executable, str(launch.BASE / 'launch.py'),
                '--mode', 'simulated', '--no-browser', '--bind', '127.0.0.1',
                '--port', '0', '--runs', folder], cwd=launch.BASE,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', env={**os.environ, 'PYTHONUTF8': '1'})
            lines = queue.Queue()
            def read_output():
                for line in process.stdout:
                    lines.put(line)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            try:
                deadline = time.monotonic() + 15
                url = None
                output = ''
                while time.monotonic() < deadline and not url:
                    try:
                        line = lines.get(timeout=0.5)
                    except queue.Empty:
                        if process.poll() is not None:
                            break
                        continue
                    output += line
                    match = re.search(r'Controls: (http\S+)', line)
                    if match:
                        url = match[1]
                self.assertIsNotNone(url, output)
                base, token = url.split('/#token=')
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                request = urllib.request.Request(base + '/api/start',
                    json.dumps({'prompt': 'wiring test', 'limit': 2, 'interval': 0}).encode(),
                    {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                with opener.open(request, timeout=5) as response:
                    run_id = json.load(response)['run']
                while time.monotonic() < deadline:
                    with opener.open(base + '/api/state', timeout=5) as response:
                        state = json.load(response)
                    if not state['active']:
                        break
                    time.sleep(0.05)
                self.assertEqual(state['phase'], 'completed')
                self.assertEqual(state['frame']['iteration'], 2)
                self.assertEqual(len(list((Path(folder) / run_id).glob('[0-9]' * 6 + '.json'))), 2)
            finally:
                process.terminate()
                process.wait(timeout=10)
                reader.join(timeout=2)
                process.stdout.close()


class ModelSetupTests(unittest.TestCase):
    def test_complete_cache_skips_download(self):
        with patch('prepare.image_cache_complete', return_value=True), patch('huggingface_hub.snapshot_download') as download:
            prepare.ensure_image_model()
            download.assert_not_called()

    def test_partial_snapshot_is_not_treated_as_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / 'config.json'
            existing.write_text('{}')
            # Even a directory containing configs must contain every required weight.
            with patch('huggingface_hub.try_to_load_from_cache', side_effect=[str(existing), None]):
                self.assertFalse(prepare.image_cache_complete())
            with patch('huggingface_hub.try_to_load_from_cache', return_value=str(existing)):
                self.assertTrue(prepare.image_cache_complete())
            existing.write_bytes(b'')
            with patch('huggingface_hub.try_to_load_from_cache', return_value=str(existing)):
                self.assertFalse(prepare.image_cache_complete())

    def test_missing_cache_in_offline_mode_has_actionable_error(self):
        with patch('prepare.image_cache_complete', return_value=False), patch.dict('os.environ', {'HF_HUB_OFFLINE': '1'}), patch('huggingface_hub.snapshot_download') as download:
            with self.assertRaisesRegex(RuntimeError, 'HF_HUB_OFFLINE'):
                prepare.ensure_image_model()
            download.assert_not_called()

    def test_missing_weights_are_downloaded_and_rechecked(self):
        with patch('prepare.image_cache_complete', side_effect=[False, True]), patch.dict('os.environ', {'HF_HUB_OFFLINE': '0'}), patch('huggingface_hub.snapshot_download') as download:
            prepare.ensure_image_model(interactive=False)
            self.assertEqual(download.call_args.kwargs['allow_patterns'], prepare.IMAGE_FILES)
            self.assertEqual(download.call_args.kwargs['revision'], prepare.DEFAULTS['revision'])

    def test_download_authentication_uses_users_account(self):
        from huggingface_hub.utils import HfHubHTTPError
        response = Mock(status_code=401, headers={}, text='Access denied')
        error = HfHubHTTPError('Denied', response=response)
        with patch('prepare.image_cache_complete', return_value=False), patch.dict('os.environ', {'HF_HUB_OFFLINE': '0'}), patch('huggingface_hub.snapshot_download', side_effect=error), patch('huggingface_hub.login') as login:
            with self.assertRaisesRegex(RuntimeError, 'own account'):
                prepare.ensure_image_model(interactive=False)
            login.assert_not_called()

    def test_existing_vision_model_never_pulls_updates(self):
        with patch('prepare.local_json', return_value={'models': [{'name': 'qwen2.5vl:3b'}]}), patch('prepare.urllib.request.build_opener') as opener:
            prepare.ensure_vision_model()
            opener.assert_not_called()

    def test_missing_vision_model_streams_download_then_verifies(self):
        tags = [{'models': []}, {'models': [{'name': 'qwen2.5vl:3b'}]}]
        stream = io.BytesIO(b'{"status":"pulling","total":100,"completed":50}\n{"status":"success"}\n')
        opener = Mock()
        opener.open.return_value = stream
        with patch('prepare.local_json', side_effect=tags), patch('prepare.urllib.request.build_opener', return_value=opener):
            prepare.ensure_vision_model()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, prepare.OLLAMA + '/api/pull')
        self.assertEqual(json.loads(request.data)['model'], 'qwen2.5vl:3b')

    def test_check_does_not_download_missing_vision(self):
        with patch('prepare.local_json', return_value={'models': []}), patch('prepare.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(RuntimeError, 'Missing vision model'):
                prepare.ensure_vision_model(check=True)
            opener.assert_not_called()

    def test_running_ollama_does_not_start_another_process(self):
        with patch('prepare.local_json', return_value={'version': 'test'}), patch('prepare.subprocess.Popen') as process:
            prepare.ensure_ollama(interactive=False)
            process.assert_not_called()

    def test_missing_ollama_has_install_instructions(self):
        with patch('prepare.local_json', side_effect=OSError), patch('prepare.ollama_executable', return_value=None), patch('prepare.subprocess.Popen') as process:
            with self.assertRaisesRegex(RuntimeError, 'https://ollama.com/download'):
                prepare.ensure_ollama(interactive=False)
            process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
