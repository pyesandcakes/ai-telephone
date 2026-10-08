# One-off automated capture

This starts a finite chain automatically, opens the paired display and records its rendered output while the models work. The existing interactive installation remains available with `python app.py`.

## Real AI content

Complete the model setup in README.md first, including `python prepare.py`. Activate that environment and run from this folder:

```sh
python -m pip install -r requirements-capture.txt
python capture.py
```

Defaults: 12 iterations, a four-second hold, seed 42, SD-Turbo one step, Qwen2.5-VL 3B. The starting prompt is “A red umbrella floating above an empty swimming pool at night.” Everything then runs automatically and stops after the final pair.

For your own prompt:

```sh
python capture.py --prompt "A glass horse standing in a flooded library" --iterations 20 --hold 5
```

The original prompt appears on the video's opening title card and in private export files. The vision model still receives only pixels and the fixed description instruction.

## Recording test without AI models

```sh
python capture.py --mock --iterations 3 --hold 1
```

This generates colour fields and pixel-derived descriptions. Its video, frames and poster are labelled **MOCK / NO AI MODELS**. Use it to check the capture pipeline, not as evidence of real AI inference.

## Saved output

`captures/<timestamp>-capture-<id>/` contains:

- `live-recording.mp4`: 1920 × 1080 H.264 video encoded continuously while the chain runs, with model-phase labels and a short opening/ending hold.
- `captions.srt`: subtitle timing for captions actually observed in the live recording.
- `timeline.json`, `capture.json`, `result.json`, `encoder.log`: recording metadata and diagnostics.

`captures/<run-id>/` contains the normal complete run history plus `exports/`:

- `pair-001.png`, etc.: clean image/interpretation frames saved during the run.
- `poster-contact-sheet.png`: a high-resolution sheet of up to 12 stages, sampling the entire chain if it is longer.
- `iterations.csv`, `iterations.json`, `transcript.txt`: all inputs, interpretations and traceable iteration numbers.

The video captures only this installation's rendered image/text output. It does not record your desktop, other windows or audio. The capture preserves real generation/interpretation waits, so its duration depends on inference speed. Two frames per second is adequate for still-image/text sequences; use `--fps 5` if needed. The video is written as fragmented MP4 to improve recovery after interruption.

The encoder is bundled through imageio-ffmpeg; no separate FFmpeg installation or screen-recording software is needed. All generated images and iteration records are saved immediately. The contact sheet and transcript are assembled at the end, including committed iterations from a stopped/failed run. Saved images and JSON can still be recovered after a force quit even if final exports were not assembled.

The host binds to loopback for one-laptop capture. Add `--bind 0.0.0.0` if using LAN displays, or `--no-browser` for unattended recording. Keep the host awake and plugged in. On Mac, use `caffeinate -i python capture.py`.

Press Ctrl+C to stop early. In-flight inference finishes or times out before shutdown. The recording keeps the last completed pair; an unfinished iteration is discarded. Never force close the terminal during final encoding unless necessary.
