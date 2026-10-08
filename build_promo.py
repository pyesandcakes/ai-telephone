"""Make promotion-ready assets from an actual, traceable AI Telephone run."""
import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
import imageio_ffmpeg

from capture import draw_paragraph, font, plate, srt_time


def excerpt(text, words=32):
    parts = text.split()
    if len(parts) <= words:
        return text
    prefix = " ".join(parts[:words])
    stop = max(prefix.rfind("."), prefix.rfind("!"), prefix.rfind("?"))
    if stop > 0 and len(prefix[:stop].split()) >= 12:
        prefix = prefix[:stop + 1]
    return prefix.rstrip(".") + "..."


def title_card(headline, explanation, subline):
    picture = Image.new("RGB", (1920, 1080), "white")
    draw = ImageDraw.Draw(picture)
    draw.text((100, 90), "A R T I F I C E   /   B R U N O", font=font(23), fill="#666666")
    draw_paragraph(draw, headline, (100, 310, 1680, 260), maximum=110)
    draw.line((100, 640, 1820, 640), fill="#dddddd", width=2)
    draw_paragraph(draw, explanation, (100, 690, 1530, 225), maximum=35)
    draw.text((100, 990), subline, font=font(19), fill="#666666")
    return picture


def promotional_video(folder, records, manifest, output):
    selected = records if len(records) <= 6 else [records[round(i * (len(records) - 1) / 5)] for i in range(6)]
    cards = [(title_card("AI TELEPHONE", "An image becomes language. Language becomes an image.",
                        "A recursive installation / real local AI output"), 4.0, "AI Telephone. An image becomes language. Language becomes an image.")]
    cards.append((title_card("ONE PROMPT", manifest["original_prompt"],
                            "The vision model never receives this prompt."), 4.0, manifest["original_prompt"]))
    for item in selected:
        caption = excerpt(item["caption"])
        picture = plate(folder / item["image"], caption, item["iteration"],
                        phase="Interpretation excerpt" if caption != item["caption"] else "Interpretation")
        cards.append((picture, 8.0, caption))
    cards.append((title_card("WHAT SURVIVES\nTHE TRANSLATION?",
                  "Two models. Separate contexts. A continuous chain of images and interpretations.",
                  "ARTIFICE / Bruno / Midterm    |    Edited sequence: inference waits removed"), 5.0,
                  "What survives the translation? Two models. Separate contexts. A continuous chain."))
    cards.append((title_card("IMAGE / LANGUAGE / IMAGE", "Concept and visual inspiration: Jake Elwes,\nA.I. Interprets A.I. Interpreting 'Against Interpretation' (2023).",
                            "Independent implementation / SD-Turbo + Qwen2.5-VL / silent video"), 4.0,
                  "Concept and visual inspiration: Jake Elwes. Independent implementation."))
    frames_folder = output / "video-stills"
    frames_folder.mkdir(exist_ok=True)
    for index, (picture, _, _) in enumerate(cards):
        picture.save(frames_folder / f"shot-{index + 1:02d}.png")
    fps = 24
    fade = 12
    video = output / "AI-Telephone-promo-1080p.mp4"
    timeline = []
    count = 0
    with (output / "promo-encoder.log").open("wb") as log:
        encoder = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "warning", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", str(fps), "-i", "-", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(video)], stdin=subprocess.PIPE, stderr=log, stdout=subprocess.DEVNULL)
        try:
            previous = None
            for index, (picture, seconds, caption) in enumerate(cards):
                start = count / fps
                if previous is not None:
                    for frame in range(fade):
                        encoder.stdin.write(Image.blend(previous, picture, (frame + 1) / fade).tobytes())
                        count += 1
                raw = picture.tobytes()
                for _ in range(round(seconds * fps)):
                    encoder.stdin.write(raw)
                    count += 1
                timeline.append({"shot": index + 1, "start": start, "end": count / fps, "caption": caption})
                previous = picture
        finally:
            encoder.stdin.close()
            encoder.wait(timeout=120)
        if encoder.returncode:
            raise RuntimeError("Video encoding failed; see promo-encoder.log")
    (output / "promo-timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    subtitles = []
    for index, item in enumerate(timeline):
        subtitles.extend([str(index + 1), f"{srt_time(item['start'])} --> {srt_time(item['end'])}", item["caption"], ""])
    (output / "AI-Telephone-promo.srt").write_text("\n".join(subtitles), encoding="utf-8")
    return count / fps


def poster(folder, records, manifest, output):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A3
    from reportlab.lib.utils import ImageReader
    width, height = 3508, 4961
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((230, 155), "A R T I F I C E   /   B R U N O   /   M I D T E R M", font=font(34), fill="#666666")
    draw.text((220, 320), "AI TELEPHONE", font=font(228), fill="#111111")
    draw_paragraph(draw, "An image becomes language.\nLanguage becomes an image.", (230, 650, 2900, 300), maximum=82)
    draw.line((230, 1030, 3278, 1030), fill="#dddddd", width=3)
    first = records[0]
    with Image.open(folder / first["image"]) as original:
        picture = ImageOps.fit(original.convert("RGB"), (1760, 1760), method=Image.Resampling.LANCZOS)
        sheet.paste(picture, (230, 1130))
    draw.text((2170, 1140), f"{first['iteration']:02d} / FIRST INTERPRETATION", font=font(32), fill="#666666")
    draw_paragraph(draw, first["caption"], (2170, 1250, 1100, 1050), maximum=63)
    draw.text((2170, 2400), "ORIGINAL PROMPT", font=font(30), fill="#666666")
    draw_paragraph(draw, manifest["original_prompt"], (2170, 2480, 1100, 385), maximum=44)
    selected = [records[round((len(records) - 1) * ratio)] for ratio in (1 / 3, 2 / 3, 1)]
    for index, item in enumerate(selected):
        x = 230 + index * 1050
        with Image.open(folder / item["image"]) as source:
            thumb = ImageOps.fit(source.convert("RGB"), (940, 940), method=Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x, 3020))
        draw.text((x, 4000), f"{item['iteration']:02d} / INTERPRETATION", font=font(28), fill="#666666")
        draw_paragraph(draw, excerpt(item["caption"], 28), (x, 4070, 940, 340), maximum=35)
    draw.line((230, 4500, 3278, 4500), fill="#dddddd", width=3)
    explanation = "One model makes an image. A second describes the pixels without seeing its prompt.\nThat interpretation becomes the next image prompt. The chain continues."
    draw_paragraph(draw, explanation, (230, 4560, 2900, 150), maximum=35)
    draw.text((230, 4780), f"{len(records)} real iterations / SD-Turbo + Qwen2.5-VL / independent implementation", font=font(27), fill="#666666")
    draw.text((230, 4840), "Inspired by Jake Elwes, A.I. Interprets A.I. Interpreting 'Against Interpretation' (2023).", font=font(24), fill="#666666")
    png = output / "AI-Telephone-poster-A3.png"
    sheet.save(png, dpi=(300, 300))
    pdf = output / "AI-Telephone-poster-A3.pdf"
    page = canvas.Canvas(str(pdf), pagesize=A3)
    page.setTitle("AI Telephone - ARTIFICE Midterm")
    page.setAuthor("Bruno")
    page.drawImage(ImageReader(sheet), 0, 0, width=A3[0], height=A3[1])
    page.showPage()
    page.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, default=Path("promotional-output"))
    args = parser.parse_args()
    folder = args.run.resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("demo"):
        raise SystemExit("Promotional exports require a real AI run, not mock footage")
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))]
    if len(records) < 3:
        raise SystemExit("At least three completed real iterations are required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    duration = promotional_video(folder, records, manifest, output)
    poster(folder, records, manifest, output)
    metadata = {"source_run": str(folder), "original_prompt": manifest["original_prompt"],
                "iterations": len(records), "video_seconds": duration, "resolution": "1920x1080 / 24fps",
                "poster": "A3 portrait / 300dpi canvas / source images 512px",
                "edits": "Chronological selected iterations, shortened captions marked excerpt, inference waits removed, silent.",
                "reference": "https://www.jakeelwes.com/project-sontag.html"}
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

