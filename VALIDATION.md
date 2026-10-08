# Validation — 8 October 2026

Verified on this Windows development host:

- 8 Python tests passed using Python 3.14.7 (standard-library controller and mock models).
- Browser acceptance passed with headless Chromium: start from the form, two completed iterations, image and text pages updating, saved history, replay, and no JavaScript page errors.
- Python source compilation and JavaScript syntax checks passed.
- Control and text screenshots were visually reviewed.
- Single-laptop `/combined` added: browser acceptance checks both outputs, wide/narrow layout, and return to authenticated controls.
- Hugging Face's model API confirmed revision `b261bac6fd2cf515557d5d0707481eafa0485ec2` and the required SD-Turbo safetensors/config/tokenizer files.

Not validated in this environment:

- Real SD-Turbo / Qwen2.5-VL inference, the Python 3.12 model environment installation, M5 performance or memory use.
- Separate physical laptops, venue Wi-Fi/firewall behaviour, fullscreen behaviour across all browsers, or a long-duration exhibition run.
- Bit-exact repeatability between different machines.

Use the Mac setup and pre-exhibition procedure in README.md to complete these hardware checks. The demo is a wiring test and does not generate AI imagery.

## Automated capture validation

The complete project was moved to D:\OneDrive - TU Eindhoven\CBL\artifice\midterm\ai-telephone. All 11 application/capture tests passed under Python 3.12. The mock capture produced a decodable H.264 MP4, three clean pair frames, subtitle timing, CSV/JSON, transcript and a contact sheet. Real model capture has not been exercised: the required Qwen2.5-VL vision model is not installed on this development computer.

## Real Windows inference and promotional output

A complete 12-iteration real SD-Turbo / Qwen2.5-VL chain was run on the RTX 3060 under Python 3.12 and CUDA PyTorch 2.8.0. All image hashes and feedback links were verified. The live recording and 69.5-second promotional edit decoded without errors; the A3 poster PDF was reopened, rendered and visually checked. Five real browser screenshots were captured. All 11 application/capture tests passed after ensuring the final committed pair is exported. M5 inference remains untested. See PROMOTIONAL-OUTPUT.md for final assets and rerun instructions.
