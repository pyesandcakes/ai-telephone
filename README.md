# AI Telephone

A local installation for one or three laptops. One host generates an image, a separate vision model describes it, and that description becomes the next image prompt. Optional display laptops only need a browser.

## One laptop / three laptops

**One laptop:** start a chain in Controls, then choose **Present on this laptop**. The `/combined` page shows the generated image and its interpretation side by side, or stacked on a narrow/portrait screen. Click Fullscreen for presentation. The loop keeps running when you change views. Move the pointer to reveal the bottom bar and choose Controls to return to start/stop/history; the original prompt stays on the private control page. The normal control page also shows both outputs alongside all controls.

**Three laptops:** keep Controls on the host and open `/image` and `/text` on the other laptops. You can switch between either arrangement without restarting the chain. `/combined` also works on a remote display if only one additional laptop is available.

On the host, the combined display is `http://127.0.0.1:8765/combined`. No LAN connection is needed when everything is on one laptop.

## Artistic reference

The visual design takes cues from the reference's project page: a black gallery-like surface, restrained sans-serif typography, a light letter-spaced title, open image/text columns and fine dividing rules. Controls use monochrome rectangular elements; the paired presentation gives the image and interpretation generous space. The image-only display retains a black surround. No external fonts or artist media are required.

Inspiration: Jake Elwes, [A.I. Interprets A.I. Interpreting ‘Against Interpretation’ (Sontag 1966)](https://www.jakeelwes.com/project-sontag.html), 2023. The artist's page describes text-to-image and image-to-language interpretation of Sontag's essay, and documents single-channel and three-channel versions. AI Telephone explores a related translation process with a recursive chain: each generated interpretation becomes the next image prompt. This project is an independent implementation; it does not include the artist's footage, code or Sontag's essay.

```text
HOST / MacBook Pro
Original prompt → SD-Turbo → PNG pixels → Qwen2.5-VL → description
                    ↑                                     │
                    └─────────────────────────────────────┘
                               │
                  completed image + description
                               │ LAN
                  ┌────────────┴─────────────┐
             /image display             /text display
             Mac or Windows             Mac or Windows
```

## First: test the installation without downloading models

Copy this entire `ai-telephone` folder to the host. In a terminal opened inside it:

```sh
python app.py --simulated-demo
```

On a Mac, use `python3` if `python` is unavailable. Demo mode needs Python 3.11 or newer and **no packages**. It plays 18 bundled 1440 × 1080 procedural abstract artworks with scripted interpretations. These are illustrative simulated data, not outputs of image/vision inference or experimental evidence. A fixed starting prompt is used; custom prompts belong to real mode. Each scripted interpretation becomes the next recorded input, while imagery is pre-authored rather than generated from that input. The default demo finishes after 18 iterations; smaller limits are supported. No downloads or model packages are needed. Provenance is visible on displays and saved in manifests and iteration records. All three screens use a black background.

Open the **Controls** URL printed by the terminal on the host. Its temporary token is stored in that browser tab's session storage and removed from the address bar. Enter a prompt, set a small iteration limit, and start.

On the two other laptops, open these addresses with the host's actual LAN IP:

```text
http://HOST-LAN-IP:8765/image
http://HOST-LAN-IP:8765/text
```

Click **Fullscreen** on each. Escape exits fullscreen. If fullscreen is unsupported, use the browser's fullscreen menu. Keep all laptops plugged in with sleep disabled; screen wake locks often require HTTPS and are only a best-effort enhancement here.

## Real models on Apple Silicon

Install native ARM64 **Python 3.11 or 3.12** and [Ollama](https://ollama.com/download). The pinned inference environment is not intended for Python 3.14. Keep the Ollama application running, or run `ollama serve` in a separate terminal if it is not already serving.

From this folder:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5vl:3b
python prepare.py
python -m unittest -v test_app
```

`prepare.py` downloads image weights, checks the vision model, reports `mps`, `cuda` or `cpu`, and writes `environment.json` plus `environment-lock.txt`. **On the Mac, expect `mps`.** If it says `cpu`, check that Python is ARM64 and PyTorch supports your macOS/device before an exhibition.

After setup, run without Hugging Face network access:

```sh
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
caffeinate -i python app.py
```

`caffeinate -i` keeps the Mac from idle sleep while the host runs. The host always calls Ollama at `127.0.0.1:11434`; no image or text requests go to cloud model APIs. Do not expose Ollama to the LAN. Leave it exclusively for this installation during a performance so other workloads do not compete for memory.

The SD-Turbo worker starts and exits for **each image**, then Ollama loads vision and is asked to unload after its reply. This favours predictable memory use over maximum speed. Model reloads are part of the iteration time.

## Model choices

| Purpose | Implemented choice | Practical use |
|---|---|---|
| Image generation | `stabilityai/sd-turbo`, 512 × 512, 1–4 steps, guidance 0 | Start at one step for a fast baseline. More steps are an artistic setting to test. |
| Interpretation | `qwen2.5vl:3b` via Ollama | Default. Smallest supported option, good starting point for this installation. |
| Interpretation alternative | `qwen2.5vl:7b` via Ollama | Pull it first, then choose it in controls. Try when memory and latency allow. |

SD-Turbo's model card specifies one-step generation, guidance 0 and preferred 512 × 512 output. Review its model licence for your exhibition's use: [SD-Turbo model card](https://huggingface.co/stabilityai/sd-turbo).

Ollama lists Qwen2.5-VL 3B at about **3.2 GB** and 7B at **6 GB** of model files. Those figures are **not total runtime RAM**. See [Ollama's Qwen2.5-VL models](https://ollama.com/library/qwen2.5vl). Ollama 0.7.0 or newer is required by this model family; record the exact version used for the installation.

My planning recommendation is to start with the 3B configuration on a 16 GB machine and allow more memory headroom at 24–32 GB. These are planning estimates, not validated minimums. Avoid jumping to much larger models before measuring a 20-iteration run. Watch macOS Activity Monitor's memory pressure and use the recorded iteration durations to choose the hold time. This project has **not been benchmarked on an M5**; no seconds-per-image claim is made. Diffusers documents the Apple Silicon MPS path here: [MPS support](https://huggingface.co/docs/diffusers/optimization/mps).

SDXL / FLUX and MLX / Core ML engines are potential future adapters, not implemented options in this version. SD-Turbo was chosen to get a portable, relatively small baseline working first.

## Windows

**Display laptops:** no Python, Ollama or model installation is needed. Open the host's `/image` or `/text` URL in a current browser.

**Windows as the host:** the controller, demo, history and adapters use the same code. Install Python 3.12 and Ollama, then run PowerShell from this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5vl:3b
.\.venv\Scripts\python.exe prepare.py
$env:HF_HUB_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
.\.venv\Scripts\python.exe app.py
```

The image worker selects CUDA if the installed PyTorch build and NVIDIA driver support it, otherwise CPU. CPU fallback is useful for diagnosis but may be impractically slow. For GPU package selection use the official [PyTorch installation instructions](https://pytorch.org/get-started/locally/) and preserve the resulting environment lock. Windows GPU inference has not been tested here.

## LAN setup

1. Connect all three laptops to the same trusted private network; Ethernet is preferable for an exhibition.
2. Find the Mac's IP in its active network connection details, or with `ipconfig getifaddr en0` if Wi-Fi is on `en0`. On Windows, inspect `ipconfig` for the active adapter's IPv4 address.
3. Allow the host's Python process / TCP port **8765** through its firewall on the private network. The app binds to `0.0.0.0` by default. Use `--bind 127.0.0.1` for host-only testing.
4. Open the display links on both other laptops. If unreachable, check guest Wi-Fi/client isolation, VPNs, the firewall and the chosen IP.
5. Reserve the host's IP in the router if the installation will run repeatedly.

The browser displays poll once per second, preserve the last pair if disconnected, and reconnect automatically. The host publishes only completed pairs; the two laptops may change up to roughly one polling interval apart. This is **not frame-accurate synchronisation**. A new run keeps the previous pair on the walls until its first pair is ready.

This is a trusted-LAN HTTP installation, not an internet-facing service. Do not port-forward it. The image and caption displays are public on that LAN. Controls and private history require both a loopback connection on the host and the random control token; no token belongs in the display URLs.

## Controls and performance operation

- **Start new chain:** uses the entered prompt only for iteration 1. Later image prompts are exactly the previous caption, including any drift or model mistakes.
- **Stop:** prevents another step. A call already in flight finishes or times out; its unfinished pair is discarded. The UI shows `stopping` until then. Image worker timeout: 900 seconds; vision HTTP socket timeout: 300 seconds. These intentionally allow slow local hardware.
- **Iteration limit:** 0 runs until stopped; any positive value stops after that many completed pairs.
- **Hold:** extra seconds after a completed pair; generation and interpretation add their own time. There is no fixed frame rate.
- **Seeds:** image and vision use `starting seed + iteration - 1`, wrapping at 2³¹. Settings are fixed for the duration of a chain; changes apply on the next start.
- **Archive:** choose a saved run, page through iterations, inspect the image inputs, and replay a pair while stopped.
- **Errors:** stop the chain and preserve the last successful pair. Read Activity and `worker.log`, resolve the issue, and start a new chain.
- **Shutdown:** stop the chain, wait for it to settle, then press Ctrl+C in the host terminal. A forced interruption leaves committed history intact. A restarted host stays idle; it never silently resumes a chain.

Before opening to an audience, run at least 20 real iterations on the target host, confirm memory pressure stays acceptable, test both display laptops, disconnect/reconnect one display, and test Stop during both model phases. The browser-only demo cannot establish real model performance.

## Prompt isolation

The original prompt is present only in the controller's private run state, on disk, and in the image worker's input. It is never included in public state or the vision API request.

`image_worker.py` reconstructs a PNG from RGB pixels to strip image metadata. `LocalModels.describe()` accepts image bytes and model/seed settings; it receives no run, original prompt or history. Every Ollama call constructs a fresh one-message request containing the image and a constant instruction to describe visible content. No tools or previous conversation are supplied. `keep_alive: 0` requests model unloading. See [Ollama chat API](https://docs.ollama.com/api/chat).

This is **model-context and process separation**, not an operating-system security sandbox. The host account can read its own files. A model may infer the initial idea from pixels, and text drawn inside an image remains visible. The fixed instruction tells the vision model to treat image text as content, not commands; it cannot guarantee a model will always comply. These effects are part of the experiment's limits.

## History, logs and reproducibility

Each run is saved under `runs/<random-id>/`:

```text
manifest.json       original prompt, settings, model revision, software versions,
                    Ollama model digests, fixed vision instruction, run status
000001.png          generated RGB image (no prompt metadata)
000001.json         input, caption, seed, timestamp, duration, image SHA-256
events.jsonl        phase events and errors
worker.log          image process output and diagnostics
```

The six-digit JSON file is the commit marker for each iteration. Temporary/incomplete images are not published. Runs left `running` after a crash appear as `interrupted` on restart. History and replay survive restarts; exact in-place continuation is not implemented.

The image model is pinned to immutable Hugging Face revision `b261bac6fd2cf515557d5d0707481eafa0485ec2`. Direct Python dependencies are pinned in `requirements.txt`; `prepare.py` captures all installed package versions in a per-host lock and records Ollama's version/model digests. Each real run records that runtime information again. Preserve the lock, model caches and manifests when archiving an exhibition. Ollama tags can change: do not pull new weights mid-exhibition, and compare the recorded digests when reproducing a run.

Reinstall a captured Python environment with `python -m pip install -r environment-lock.txt` on an equivalent OS/Python environment. There is no universal hash-locked cross-platform dependency file here. Identical seeds do not guarantee bit-identical output across Apple/CUDA/CPU devices or library versions.

History grows until you remove it; no automatic deletion is performed. Monitor free disk space for continuous installations. Back up whole run folders, and manage them only while the host is stopped. Disk files contain the original prompt and are private to the host user, not encrypted.

## Verification and files

```sh
python -m unittest -v test_app
```

Tests cover feedback chaining, seed order, a fresh image-only vision payload, public API privacy, protected history, path traversal rejection, persistence/replay, failures and stop/concurrent-start behaviour. Tests use mock models and make no AI-service calls.

Optional browser acceptance test (requires Node.js):

```sh
npm install --no-save playwright
npx playwright install chromium --only-shell
node smoke-browser.cjs
```

It starts a disposable local demo, drives the control UI, checks both displays and history replay, and writes screenshots. It uses port 8766. Set `PYTHON` to the Python executable if `python` is not on PATH.

Implementation map: `app.py` owns orchestration/storage/HTTP, `models.py` owns model boundaries, `image_worker.py` runs diffusion, `prepare.py` prepares the environment, and `web/` contains the three browser views. There is no frontend build or CDN dependency.

## Automated midterm capture

See [CAPTURE.md](CAPTURE.md) for the one-off automatic mode. It starts a finite chain, saves clean image/text frames during the run, and records the live output to MP4. The final exports include a poster contact sheet, subtitle file, transcript, CSV and full iteration history.

After model setup, run `python capture.py`, or use `Capture-Midterm.ps1` on Windows and `bash Capture-Midterm.command` on Mac. The default uses real models. Use `--mock` for a clearly labelled recording-only test.

## Mac real-model demo

This Mac uses a separate `.venv-mac` environment (Python 3.11), with half-precision SD-Turbo downloads (~2.6 GB; full-precision arithmetic on the Apple GPU to avoid invalid/black pixels) and Qwen2.5-VL 3B (~3.2 GB). The existing Windows environment is preserved.

Start the local vision server with `/opt/homebrew/bin/ollama serve` if it is not already running. Double-click `Generate-Real-Demo.command` to produce 18 actual local image→vision iterations at 512 × 512, four image steps per frame. Each vision call receives only the image pixels; its caption becomes the next input. Output and model provenance are saved in `runs/`. This is the baseline model's native resolution, not the simulated artwork's 1440 × 1080 size.

After generation completes, double-click `Play-Real-Demo.command`. Open the printed Controls URL on the Mac, choose **Play recorded chain**, and use `/image` and `/text` on the display laptops. Playback runs without inference, checks original image hashes and feedback links, and is labeled **Recorded real-model chain**. It finishes after 18 frames by default; press Play again to restart. `--demo` still selects the separate simulated artwork sequence.

The original inference records preserve model/environment information and generation timings. Playback records identify their source run and preserve source iteration metadata; their elapsed times describe replay, not inference speed.

## Live demo and continuous testing on this Mac

`Live-Demo.command` (also `Play-Real-Demo.command`) starts real models, not recordings. `Continuous-Testing.command` opens the same controller with continuous testing selected. Both accept your own starting prompt. Choose the mode in the controller: **Live demo** defaults to 18 freshly generated iterations, with an adjustable limit; **Continuous testing** enforces no iteration limit and runs until Stop. Switching modes never overwrites your typed prompt. The caption from each image becomes the next image prompt, with isolated vision requests. Stop waits for the active model call and discards an unfinished pair.

Terminal equivalents: `.venv-mac/bin/python app.py --demo` and `.venv-mac/bin/python app.py --testing`. Only `--simulated-demo` selects the separate artificial test sequence. The explicit `--recorded-demo` option remains available for archive playback but is not used by either live launcher. Black backgrounds and `/image`, `/text`, `/combined` views are preserved.


## Automatic image and prompt saving

Both live demo and continuous testing save every completed iteration immediately in `runs/<run-id>/`. PNGs are named `000001.png`, `000002.png`, etc. Each run contains `prompts.txt` (readable original prompt, exact input for each image, interpretation/next prompt, image filename and seed) and `prompts.jsonl` (one structured record per completed iteration). Individual numbered JSON records and the manifest are also retained. Exports update as the chain runs, so completed images/prompts remain available after Stop or a later model error. An unfinished iteration is discarded. Every new run gets its own folder, preserving earlier runs. Prompt exports are private host files and are not served to display laptops.


## Replay a whole saved run

In the controller’s Iteration archive, choose a saved run, set Playback hold in seconds, and click Replay run. Images and exact saved interpretations play chronologically on `/combined`, `/image`, and `/text`. Optional Loop until Stop repeats the sequence. Stop interrupts playback promptly. No models are called; original images, prompts, timings and manifests remain unchanged. Playback is explicitly labeled, and cannot overlap live generation.


## Original prompt and readable replay

The combined page displays a labeled original starting prompt above the image/interpretation pair, including during saved-run replay. This display intentionally shares the original prompt through `/api/combined-state`; `/image`, `/text`, and `/api/state` continue to omit it, and the vision model still receives only pixels. Reset clears the original prompt too. Long originals can be scrolled in their dedicated area.

Whole-run replay defaults to Reading pace: at least 12 seconds per frame, roughly 150 words per minute plus a 3-second margin. The first frame includes extra time for the original prompt. Uncheck Reading pace to choose a fixed custom hold. No model inference is performed during playback.
