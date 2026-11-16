"""Build small, shareable Mac/Windows ZIPs with correct launcher permissions."""
import argparse
from pathlib import Path
import stat
import zipfile

BASE = Path(__file__).resolve().parent
COMMON_FILES = [
    "START-HERE.md", "README.md", "CAPTURE.md", "PROMOTIONAL-OUTPUT.md",
    "app.py", "models.py", "image_worker.py", "prepare.py", "launch.py",
    "capture.py", "build_promo.py", "generate_real_demo.py",
    "build_downloads.py",
    "requirements.txt", "requirements-capture.txt", "requirements-promo.txt",
]


def build(target, output):
    files = [BASE / name for name in COMMON_FILES]
    for folder in ("web", "demo"):
        files.extend(sorted(p for p in (BASE / folder).rglob("*") if p.is_file() and not p.name.startswith(".")))
    patterns = ("*.command",) if target == "Mac" else ("*.cmd", "*.ps1")
    for pattern in patterns:
        files.extend(sorted(BASE.glob(pattern)))
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"AI-Telephone-{target}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in files:
            relative = source.relative_to(BASE)
            info = zipfile.ZipInfo("AI-Telephone/" + relative.as_posix())
            info.create_system = 3  # Unix metadata, preserved by macOS Archive Utility.
            permissions = 0o755 if source.suffix == ".command" else 0o644
            info.external_attr = (stat.S_IFREG | permissions) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, source.read_bytes())
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "downloads")
    args = parser.parse_args()
    for target in ("Mac", "Windows"):
        archive = build(target, args.output)
        print(f"Created {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
