"""One-off chain with live MP4 recording and poster-ready exports."""
import argparse
import csv
import json
import math
import platform
import subprocess
import threading
import time
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import BASE, Installation, handler_for, save_json

DEFAULT_PROMPT = "A red umbrella floating above an empty swimming pool at night."


def font(size):
    from PIL import ImageFont
    paths = ["C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for candidate in paths:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def wrap(draw, text, face, width):
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            if draw.textlength(word, font=face) > width:
                if line:
                    lines.append(line)
                    line = ""
                fragment = ""
                for char in word:
                    if fragment and draw.textlength(fragment + char, font=face) > width:
                        lines.append(fragment)
                        fragment = ""
                    fragment += char
                line = fragment
            elif line and draw.textlength(line + " " + word, font=face) > width:
                lines.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        lines.append(line)
    return lines


def draw_paragraph(draw, text, box, maximum=44):
    x, y, width, height = box
    for size in range(maximum, 11, -1):
        face = font(size)
        lines = wrap(draw, text, face, width)
        leading = math.ceil(size * 1.55)
        if len(lines) * leading <= height:
            break
    for line in lines:
        draw.text((x, y), line, font=face, fill="#161616")
        y += leading


def plate(image_path=None, caption="", iteration=0, phase="", mock=False, title=False):
    from PIL import Image, ImageDraw, ImageOps
    output = Image.new("RGB", (1920, 1080), "white")
    draw = ImageDraw.Draw(output)
    draw.text((80, 55), "A I   T E L E P H O N E", font=font(26), fill="#333333")
    if mock:
        draw.text((1260, 60), "MOCK RECORDING TEST / NO AI MODELS", font=font(19), fill="#8e301e")
    if image_path:
        with Image.open(image_path) as image:
            fitted = ImageOps.contain(image.convert("RGB"), (850, 850))
            output.paste(fitted, (80 + (850 - fitted.width) // 2, 115 + (850 - fitted.height) // 2))
    else:
        draw.text((80, 410), "An image becomes language.", font=font(37), fill="#333333")
        draw.text((80, 470), "Language becomes an image.", font=font(37), fill="#333333")
    draw.line((1030, 220, 1820, 220), fill="#dddddd", width=1)
    draw.text((1030, 250), "ORIGINAL PROMPT" if title else "INTERPRETATION", font=font(17), fill="#666666")
    draw_paragraph(draw, caption, (1030, 300, 790, 620))
    draw.text((80, 1020), f"ITERATION {iteration:03d}" if iteration else "ONE PROMPT / TWO MODEL CONTEXTS", font=font(16), fill="#666666")
    draw.text((1030, 1020), phase.upper(), font=font(16), fill="#666666")
    return output


def srt_time(seconds):
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def export_assets(folder, records, manifest):
    """Recoverable exports even when a capture was stopped or a model failed."""
    from PIL import Image, ImageDraw, ImageOps
    assets = folder / "exports"
    assets.mkdir(exist_ok=True)
    for item in records:
        pair_path = assets / f"pair-{item['iteration']:03d}.png"
        if not pair_path.exists():
            plate(folder / item["image"], item["caption"], item["iteration"],
                  mock=manifest["demo"]).save(pair_path, dpi=(150, 150))
    save_json(assets / "iterations.json", records)
    with (assets / "iterations.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, extrasaction="ignore", fieldnames=["iteration", "input", "caption", "seed", "seconds", "image", "time", "sha256"])
        writer.writeheader()
        writer.writerows(records)
    transcript = ["AI Telephone", "MOCK RECORDING TEST — no AI models" if manifest["demo"] else "Local AI capture",
                  "Original prompt: " + manifest["original_prompt"], ""]
    for item in records:
        transcript.extend([f"Iteration {item['iteration']:03d}", item["caption"], ""])
    (assets / "transcript.txt").write_text("\n".join(transcript), encoding="utf-8")
    if not records:
        return
    selected = records if len(records) <= 12 else [records[round(i * (len(records) - 1) / 11)] for i in range(12)]
    columns = 3
    rows = math.ceil(len(selected) / columns)
    sheet = Image.new("RGB", (2400, 380 + rows * 950), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((70, 60), "A I   T E L E P H O N E", font=font(42), fill="#161616")
    draw.text((70, 140), "MOCK TEST / NO AI MODELS" if manifest["demo"] else "One prompt. A chain of interpretations.", font=font(24), fill="#666666")
    draw_paragraph(draw, "Original prompt: " + manifest["original_prompt"], (70, 195, 2200, 150), maximum=28)
    for index, item in enumerate(selected):
        x, y = 70 + (index % columns) * 780, 380 + (index // columns) * 950
        with Image.open(folder / item["image"]) as source:
            picture = ImageOps.contain(source.convert("RGB"), (690, 620))
            sheet.paste(picture, (x, y))
        draw.text((x, y + 640), f"ITERATION {item['iteration']:03d}", font=font(19), fill="#666666")
        draw_paragraph(draw, item["caption"], (x, y + 680, 690, 235), maximum=25)
    sheet.save(assets / "poster-contact-sheet.png", dpi=(300, 300))


def capture(args):
    import imageio_ffmpeg
    if not args.mock:
        from prepare import environment
        info = environment()
        missing = [name for name, version in info["packages"].items() if version == "not installed"]
        if missing:
            raise SystemExit("Complete README model setup first. Missing: " + ", ".join(missing))
        if args.vision_model not in {model["name"] for model in info["models"]}:
            raise SystemExit("Before real capture run: ollama pull " + args.vision_model)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    installation = Installation(args.output, demo=args.mock)
    server = ThreadingHTTPServer((args.bind, args.port), handler_for(installation))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    # Start recording before the first model call, after a short prompt title card.
    session = args.output / (stamp + "-capture-" + __import__("uuid").uuid4().hex[:8])
    session.mkdir(parents=True)
    video = session / "live-recording.mp4"
    ffmpeg_log = (session / "encoder.log").open("wb")
    encoder = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "warning",
        "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080",
        "-r", str(args.fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
        str(video)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=ffmpeg_log)
    frame_count = 0
    timeline = []
    seen = set()
    run_id = None
    failure = None
    print("Capture folder:", session, flush=True)
    print("Models:", "MOCK TEST — no AI imagery" if args.mock else "REAL LOCAL AI", flush=True)
    print(f"Controls: http://127.0.0.1:{server.server_port}/#token={installation.token}", flush=True)
    print(f"Presentation: http://127.0.0.1:{server.server_port}/combined", flush=True)
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{server.server_port}/combined")
    def write_frame(picture):
        nonlocal frame_count
        encoder.stdin.write(picture.tobytes())
        frame_count += 1
    try:
        intro = plate(caption=args.prompt, mock=args.mock, title=True, phase="Beginning the chain")
        for _ in range(args.fps * 2):
            write_frame(intro)
        run_id = installation.start({"prompt": args.prompt, "interval": args.hold,
                                     "limit": args.iterations, "seed": args.seed,
                                     "steps": args.steps, "vision_model": args.vision_model})
        folder = installation.root / run_id
        save_json(session / "capture.json", {"run": run_id, "run_folder": str(folder.resolve()),
                  "mode": "mock" if args.mock else "real", "fps": args.fps,
                  "resolution": [1920, 1080], "python": platform.python_version(),
                  "recording": "live rendered output with model phases, no desktop capture"})
        (folder / "exports").mkdir()
        while True:
            tick = time.monotonic()
            state = installation.public_state()
            for record_file in sorted(folder.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")):
                if record_file.name in seen:
                    continue
                item = json.loads(record_file.read_text(encoding="utf-8"))
                clean = plate(folder / item["image"], item["caption"], item["iteration"], mock=args.mock)
                clean.save(folder / "exports" / f"pair-{item['iteration']:03d}.png", dpi=(150, 150))
                seen.add(record_file.name)
                print(f"Saved iteration {item['iteration']:03d} ({item['seconds']}s)", flush=True)
            state = installation.public_state()
            frame = state["frame"]
            if frame and (not timeline or timeline[-1]["iteration"] != frame["iteration"]):
                timeline.append({"iteration": frame["iteration"], "caption": frame["caption"], "start": frame_count / args.fps})
                save_json(session / "timeline.json", timeline)
            picture = plate(folder / Path(frame["image"]).name if frame else None,
                            frame["caption"] if frame else "The first image is being generated and interpreted.",
                            frame["iteration"] if frame else 0, phase=state["phase"], mock=args.mock)
            write_frame(picture)
            if not installation.active():
                for _ in range(args.fps * 3):
                    write_frame(picture)
                break
            time.sleep(max(0, 1 / args.fps - (time.monotonic() - tick)))
        failure = installation.error
    except KeyboardInterrupt:
        installation.stop()
        print("Stopping capture; waiting for the in-flight model call...", flush=True)
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        installation.stop()
    finally:
        if installation.thread:
            installation.thread.join(timeout=910)
        if encoder.stdin:
            encoder.stdin.close()
        encoder.wait(timeout=60)
        ffmpeg_log.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        if run_id:
            folder = installation.root / run_id
            records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))]
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            export_assets(folder, records, manifest)
            subtitle_lines = []
            for index, item in enumerate(timeline):
                end = timeline[index + 1]["start"] if index + 1 < len(timeline) else frame_count / args.fps
                if end <= item["start"]: continue
                subtitle_lines.extend([str(index + 1), f"{srt_time(item['start'])} --> {srt_time(end)}", item["caption"], ""])
            (session / "captions.srt").write_text("\n".join(subtitle_lines), encoding="utf-8")
        save_json(session / "result.json", {"run": run_id, "video": str(video.resolve()),
                  "video_seconds": frame_count / args.fps, "encoder_exit": encoder.returncode,
                  "status": installation.phase, "error": failure or installation.error,
                  "assets": str((installation.root / run_id / "exports").resolve()) if run_id else None})
    if failure or installation.error or encoder.returncode:
        raise SystemExit("Capture incomplete. Saved files are retained. " + (failure or installation.error or "Read encoder.log"))
    print("Finished. Video:", video, flush=True)
    print("Poster, paired frames, transcript and CSV:", installation.root / run_id / "exports", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--hold", type=float, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--vision-model", choices=["qwen2.5vl:3b", "qwen2.5vl:7b"], default="qwen2.5vl:3b")
    parser.add_argument("--mock", action="store_true", help="Labelled recording test without AI models")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--output", type=Path, default=BASE / "captures")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--fps", type=int, default=2, help="Video rate; 2 is sufficient for still-image sequences")
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100 or not 0.5 <= args.hold <= 120 or not 1 <= args.fps <= 10:
        parser.error("Use 1–100 iterations, 0.5–120 second hold, and 1–10 fps")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    capture(args)


if __name__ == "__main__":
    main()

