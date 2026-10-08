"""Download pinned image weights and verify the local vision model before opening."""
import importlib.metadata
import json
import platform
import subprocess
import urllib.request
from pathlib import Path

from app import DEFAULTS
from models import OLLAMA


def environment():
    packages = {}
    for name in ("torch", "diffusers", "transformers", "accelerate", "safetensors", "huggingface-hub", "Pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(OLLAMA + "/api/tags", timeout=5) as response:
        models = json.load(response)["models"]
    with opener.open(OLLAMA + "/api/version", timeout=5) as response:
        version = json.load(response)
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": packages, "ollama": version, "models": models}


def main():
    import torch
    from huggingface_hub import snapshot_download
    print("Downloading pinned SD-Turbo weights (first setup requires internet)...")
    snapshot_download(DEFAULTS["image_model"], revision=DEFAULTS["revision"],
                      allow_patterns=["*.json", "*.txt", "*.safetensors", "*.model"],
                      ignore_patterns=["*.fp16.*", "*.onnx", "*.msgpack", "sd_turbo.safetensors"])
    info = environment()
    names = [m["name"] for m in info["models"]]
    if DEFAULTS["vision_model"] not in names:
        raise SystemExit("Run: ollama pull " + DEFAULTS["vision_model"])
    info["device"] = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    Path("environment.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    lock = subprocess.check_output([__import__("sys").executable, "-m", "pip", "freeze"])
    Path("environment-lock.txt").write_bytes(lock)
    print("Ready. Device:", info["device"])
    print("Saved package versions and Ollama model digests in environment.json.")


if __name__ == "__main__":
    main()
