"""Shared Mac/Windows setup and launcher. Uses only the standard library to bootstrap."""
import argparse
import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def run(command, **kwargs):
    subprocess.run([str(part) for part in command], check=True, cwd=BASE, **kwargs)


def environment_python(folder):
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def usable_python(python):
    try:
        result = subprocess.run([str(python), "-c",
            "import sys; assert sys.version_info[:2] in ((3,11),(3,12)); print(sys.prefix)"],
            capture_output=True, text=True, timeout=15)
        # Reject copied/moved environments even if a symlink still runs.
        return result.returncode == 0 and Path(result.stdout.strip()).resolve() == python.parent.parent.resolve()
    except (OSError, subprocess.TimeoutExpired):
        return False


def choose_environment(check=False):
    runtime = BASE / ".runtime" / (platform.system().lower() + "-" + platform.machine().lower())
    legacy = BASE / (".venv" if os.name == "nt" else ".venv-mac")
    for folder in (runtime, legacy):
        python = environment_python(folder)
        if python.is_file() and usable_python(python):
            return python
    if check:
        raise RuntimeError("No usable Python model environment. Run Start-AI-Telephone to create one.")
    if runtime.exists():
        backup = runtime.with_name(runtime.name + "-old-" + str(time.time_ns()))
        runtime.rename(backup)
        print("Preserved an unusable copied environment at " + str(backup))
    print("Creating a model environment for this computer...", flush=True)
    run([sys.executable, "-m", "venv", runtime])
    return environment_python(runtime)


