"""
flux_ltx_runner.py — Kaggle T4 x2 GPU runner for FLUX.1-schnell + LTX-Video 2B

Detects dual T4 GPUs, loads FLUX.1-schnell and LTX-Video 2B with bfloat16 + cpu offload.
For each scene:
  - photo1: FLUX image 1920x1080, 4 steps, channel style
  - photo2: FLUX image 1920x1080, 4 steps, different angle/composition
  - video: LTX-Video 1280x720, 97 frames, 8 steps

Reads: /kaggle/input/openmontage-prompts/scene_prompts.json
Writes: /kaggle/working/footage/s{scene_id}_photo1.jpg, s{scene_id}_photo2.jpg, s{scene_id}_1.mp4
"""
import json, os, subprocess, sys, time
import torch
from pathlib import Path

CHANNEL_STYLES = {
    "weirdhistory": "historical archive photograph, 35mm film grain, Rembrandt lighting, chiaroscuro, amber candlelight, dark academia",
    "crimeledger": "crime scene documentary, cold blue steel lighting, Fincher aesthetic, teal shadows, forensic atmosphere",
    "mindtactics": "psychological portrait, high contrast monochrome, red accent color, analog horror, VHS distortion",
}


def install_deps():
    deps = [
        "diffusers>=0.31.0", "transformers", "accelerate",
        "torch", "torchvision", "imageio[ffmpeg]", "sentencepiece",
        "protobuf",
    ]
    subprocess.run(["pip", "install", "-q"] + deps, check=True)


def load_prompts():
    paths = [
        Path("/kaggle/input/openmontage-prompts/scene_prompts.json"),
        Path("/kaggle/working/scene_prompts.json"),
    ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    sys.exit("ERROR: scene_prompts.json not found")


def make_flux_image(pipe, prompt, out_path, scene_id):
    if out_path.exists():
        return True
    try:
        result = pipe(
            prompt=prompt,
            width=1920, height=1080,
            num_inference_steps=4,
            guidance_scale=0.0,
            generator=torch.Generator("cuda").manual_seed(scene_id),
        )
        img = result.images[0]
        img.save(str(out_path), quality=92)
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def make_ltx_video(pipe, prompt, out_path):
    if out_path.exists():
        return True
    try:
        result = pipe(
            prompt=prompt,
            negative_prompt="blurry, low quality, watermark, text, distorted",
            width=1280, height=720,
            num_frames=97,
            num_inference_steps=8,
            guidance_scale=3.0,
        )
        frames = result.frames[0]
        import imageio
        imageio.mimwrite(
            str(out_path), frames,
            fps=30, quality=8,
            output_params=["-vcodec", "libx264", "-pix_fmt", "yuv420p"],
        )
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def inject_style(raw_prompt, channel):
    style = CHANNEL_STYLES.get(channel, "")
    if style:
        return f"{style}, {raw_prompt}"
    return raw_prompt


def main():
    print("=== FLUX + LTX Runner on Kaggle T4 x2 ===")
    install_deps()

    from diffusers import FluxPipeline, LTXPipeline

    num_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 0
    print(f"GPU count: {num_gpus}")
    for i in range(num_gpus):
        gpu_name = torch.cuda.get_device_name(i)
        vram_gb = torch.cuda.get_device_properties(i).total_memory / 1e9
        print(f"  GPU {i}: {gpu_name} | VRAM: {vram_gb:.1f}GB")
    if num_gpus == 0:
        sys.exit("ERROR: No GPU detected")

    data = load_prompts()
    channel = data.get("channel", "weirdhistory")
    scenes = data.get("scenes", [])
    total = len(scenes)
    print(f"Channel: {channel} | Scenes: {total}")

    out_dir = Path("/kaggle/working/footage")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n--- Loading FLUX.1-schnell ---")
    flux = FluxPipeline.from_pretrained(
        "black-forest-labs/FLUX.1-schnell",
        torch_dtype=torch.bfloat16,
    )
    flux.enable_model_cpu_offload()

    print("--- Loading LTX-Video 2B ---")
    ltx = LTXPipeline.from_pretrained(
        "Lightricks/LTX-Video",
        torch_dtype=torch.bfloat16,
    )
    ltx.enable_model_cpu_offload()
    ltx.vae.enable_tiling()

    for idx, scene in enumerate(scenes, 1):
        scene_id = scene.get("id")
        if not scene_id:
            continue

        img1_prompt = scene.get("img1_prompt") or scene.get("title", "")
        img2_prompt = scene.get("img2_prompt") or img1_prompt
        vid_prompt = scene.get("vid_prompt") or img1_prompt

        photo1 = out_dir / f"s{scene_id}_photo1.jpg"
        photo2 = out_dir / f"s{scene_id}_photo2.jpg"
        video = out_dir / f"s{scene_id}_1.mp4"

        sys.stdout.write(f"[{idx}/{total}] ")
        sys.stdout.flush()

        ok1 = make_flux_image(flux, inject_style(img1_prompt, channel), photo1, scene_id)
        sys.stdout.write("photo1 OK, ")
        sys.stdout.flush()

        ok2 = make_flux_image(flux, inject_style(img2_prompt, channel), photo2, scene_id + 1000)
        sys.stdout.write("photo2 OK, ")
        sys.stdout.flush()

        ok3 = make_ltx_video(ltx, inject_style(vid_prompt, channel), video)
        sys.stdout.write("video OK\n")
        sys.stdout.flush()

    print("\n=== Done ===")
    files = list(out_dir.iterdir())
    print(f"Generated {len(files)} assets:")
    for f in sorted(files):
        kb = f.stat().st_size // 1024 if f.is_file() else 0
        print(f"  {f.name} ({kb}KB)")


if __name__ == "__main__":
    main()
