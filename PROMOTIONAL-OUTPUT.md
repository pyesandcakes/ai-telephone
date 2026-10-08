# Real promotional demo - 8 October 2026

Installed and exercised on Bruno's Windows PC: Python 3.12, CUDA-enabled PyTorch 2.8.0, NVIDIA RTX 3060 12 GB, SD-Turbo and Ollama Qwen2.5-VL 3B. This run contains actual local model output, not the earlier colour-square mock.

The starting prompt was: “A red umbrella floating above an empty swimming pool at night.” Twelve iterations took the imagery from a red umbrella by dark water through sunset docks to a vivid city skyline. Every later image request used the previous interpretation. The vision requests remained separate and image-only apart from their constant description instruction.

## Ready-to-use files

All final designed assets are in `promotional-output/`:

- `AI-Telephone-promo-1080p.mp4` - 69.5-second, 1920 x 1080, 24fps H.264 edit with title cards, six chronological stages, short marked caption excerpts, transitions and credits. Silent; inference waits removed.
- `AI-Telephone-promo.srt` - timed captions for the edit.
- `AI-Telephone-poster-A3.pdf` - printable portrait A3 poster.
- `AI-Telephone-poster-A3.png` - 3508 x 4961 PNG for placing into a poster editor. Its canvas is 300dpi; generated source images are 512 x 512.
- `screenshots/` - actual browser views of the real run: controls/history, image-only, text-only and wide/portrait combined views.
- `video-stills/` - each promotional shot as a clean PNG.
- `provenance.json` - exact source run, edits and model reference.

The full live recording and its subtitle/timing files are in `captures/20261008-142403-capture-1758fe27/`.

All twelve original images, full descriptions, inputs, seeds, model metadata and logs are in `captures/b40698a494a64050b5af06ed8f7a70cb/`. Its `exports/` folder contains all twelve full image/text plates, a contact sheet, transcript and CSV/JSON.

The original prompt appears on the public-facing video's opening title card. It was never provided to the vision model. The edited video uses shortened descriptions for readability; full model text remains in the run folder. Source images and model text have not been retouched.

## Run again

The real-model environment and downloaded weights are now installed. From PowerShell in this project:

```powershell
powershell -ExecutionPolicy Bypass -File .\Run-Promotional-Demo.ps1
```

Optional custom prompt:

```powershell
powershell -ExecutionPolicy Bypass -File .\Run-Promotional-Demo.ps1 -Prompt "A glass horse standing in a flooded library" -Iterations 12
```

The launcher makes another full real capture and promotional export. It preserves prior run folders; the named files in `promotional-output/` are regenerated. Browser screenshots were taken automatically for this handoff; use `capture_browser.cjs` for another run if Node/Playwright are installed.

For another machine, install `requirements-promo.txt` in the model environment before running `build_promo.py`.

## Verification

All 11 application/capture tests passed after the final capture fix. All 12 PNG image hashes match their iteration records, and all 11 feedback links use the preceding caption. Both the live and promotional MP4 files decoded without errors. The A3 PDF was reopened, rendered and visually reviewed. The display now reduces caption font size when needed to fit longer real-model outputs.

Artistic and visual reference: https://www.jakeelwes.com/project-sontag.html
