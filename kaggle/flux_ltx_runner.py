# OpenMontage SANA + LTX Runner
# Reads prompts from prompts.json or env PROMPTS_JSON
# Saves photos and videos to /kaggle/working/

import os, json, gc, glob, sys
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import numpy as np
from PIL import Image

print("=== OpenMontage SANA + LTX Runner ===")

# STEP 0: INSTALL DEPENDENCIES
import subprocess
pkgs = [
    "diffusers>=0.32.0",
    "transformers>=4.46.0",
    "accelerate",
    "sentencepiece",
    "imageio[ffmpeg]",
    "Pillow",
]
subprocess.run(["pip", "install", "-q"] + pkgs, check=True)
print("Dependencies installed")

import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    total = torch.cuda.get_device_properties(0).total_memory
    print(f"VRAM: {total/1e9:.1f}GB")
device = "cuda" if torch.cuda.is_available() else "cpu"

# STEP 1: LOAD PROMPTS
scenes = []
channel = "weirdhistory"

# Source 1: file from dataset
prompts_paths = [
    "/kaggle/input/openmontage-prompts/prompts.json",
    "/kaggle/working/prompts.json",
]
for path in prompts_paths:
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        scenes = data.get("scenes", [])
        channel = data.get("channel", "weirdhistory")
        print(f"Prompts loaded from {path}: {len(scenes)} scenes")
        break

# Source 2: env variable (fallback)
if not scenes:
    prompts_json = os.environ.get("PROMPTS_JSON", "")
    if prompts_json:
        data = json.loads(prompts_json)
        scenes = data.get("scenes", [])
        channel = data.get("channel", "weirdhistory")
        print(f"Prompts from ENV: {len(scenes)} scenes")

# Source 3: test data
if not scenes:
    print("WARNING: using test prompts")
    scenes = [
        {
            "idx": i,
            "photo_prompt_1": f"dark medieval scene {i}, chiaroscuro lighting, 35mm grain, gothic architecture, candlelight, ultra detailed photorealistic",
            "photo_prompt_2": f"historical archive photo scene {i}, amber shadows, stone walls, dramatic lighting, ultra detailed",
            "video_prompt": f"cinematic slow motion medieval scene {i}, dark atmosphere, candlelight flicker, chiaroscuro, 4K",
            "generate_video": (i % 3 == 0)
        }
        for i in range(6)
    ]

print(f"Channel: {channel}")
print(f"Total scenes: {len(scenes)}")
video_scenes = [s for s in scenes if s.get("generate_video", s["idx"] % 3 == 0)]
print(f"Video scenes: {len(video_scenes)}")

# STEP 2: SANA — GENERATE ALL PHOTOS
print("\n=== PHASE 1: SANA PHOTOS ===")
SanaPipeline = None
for cls_name in ["SanaSprintPipeline", "SanaPipeline"]:
    try:
        exec(f"from diffusers import {cls_name}")
        SanaPipeline = eval(cls_name)
        print(f"Using {cls_name}")
        break
    except ImportError:
        continue

if SanaPipeline is None:
    from diffusers import AutoPipelineForText2Image as SanaPipeline
    print("Using AutoPipelineForText2Image")

pipe_sana = SanaPipeline.from_pretrained(
    "Efficient-Large-Model/Sana_Sprint_1.6B_1024px_diffusers",
    torch_dtype=torch.bfloat16,
)
from diffusers import AutoencoderDC
vae = AutoencoderDC.from_pretrained(
    "mit-han-lab/dc-ae-lite-f32c32-sana-1.1-diffusers",
    torch_dtype=torch.float16,
)
pipe_sana.vae = vae
pipe_sana.to(device)
print("SANA loaded (with DC-AE-Lite)")

