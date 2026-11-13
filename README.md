# AI Telephone

An image becomes language. Language becomes the next image. SD-Turbo generates images locally; Qwen2.5-VL describes their pixels through local Ollama. The host can be a Mac or Windows computer. Additional display computers need only a browser.

## Start here

1. Download/copy the whole project folder and extract it if zipped.
2. Double-click **`Start-AI-Telephone.command` on Mac** or **`Start-AI-Telephone.cmd` on Windows**.
3. If Python is missing, the launcher opens its download page. Install **Python 3.12** (3.11 also works; [3.12 installers](https://www.python.org/downloads/release/python-31210/)), then double-click again. On Windows, include the Python launcher when installing. The pinned model packages do not target Python 3.13 or newer.
4. If Ollama is missing, setup opens [Ollama's installer page](https://ollama.com/download). Install and open Ollama, then press Enter in the setup terminal to continue.
5. Wait for first-time setup. It creates a local Python environment, installs dependencies, starts Ollama, checks both models and downloads missing files. Downloads total roughly 6 GB for the default models, plus Python packages. Allow additional disk space for installation and saved images. Keep internet connected until setup finishes.
6. The authenticated controller opens in your browser. Enter a prompt and click **Start live demo**. Use **Present on this laptop** to see the image, interpretation and starting prompt together.

Leave the terminal open while running. To finish, click **Stop**, wait for the current model call, then press Ctrl+C in the terminal. Completed images and prompts remain saved.

If macOS blocks opening the downloaded script, use Finder's **Open** action or the relevant Privacy & Security setting. You can also open Terminal in this folder and run `bash Start-AI-Telephone.command`. On Windows, use the `.cmd` launcher; no permanent PowerShell execution-policy change is needed.

### Accounts and keys

**No paid API key is required by this implementation.** Inference uses your own computer, not a cloud model API. The default public models normally download without signing in. Local Ollama models do not require an Ollama account.

If Hugging Face returns an access restriction, setup explains where to sign in and accept any applicable model terms **using your own account**, then asks for your own read token with hidden input. The Hugging Face library stores authentication in your user cache, not this repository. You can instead authenticate with `hf auth login` in the model environment or set `HF_TOKEN` privately before launching. Never put tokens in source files, screenshots, prompts or shared launchers. The launcher does not load `.env` files.

Existing model files are reused. Setup checks every required SD-Turbo file at its pinned revision and the selected Ollama model tag. It does not update an already installed Ollama model. Rerun the launcher after an interrupted download to resume missing files. Once setup is complete, SD-Turbo inference runs with Hugging Face offline mode enabled. Internet is needed again only when dependencies or model files are missing, or when selecting an undownloaded vision model.

### Hardware

- **Apple Silicon Mac:** uses PyTorch MPS with float32 arithmetic, retaining the fix for invalid/black frames.
- **Windows with supported NVIDIA GPU:** setup chooses a CUDA PyTorch wheel and checks that an actual GPU kernel runs. CUDA 12.6 is the default for older GPU architectures; newer architectures use CUDA 12.8. An appropriate NVIDIA driver is required.
- **CPU fallback:** supported, including computers without a supported GPU, but generation can be slow. Intel Macs and Windows ARM machines are not validated targets for the pinned dependencies; install failures are reported rather than claiming universal GPU support.

The launcher prints the actual device. If you expected NVIDIA acceleration but it reports CPU, check your driver and GPU compatibility. AMD/Intel GPU acceleration on Windows is not implemented by this adapter. A historical Windows run used an RTX 3060 12 GB; a historical Mac run used Apple M5 with 16 GB. Those are tested configurations, not minimum specifications or performance guarantees.

## Modes and shortcuts

| Task | Mac | Windows |
|---|---|---|
| Open controller / live demo | `Start-AI-Telephone.command` | `Start-AI-Telephone.cmd` |
| Continuous real generation | `Continuous-Testing.command` | `Continuous-Testing.cmd` |
| Automated recording and exports | `Capture-Midterm.command` | `Capture-Midterm.cmd` |
| Real capture plus promotional video/poster | `Run-Promotional-Demo.command` | `Run-Promotional-Demo.cmd` |
| Generate a fixed 18-frame real chain | `Generate-Real-Demo.command` | `Generate-Real-Demo.cmd` |

`Live-Demo` and `Play-Real-Demo.command` remain aliases for the live controller. They perform fresh inference. Use the controller's **Replay run** for saved playback.

In the controller, **Live demo** defaults to 18 iterations; **Continuous testing** runs until Stop. You can switch modes before starting. The 3B vision model is the default; selecting 7B downloads it automatically on first use if absent. Downloads show as a model-download phase; progress is printed in the terminal. Stop during an active download or model call waits for that operation to finish or fail.

Capture and promotional dependencies are installed automatically only when those workflows are requested. See [CAPTURE.md](CAPTURE.md) for output details. Promotional mode regenerates named files in `promotional-output/`; it preserves original capture/run folders.

### Terminal options

Run these from the project folder with Python 3.11/3.12. You do not need to activate an environment; the launcher selects or creates one.

```sh
python launch.py                         # Setup, then open the controller
python launch.py --mode setup            # Prepare models without starting the web host
python launch.py --check                 # Read-only check; no installs, downloads or service starts
python launch.py --mode testing          # Continuous mode selected in the controller
python launch.py --mode simulated        # Bundled simulated art; no packages/models required
python launch.py --vision-model qwen2.5vl:7b
python launch.py --bind 127.0.0.1 --port 8766 --no-browser
python launch.py --mode capture -- --prompt "A glass horse in a flooded library" --iterations 12
python launch.py --mode capture -- --mock --iterations 3 --hold 1
python launch.py --mode promo -- --iterations 12
```

On Mac, use `python3.12` or `bash Start-AI-Telephone.command` in place of `python` if needed. On Windows, use `py -3.12` or `Start-AI-Telephone.cmd`. The double-click launchers also accept these options from a terminal. `--` separates capture options from launcher options.

Windows troubleshooting overrides:

```powershell
.\Start-AI-Telephone.cmd --torch-backend cpu
.\Start-AI-Telephone.cmd --torch-backend cu126
.\Start-AI-Telephone.cmd --torch-backend cu128
```

An explicit backend may reinstall PyTorch. The wheel choices follow [PyTorch's versioned installation commands](https://pytorch.org/get-started/previous-versions/). GPU selection changes image generation only; Ollama manages its own vision-model device.

## Displays and LAN

The browser opens the host-only controller with its temporary authentication token. Keep that tab. The terminal also prints the control URL. A second launcher refuses to start on an occupied port; use the original control link/tab or choose another port.

On the host:

- `http://127.0.0.1:8765/combined` — image, caption and original prompt.
- `http://127.0.0.1:8765/image` — image only.
- `http://127.0.0.1:8765/text` — interpretation only.

For additional Mac/Windows display laptops, connect to the same trusted private network and replace `127.0.0.1` with the host's LAN IPv4 address. Find it in network settings or `ipconfig` on Windows. Allow the host Python process/TCP port 8765 through the private-network firewall. No model installation is needed on display laptops. Use Fullscreen on each display.

The launcher prevents idle sleep on Mac/Windows while the application runs. Keep laptops plugged in. Displays poll once per second, retain the last completed pair on disconnect, and reconnect automatically; this is not frame-accurate synchronization. Use `--bind 127.0.0.1` for host-only operation. Ollama remains on `127.0.0.1:11434`; do not expose it to the LAN.

## Setup storage and troubleshooting

New environments live under `.runtime/<os>-<architecture>/`, which is ignored by Git. A valid existing `.venv-mac` (Mac) or `.venv` (Windows) is reused. Copied or relocated environments are checked before use; an unusable managed environment is preserved under a timestamped name and recreated. Do not distribute virtual environments as portable installations. Model weights live in each user's Hugging Face/Ollama caches and are checked on that computer.

- **No supported Python:** install 3.11/3.12 and rerun. Model dependencies are pinned for these versions.
- **Ollama won't start:** open the Ollama app and retry. See `tmp/ollama-launch.log`.
- **Download interrupted:** reconnect and rerun. Existing cached files are reused. Check free disk space.
- **Missing weights with `HF_HUB_OFFLINE` enabled:** unset that variable during setup. The launcher enables it only after checking the image files.
- **CUDA cannot run:** update the NVIDIA driver or use CPU override. An incompatible GPU does not become supported merely by installing a CUDA wheel.
- **Port occupied:** stop the existing instance or use `--port 8766`; use the printed links with the new port.
- **Slow chain:** each iteration includes image loading/generation, vision loading/interpretation and the configured hold. Start with 3B and one image step.
- **Model error:** the previous successful pair remains visible. Read Activity and the run's `worker.log`; resolve the issue and start a new chain.

`prepare.py` also remains available for manually managed environments. `python prepare.py` starts/checks Ollama and downloads missing models; `python prepare.py --check` inspects only. Setup records this host's packages, device, Ollama version and model digests in `environment.json` and `environment-lock.txt`. These local records are ignored by Git.

## Model and data behavior

```text
Starting prompt → SD-Turbo → PNG pixels → Qwen2.5-VL → description
                      ↑                                  │
                      └──────────────────────────────────┘
```

SD-Turbo generates 512 × 512 images with 1–4 steps and guidance 0. The image-model revision is pinned to `b261bac6fd2cf515557d5d0707481eafa0485ec2`. Qwen2.5-VL 3B or 7B receives a fresh one-message request with image pixels and a fixed instruction to describe visible content. It never receives the original generation prompt, run history or tools. PNG metadata is stripped. Each caption becomes exactly the next image prompt.

A separate image subprocess exits after each generation; Ollama is asked to unload vision after each description. This limits memory overlap at the expense of model reload time. Identical seeds do not guarantee identical pixels across devices/library versions. Review the [SD-Turbo model card](https://huggingface.co/stabilityai/sd-turbo) and applicable model terms for your use.

Controls and history require both a loopback connection and the random controller token. `/api/state`, `/image` and `/text` omit the original prompt. **`/combined` intentionally shares it**, through `/api/combined-state`. Images/captions and that combined prompt are visible to anyone who can access the host on the LAN. This is a trusted-LAN HTTP installation, not an internet-hosted service. Model context separation is not an OS security sandbox.

Each original run is saved under `runs/<random-id>/`:

```text
manifest.json      Original prompt, settings, model/runtime provenance and status
000001.png         Generated RGB pixels
000001.json        Exact input, caption, seed, duration, time and image hash
prompts.txt        Readable incremental prompt/interpretation export
prompts.jsonl      Structured incremental export
worker.log         Image worker diagnostics
events.jsonl       Phase/error events
```

The numbered JSON is the commit marker; unfinished pairs are discarded. Stop finishes the current call before settling (image timeout 900 seconds; vision socket timeout 300 seconds). Saved runs survive restart; automatic in-place continuation is not implemented. Replay checks image hashes and does no inference or rewriting of original records. Reset clears displays while retaining history.

Saved prompt files are private host files, not encrypted. History grows until you remove it. Back up whole run folders and manage them while stopped. Preserve per-host locks/caches for reproducibility; the captured lock is not a universal cross-platform installer.

## Verification and implementation

In the model environment:

```sh
python -m unittest -v test_launch test_app test_capture
```

The suite checks setup reuse, incomplete caches, download/authentication paths, GPU-wheel selection, feedback chaining, prompt isolation, stop/failure behavior, persistence/replay, HTTP access and a complete mock MP4 capture. Setup tests simulate missing models rather than downloading GB of weights.

Optional browser acceptance (Node.js):

```sh
npm install --no-save playwright
npx playwright install chromium --only-shell
node smoke-browser.cjs
```

Set `PYTHON` to the model environment's interpreter if needed. Hardware validation and historical results are in [VALIDATION.md](VALIDATION.md).

| Files | Responsibility |
|---|---|
| `launch.py`, `Start-AI-Telephone.*` | Shared bootstrap, dependency setup and guided launch |
| `prepare.py` | Ollama startup, cache verification, downloads and environment records |
| `app.py` | Feedback loop, storage, HTTP routes and replay |
| `models.py`, `image_worker.py` | Local inference boundaries and diffusion worker |
| `web/` | Controller and display pages; no build/CDN dependency |
| `capture.py`, `build_promo.py`, `capture_browser.cjs` | Recording, exports and promotional assets |
| `demo/` | Explicitly simulated artwork/interpretation sequence |
| `platformio.ini`, `src/main.cpp` | Separate ESP32/LD2450 radar experiment, not wired into AI Telephone |

Artistic and visual reference: Jake Elwes, [A.I. Interprets A.I. Interpreting ‘Against Interpretation’](https://www.jakeelwes.com/project-sontag.html), 2023. This is an independent implementation; it includes none of the artist's footage, code or Sontag's essay.
