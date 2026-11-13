"""Check local model caches, download missing weights, and record this host."""
import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app import BASE, DEFAULTS
from models import OLLAMA

# Exact files used by the pinned fp16 SD-Turbo pipeline. A snapshot directory
# alone is insufficient: interrupted downloads can leave a partial snapshot.
IMAGE_FILES = [
    "model_index.json", "scheduler/scheduler_config.json",
    "tokenizer/tokenizer_config.json", "tokenizer/special_tokens_map.json",
    "tokenizer/merges.txt", "tokenizer/vocab.json", "text_encoder/config.json",
    "text_encoder/model.fp16.safetensors", "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors", "vae/config.json",
    "vae/diffusion_pytorch_model.fp16.safetensors",
]


def local_json(route, timeout=5):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(OLLAMA + route, timeout=timeout) as response:
        return json.load(response)


def ollama_executable():
    candidates = [shutil.which("ollama"), "/opt/homebrew/bin/ollama",
                  "/usr/local/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama"]
    if os.name == "nt":
        candidates.append(str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"))
    return next((str(p) for p in candidates if p and Path(p).is_file()), None)


def ensure_ollama(interactive=True):
    try:
        local_json("/api/version")
        return
    except (OSError, ValueError):
        pass
    executable = ollama_executable()
    if not executable and interactive and sys.stdin.isatty():
        import webbrowser
        print("Install Ollama from the page opening in your browser. No account is needed for local models.", flush=True)
        webbrowser.open("https://ollama.com/download")
        input("After installing and opening Ollama, press Enter here to continue (Ctrl+C to stop): ")
        try:
            local_json("/api/version")
            return
        except (OSError, ValueError):
            executable = ollama_executable()
    if not executable:
        raise RuntimeError("Ollama is not installed. Install it from https://ollama.com/download, "
                           "then run Start-AI-Telephone again. No Ollama account is needed for these local models.")
    logs = BASE / "tmp"
    logs.mkdir(exist_ok=True)
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
    print("Starting local Ollama...", flush=True)
    with (logs / "ollama-launch.log").open("ab") as log:
        subprocess.Popen([executable, "serve"], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log,
                         env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}, **options)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            local_json("/api/version", timeout=1)
            return
        except (OSError, ValueError):
            time.sleep(0.5)
    raise RuntimeError("Ollama did not start. Open the Ollama app and retry. See tmp/ollama-launch.log.")