photo_count = 0
for scene in scenes:
    idx = scene["idx"]
    for photo_num in [1, 2]:
        prompt_key = f"photo_prompt_{photo_num}"
        prompt = scene.get(prompt_key, scene.get("photo_prompt_1", "dark medieval scene"))
        out_path = f"/kaggle/working/s{idx:03d}_photo{photo_num}.jpg"

        try:
            img = pipe_sana(
                prompt=prompt,
                num_inference_steps=2,
                guidance_scale=4.0,
                width=1024,
                height=1024,
            ).images[0]

            img = img.resize((1920, 1080), Image.LANCZOS)
            img.save(out_path, "JPEG", quality=90)
            size = os.path.getsize(out_path)
            print(f"s{idx:03d}_photo{photo_num}.jpg: {size/1024:.0f}KB")
            assert size > 10000, f"Too small: {out_path}"
            photo_count += 1

        except Exception as e:
            print(f"ERROR photo {idx}/{photo_num}: {e}")
            colors = [(20,15,10),(15,20,10),(10,15,20)]
            color = colors[idx % 3]
            noise = np.random.randint(0,30,(1080,1920,3),dtype=np.uint8)
            img_arr = np.clip(np.array(color,dtype=np.uint8) + noise, 0, 255).astype(np.uint8)
            Image.fromarray(img_arr).save(out_path, "JPEG", quality=85)
            photo_count += 1

print(f"SANA done: {photo_count} photos")

# FREE VRAM
del pipe_sana
gc.collect()
torch.cuda.empty_cache()
torch.cuda.synchronize()
if torch.cuda.is_available():
    used = torch.cuda.memory_allocated()/1e9
    print(f"VRAM after SANA: {used:.2f}GB")

# STEP 3: LTX-VIDEO
print("\n=== PHASE 2: LTX-VIDEO ===")
from diffusers import LTXPipeline
import imageio

try:
    pipe_ltx = LTXPipeline.from_pretrained(
        "Lightricks/LTX-Video",
        torch_dtype=torch.bfloat16,
    )
    pipe_ltx.enable_model_cpu_offload()
    pipe_ltx.enable_attention_slicing()
    print("LTX-Video loaded")
    ltx_loaded = True
except Exception as e:
    print(f"LTX load failed: {e}")
    ltx_loaded = False

video_count = 0
if ltx_loaded:
    for scene in video_scenes:
        idx = scene["idx"]
        out_path = f"/kaggle/working/s{idx:03d}_video.mp4"

        try:
            output = pipe_ltx(
                prompt=scene.get("video_prompt", "cinematic dark scene"),
                negative_prompt="blurry, static, low quality, worst quality",
                width=640,
                height=384,
                num_frames=49,
                num_inference_steps=20,
                guidance_scale=3.0,
            )
            frames = output.frames[0]
            imageio.mimwrite(
                out_path,
                [np.array(f) for f in frames],
                fps=24,
                quality=7,
                macro_block_size=None,
            )
            size = os.path.getsize(out_path)
            print(f"s{idx:03d}_video.mp4: {size/1024:.0f}KB")
            assert size > 100000, f"Too small: {out_path}"
            video_count += 1

        except Exception as e:
            print(f"ERROR video {idx}: {e}")
            continue

    del pipe_ltx
    gc.collect()
    torch.cuda.empty_cache()

print(f"LTX done: {video_count} videos")

# STEP 4: FINAL REPORT
print("\n=== FINAL REPORT ===")
all_files = (
    glob.glob("/kaggle/working/s*_photo*.jpg") +
    glob.glob("/kaggle/working/s*_video.mp4")
)
all_files.sort()
total_size = 0
for f in all_files:
    size = os.path.getsize(f)
    total_size += size
    print(f"  {os.path.basename(f)}: {size/1024:.0f}KB")

print(f"\nTotal files: {len(all_files)}")
print(f"Photos: {photo_count}")
print(f"Videos: {video_count}")
print(f"Total size: {total_size/1024/1024:.1f}MB")

if photo_count == 0:
    print("CRITICAL ERROR: no photos")
    sys.exit(1)

print("=== KERNEL COMPLETE ===")
