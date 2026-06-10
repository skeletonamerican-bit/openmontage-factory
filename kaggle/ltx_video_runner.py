"""
ltx_video_runner.py — Kaggle T4 GPU inference for LTX-Video 2B
Generates 4-second cinematic clips from AI image prompts
Supports weirdhistory, crimeledger, mindtactics channels
"""
import json, os, subprocess, sys
from pathlib import Path

def install_deps():
    subprocess.run([
        "pip", "install", "-q",
        "diffusers>=0.31.0", "transformers", "accelerate",
        "torch", "torchvision", "imageio[ffmpeg]", "sentencepiece"
    ], check=True)

def load_prompts():
    p = Path("/kaggle/working/scene_prompts.json")
    if not p.exists():
        p = Path("/kaggle/working/openmontage-factory/scene_prompts.json")
    with open(p) as f:
        return json.load(f)

def generate_clip(pipe, prompt, scene_id, out_dir, channel):
    out_path = out_dir / f"{scene_id}_1.mp4"
    if out_path.exists():
        print(f"  Skip {scene_id} (exists)")
        return out_path
    print(f"  Generating {scene_id}...")
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
        output_params=["-vcodec", "libx264", "-pix_fmt", "yuv420p"]
    )
    print(f"  OK: {out_path.name}")
    return out_path

def build_prompt(scene, channel):
    base = scene.get("visual", scene.get("narration", ""))
    style_prefixes = {
        "weirdhistory": "historical archive photo, 35mm film grain, Rembrandt lighting, chiaroscuro, moody shadows, dark academia aesthetic, slow cinematic zoom",
        "crimeledger": "crime scene documentary footage, cold steel grey, dark green tint, fluorescent lighting, forensic photography aesthetic, slow dolly zoom",
        "mindtactics": "dark psychological portrait, high contrast, one color accent, psychiatric file aesthetic, analog horror, VHS texture, unsettling slow zoom",
    }
    prefix = style_prefixes.get(channel, "cinematic documentary footage, 4K, dramatic lighting")
    return f"{prefix}, {base}"

def main():
    print("=== LTX-Video Runner on Kaggle T4 ===")
    install_deps()
    channel = os.environ.get("CHANNEL", "weirdhistory")

    import torch
    from diffusers import LTXPipeline

    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9 if torch.cuda.is_available() else 0
    print(f"GPU: {gpu_name} | VRAM: {vram_gb:.1f}GB")

    print("Loading LTX-Video 2B distilled...")
    pipe = LTXPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()

    prompts = load_prompts()
    out_dir = Path("/kaggle/working/footage")
    out_dir.mkdir(exist_ok=True)
    scenes = prompts.get("scenes", [])
    print(f"Generating {len(scenes)} clips for channel: {channel}")

    for scene in scenes:
        sid = scene["id"]
        prompt = build_prompt(scene, channel)
        generate_clip(pipe, prompt, sid, out_dir, channel)

    mp4s = list(out_dir.glob("*.mp4"))
    print(f"\nDone! Generated {len(mp4s)} clips")
    for mp4 in mp4s:
        print(f"  {mp4.name}")

if __name__ == "__main__":
    main()