def ensure_vision_model(model=DEFAULTS["vision_model"], check=False):
    names = {item["name"] for item in local_json("/api/tags")["models"]}
    if model in names:
        print("Vision model already downloaded: " + model, flush=True)
        return
    if check:
        raise RuntimeError("Missing vision model: " + model + ". Run the launcher to download it.")
    print("Downloading " + model + " through local Ollama (several GB; resumable)...", flush=True)
    request = urllib.request.Request(OLLAMA + "/api/pull",
        json.dumps({"model": model, "stream": True}).encode(), {"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last = None
    with opener.open(request, timeout=300) as response:
        for line in response:
            item = json.loads(line)
            if item.get("error"):
                raise RuntimeError("Ollama download failed: " + item["error"])
            total = item.get("total", 0)
            progress = f" {100 * item.get('completed', 0) // total}%" if total else ""
            status = item.get("status", "Downloading") + progress
            if status != last:
                print(status, flush=True)
                last = status
    if model not in {item["name"] for item in local_json("/api/tags")["models"]}:
        raise RuntimeError("Vision download incomplete. Run the launcher again to resume.")


def image_cache_complete():
    from huggingface_hub import try_to_load_from_cache
    for name in IMAGE_FILES:
        cached = try_to_load_from_cache(DEFAULTS["image_model"], name, revision=DEFAULTS["revision"])
        if not isinstance(cached, str) or not Path(cached).is_file() or Path(cached).stat().st_size == 0:
            return False
    return True


def ensure_image_model(check=False, interactive=True):
    if image_cache_complete():
        print("Image model already downloaded: SD-Turbo (pinned revision)", flush=True)
        return
    if check:
        raise RuntimeError("SD-Turbo cache is missing or incomplete. Run the launcher to download it.")
    if os.environ.get("HF_HUB_OFFLINE", "").upper() in ("1", "TRUE", "YES", "ON"):
        raise RuntimeError("Image weights are missing but HF_HUB_OFFLINE is enabled. Unset it and rerun setup.")
    from huggingface_hub import snapshot_download, login
    from huggingface_hub.utils import HfHubHTTPError
    print("Downloading missing SD-Turbo files (about 2.6 GB total; resumable).", flush=True)
    print("Default models need no paid API key. Any Hugging Face authentication uses your own account.", flush=True)
    options = dict(repo_id=DEFAULTS["image_model"], revision=DEFAULTS["revision"], allow_patterns=IMAGE_FILES)
    try:
        snapshot_download(**options)
    except HfHubHTTPError as exc:
        if exc.response is None or exc.response.status_code not in (401, 403):
            raise
        if not interactive or not sys.stdin.isatty():
            raise RuntimeError("Hugging Face denied access. Accept the model terms using your own account at "
                               "https://huggingface.co/stabilityai/sd-turbo, then run `hf auth login` "
                               "in this environment or set HF_TOKEN privately and retry.") from None
        import getpass
        print("Accept any model terms at https://huggingface.co/stabilityai/sd-turbo in your own account.")
        token = getpass.getpass("Your Hugging Face read token (hidden; stored in your user HF cache): ")
        if not token.strip():
            raise RuntimeError("No token entered. Setup can be resumed by running the launcher again.")
        login(token=token.strip(), add_to_git_credential=False)
        del token
        snapshot_download(**options)
    if not image_cache_complete():
        raise RuntimeError("Image download is incomplete. Run the launcher again to resume.")


def environment():
    packages = {}
    for name in ("torch", "diffusers", "transformers", "accelerate", "safetensors", "huggingface-hub", "Pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": packages, "ollama": local_json("/api/version"),
            "models": local_json("/api/tags")["models"]}


def device_info():
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    info = {"device": device, "torch": torch.__version__}
    if device == "cuda":
        # Exercise a kernel, rather than only trusting driver detection.
        (torch.ones(1, device="cuda") + 1).cpu()
        info["gpu"] = torch.cuda.get_device_name(0)
        info["cuda"] = torch.version.cuda
    elif device == "mps":
        (torch.ones(1, device="mps") + 1).cpu()
    return info


def prepare(vision_model=DEFAULTS["vision_model"], check=False, interactive=True):
    if check:
        try:
            local_json("/api/version")
        except (OSError, ValueError):
            raise RuntimeError("Ollama is not running. Run the launcher without --check to start it automatically.") from None
    else:
        ensure_ollama(interactive=interactive)
    ensure_vision_model(vision_model, check=check)
    ensure_image_model(check=check, interactive=interactive)
    info = {**environment(), **device_info()}
    print("Image inference device: " + info["device"] + (" / " + info["gpu"] if "gpu" in info else ""), flush=True)
    if info["device"] == "cpu":
        print("CPU mode: usable, but model inference may take several minutes per image.", flush=True)
    if not check:
        (BASE / "environment.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        lock = subprocess.check_output([sys.executable, "-m", "pip", "freeze"])
        (BASE / "environment-lock.txt").write_bytes(lock)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Inspect only; do not download or start services")
    parser.add_argument("--vision-model", choices=["qwen2.5vl:3b", "qwen2.5vl:7b"], default=DEFAULTS["vision_model"])
    args = parser.parse_args()
    try:
        prepare(args.vision_model, check=args.check)
    except (OSError, RuntimeError) as exc:
        raise SystemExit("Setup: " + str(exc)) from None


if __name__ == "__main__":
    main()