def nvidia_backend():
    """CUDA 12.8 supports newer GPUs; 12.6 also covers older architectures."""
    tool = shutil.which("nvidia-smi")
    if not tool:
        return "cpu"
    try:
        result = subprocess.run([tool, "--query-gpu=compute_cap", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=10, check=True)
        capabilities = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        return "cu128" if capabilities and max(capabilities) >= 10 else "cu126"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "cu126"


def required_packages(mode="live"):
    result = {}
    files = [] if mode == "mock-capture" else ["requirements.txt"]
    if mode in ("capture", "promo", "mock-capture"):
        files.append("requirements-capture.txt")
    if mode == "promo":
        files.append("requirements-promo.txt")
    for name in files:
        for line in (BASE / name).read_text(encoding="utf-8").splitlines():
            if "==" in line and not line.startswith("#"):
                package, version = line.strip().split("==")
                result[package] = version
    return result


def ensure_packages(backend="auto", check=False, mode="live"):
    import importlib.metadata
    missing = []
    for package, version in required_packages(mode).items():
        try:
            installed = importlib.metadata.version(package).split("+")[0]
        except importlib.metadata.PackageNotFoundError:
            installed = None
        if installed != version:
            missing.append(package)
    import_error = None
    if mode != "mock-capture" and "torch" not in missing:
        try:
            # Probe in a child. Importing torch in this process would lock its
            # DLLs on Windows while pip tries to replace an incompatible wheel.
            probe = subprocess.run([sys.executable, "-c",
                "import json, torch; print(json.dumps({'cuda': torch.version.cuda}))"],
                capture_output=True, text=True, check=True, timeout=60)
            cuda = json.loads(probe.stdout)["cuda"]
            if backend.startswith("cu") and cuda != {"cu126": "12.6", "cu128": "12.8"}[backend]:
                missing.append("torch")
            if os.name == "nt" and (backend.startswith("cu") or backend == "auto" and nvidia_backend().startswith("cu")) and not cuda:
                missing.append("torch")
            if backend == "cpu" and cuda:
                missing.append("torch")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            import_error = exc
            missing.append("torch")
    if check and missing:
        raise RuntimeError("Dependencies need setup: " + ", ".join(missing) + ". Run the launcher without --check.")
    if not missing:
        print("Python dependencies ready.", flush=True)
        return
    print("Installing dependencies: " + ", ".join(missing), flush=True)
    if import_error:
        print("Existing PyTorch could not load; reinstalling it.")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    if "torch" in missing:
        selected = backend if backend != "auto" else nvidia_backend() if os.name == "nt" else "native"
        command = [sys.executable, "-m", "pip", "install", "torch==2.8.0"]
        if selected != "native":
            command += ["--index-url", "https://download.pytorch.org/whl/" + selected]
        # Same base version may already be installed with a different wheel type.
        command += ["--force-reinstall"]
        run(command)
    command = [sys.executable, "-m", "pip", "install"]
    if mode != "mock-capture":
        command += ["-r", "requirements.txt"]
    if mode in ("capture", "promo", "mock-capture"):
        command += ["-r", "requirements-capture.txt"]
    if mode == "promo":
        command += ["-r", "requirements-promo.txt"]
    run(command)
    # Start a fresh interpreter after installing libraries to avoid stale imports.
    os.execv(sys.executable, [sys.executable, str(BASE / "launch.py"), *sys.argv[1:]])


def check_port(bind, port):
    if port == 0:
        return
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        try:
            connection.bind((bind, port))
        except OSError:
            raise RuntimeError(f"Port {port} is already in use. If AI Telephone is running, use its "
                               "existing browser tab/control link. Otherwise close that service or use --port 8766.") from None


class KeepAwake:
    def __enter__(self):
        self.process = None
        if sys.platform == "darwin" and shutil.which("caffeinate"):
            self.process = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        elif os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
        return self

    def __exit__(self, *args):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
        elif os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "testing", "simulated", "setup", "capture", "promo", "generate"], default="live")
    parser.add_argument("--check", action="store_true", help="Inspect setup without downloads, installs, or services")
    parser.add_argument("--vision-model", choices=["qwen2.5vl:3b", "qwen2.5vl:7b"], default="qwen2.5vl:3b")
    parser.add_argument("--torch-backend", choices=["auto", "cpu", "cu126", "cu128"], default="auto")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runs", type=Path, default=BASE / "runs", help="Saved live/simulated run folder")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Extra capture/generation arguments after --")
    parser.add_argument("--in-environment", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    extra = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    if extra and args.mode not in ("capture", "promo"):
        parser.error("Extra arguments are supported only for --mode capture or promo")
    if not 0 <= args.port <= 65535:
        parser.error("Port must be 0–65535")
    if args.torch_backend != "auto" and os.name != "nt":
        parser.error("Explicit wheel selection is supported by this launcher on Windows. Use auto on Mac.")
    os.chdir(BASE)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYTHONUTF8"] = "1"
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    mock_capture = args.mode == "capture" and "--mock" in extra
    if args.in_environment or args.mode == "simulated":
        print("AI Telephone / " + platform.system() + " / Python " + platform.python_version(), flush=True)
    if args.mode == "simulated":
        if args.check:
            print("Simulated mode needs only Python and the bundled demo assets.")
            return
    else:
        if sys.version_info[:2] not in ((3, 11), (3, 12)):
            raise RuntimeError("Real models need Python 3.11 or 3.12. Install Python 3.12 from https://www.python.org/downloads/ and rerun the launcher.")
        if not args.in_environment:
            python = choose_environment(check=args.check)
            return subprocess.call([str(python), str(BASE / "launch.py"), "--in-environment", *sys.argv[1:]], cwd=BASE)
        ensure_packages(args.torch_backend, check=args.check, mode="mock-capture" if mock_capture else args.mode)
        if not mock_capture:
            from prepare import prepare
            prepare(args.vision_model, check=args.check)
        if args.check or args.mode == "setup":
            print("Setup is ready. Run Start-AI-Telephone to open the controller.", flush=True)
            return
    if args.mode in ("live", "testing", "simulated", "capture", "promo"):
        check_port(args.bind, args.port)
    # Offline only after every required file has been verified/downloaded.
    os.environ["HF_HUB_OFFLINE"] = "1"
    from app import DEFAULTS
    DEFAULTS["vision_model"] = args.vision_model
    with KeepAwake():
        if args.mode in ("live", "testing", "simulated"):
            from app import main as app_main
            sys.argv = ["app.py", "--bind", args.bind, "--port", str(args.port), "--runs", str(args.runs),
                        {"live": "--demo", "testing": "--testing", "simulated": "--simulated-demo"}[args.mode]]
            if not args.no_browser:
                sys.argv.append("--open-browser")
            app_main()
        elif args.mode in ("capture", "promo"):
            from capture import main as capture_main
            sys.argv = ["capture.py", "--vision-model", args.vision_model, "--bind", args.bind, "--port", str(args.port)]
            if args.no_browser:
                sys.argv.append("--no-browser")
            # Infer this invocation's capture via its result, never directory creation time.
            before = set((BASE / "captures").glob("*-capture-*/result.json"))
            sys.argv += extra
            if args.mode == "promo" and any(part == "--output" or part.startswith("--output=") or part == "--mock" for part in extra):
                raise RuntimeError("Promotional mode requires a real capture in the default captures folder.")
            capture_main()
            if args.mode == "promo":
                created = set((BASE / "captures").glob("*-capture-*/result.json")) - before
                if len(created) != 1:
                    raise RuntimeError("Cannot identify this capture's result; original output is preserved.")
                result = json.loads(created.pop().read_text(encoding="utf-8"))
                from build_promo import main as promo_main
                sys.argv = ["build_promo.py", str(Path(result["assets"]).parent)]
                promo_main()
        elif args.mode == "generate":
            from generate_real_demo import main as generate_main
            generate_main()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print("\nStopped. Completed output is preserved.", flush=True)
        sys.exit(130)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print("\nSetup could not finish: " + str(exc), file=sys.stderr)
        print("Fix the issue above and run Start-AI-Telephone again; completed downloads are reused.", file=sys.stderr)
        sys.exit(1)
