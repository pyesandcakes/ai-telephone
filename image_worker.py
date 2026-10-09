"""One image per process; request arrives on stdin, not command-line arguments."""
import json
import sys


def main():
    import torch
    from diffusers import AutoPipelineForText2Image
    request = json.load(sys.stdin)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    # Download fp16 weights, but use float32 arithmetic on MPS to avoid NaN/black frames.
    dtype = torch.float16 if device == "cuda" else torch.float32
    pipe = AutoPipelineForText2Image.from_pretrained(
        request["model"], revision=request["revision"], torch_dtype=dtype,
        use_safetensors=True, variant="fp16",
    ).to(device)
    pipe.enable_attention_slicing()
    # CPU generator is supported by Diffusers on MPS. Seed is recorded by host.
    latents = pipe(prompt=request["prompt"], num_inference_steps=request["steps"],
                 guidance_scale=0.0, width=512, height=512,
                 generator=torch.Generator(device="cpu").manual_seed(request["seed"]), output_type="latent").images
    if not torch.isfinite(latents).all():
        raise ValueError("Image model produced non-finite latents")
    with torch.no_grad():
        pixels = pipe.vae.decode(latents / pipe.vae.config.scaling_factor, return_dict=False)[0]
    if not torch.isfinite(pixels).all():
        raise ValueError("Image decoder produced non-finite pixels")
    image = pipe.image_processor.postprocess(pixels, output_type="pil")[0]
    # Rebuild from pixels to strip metadata, including any prompt fields.
    from PIL import Image
    clean = Image.frombytes("RGB", image.size, image.convert("RGB").tobytes())
    clean.save(request["destination"], format="PNG")
    print(json.dumps({"device": device, "torch": torch.__version__, "seed": request["seed"], "inference_dtype": str(dtype), "weight_variant": "fp16"}))


if __name__ == "__main__":
    main()
