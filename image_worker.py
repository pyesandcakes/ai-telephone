"""One image per process; request arrives on stdin, not command-line arguments."""
import json
import sys


def main():
    import torch
    from diffusers import AutoPipelineForText2Image
    request = json.load(sys.stdin)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float32 if device == "cpu" else torch.float16
    pipe = AutoPipelineForText2Image.from_pretrained(
        request["model"], revision=request["revision"], torch_dtype=dtype,
        use_safetensors=True,
    ).to(device)
    pipe.enable_attention_slicing()
    # CPU generator is supported by Diffusers on MPS. Seed is recorded by host.
    image = pipe(prompt=request["prompt"], num_inference_steps=request["steps"],
                 guidance_scale=0.0, width=512, height=512,
                 generator=torch.Generator(device="cpu").manual_seed(request["seed"])).images[0]
    # Rebuild from pixels to strip metadata, including any prompt fields.
    from PIL import Image
    clean = Image.frombytes("RGB", image.size, image.convert("RGB").tobytes())
    clean.save(request["destination"], format="PNG")
    print(json.dumps({"device": device, "torch": torch.__version__, "seed": request["seed"]}))


if __name__ == "__main__":
    main()
