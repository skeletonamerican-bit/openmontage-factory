"""Test: build one scene through the new pipeline (Part 7)"""
import os, sys, subprocess, json, time
from pathlib import Path

CHANNEL = "weirdhistory"
os.environ["CHANNEL"] = CHANNEL
sys.path.insert(0, ".")

from assemble_v2 import *

tmp = Path("/tmp/omfactory")
tmp.mkdir(exist_ok=True)

PROJECT_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
FOOTAGE_DIR.mkdir(parents=True, exist_ok=True)

# Create test assets
print("=== Creating test assets ===")
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x2B0000:s=1920x1080:d=0.1",
    "-vframes", "1", str(FOOTAGE_DIR / "s000_photo1.jpg")],
    check=True, capture_output=True)
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1A0033:s=1920x1080:d=0.1",
    "-vframes", "1", str(FOOTAGE_DIR / "s000_photo2.jpg")],
    check=True, capture_output=True)
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1A0A00:s=1920x1080:d=5.5",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(FOOTAGE_DIR / "s000_video.mp4")],
    check=True, capture_output=True)
subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=180:duration=15",
    "-ac", "1", "-ar", "22050", str(AUDIO_DIR / "1.wav")],
    check=True, capture_output=True)

# Create script
script = {
    "title": "Test Scene",
    "scenes": [{
        "id": 1,
        "title": "The Corpse Trial Begins",
        "narration": "In 897 AD, Pope Stephen VI did the unthinkable. He exhumed the corpse of his predecessor dressed it in papal robes and put it on trial for perjury.",
        "sfx": "cinematic_boom"
    }]
}
json.dump(script, open(PROJECT_DIR / "script.json", "w"), indent=2, ensure_ascii=False)

print("=== Processing scene 0 ===")
t0 = time.time()
wavs = sorted(AUDIO_DIR.glob("*.wav"))
print(f"Using WAV: {wavs[0].name}")

scene = script["scenes"][0]
idx = 0
p = tmp / f"s{idx:02d}"
cfg = CHANNEL_CONFIGS[CHANNEL]
kb_a, kb_b = get_ken_burns_modes(idx)
print(f"Ken Burns modes: {kb_a}, {kb_b}")

photo1 = FOOTAGE_DIR / f"s{idx:03d}_photo1.jpg"
photo2 = FOOTAGE_DIR / f"s{idx:03d}_photo2.jpg"
video = FOOTAGE_DIR / f"s{idx:03d}_video.mp4"

# Step 1: Clip 1 - LTX-Video
print(f"\n[Step 1] Video clip...")
t1 = time.time()
vclip = Path(str(p) + "_vclip.mp4")
prep_video_clip(video, vclip, VIDEO_DUR, cfg)
print(f"  Done in {time.time()-t1:.1f}s -> {vclip.stat().st_size/1024:.0f}KB")

# Step 2: Clip 2 - Photo 1 + Ken Burns
print(f"\n[Step 2] Photo 1 + {kb_a}...")
t1 = time.time()
kb1 = Path(str(p) + "_kb1.mp4")
ken_burns_photo(photo1, kb1, PHOTO_DUR, kb_a, cfg)
print(f"  Done in {time.time()-t1:.1f}s -> {kb1.stat().st_size/1024:.0f}KB")

# Step 3: Clip 3 - Photo 2 + Ken Burns
print(f"\n[Step 3] Photo 2 + {kb_b}...")
t1 = time.time()
kb2 = Path(str(p) + "_kb2.mp4")
ken_burns_photo(photo2, kb2, PHOTO_DUR, kb_b, cfg)
print(f"  Done in {time.time()-t1:.1f}s -> {kb2.stat().st_size/1024:.0f}KB")

# Step 4: Crossfade concat
print(f"\n[Step 4] Crossfade concat...")
t1 = time.time()
offset1 = VIDEO_DUR - XFADE_DUR
offset2 = 2 * VIDEO_DUR - 2 * XFADE_DUR
concat_raw = Path(str(p) + "_concat.mp4")
subprocess.run([
    "ffmpeg", "-y",
    "-i", str(vclip), "-i", str(kb1), "-i", str(kb2),
    "-filter_complex",
    f"[0:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset1}[t0];"
    f"[t0][2:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset2}[video]",
    "-map", "[video]",
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-an", str(concat_raw)
], check=True, capture_output=True)
print(f"  Done in {time.time()-t1:.1f}s -> {concat_raw.stat().st_size/1024:.0f}KB")

# Step 5: Subtitles
print(f"\n[Step 5] Burn subtitles...")
t1 = time.time()
sub = Path(str(p) + "_sub.mp4")
burn_subs(concat_raw, sub, scene["narration"], SCENE_DUR)
print(f"  Done in {time.time()-t1:.1f}s")

# Step 6: Audio mix
print(f"\n[Step 6] Audio mix...")
t1 = time.time()
mix_a = Path(str(p) + "_mix.aac")
mix_scene_audio(wavs[0], None, mix_a, SCENE_DUR, idx)
print(f"  Done in {time.time()-t1:.1f}s")

# Step 7: Final scene
print(f"\n[Step 7] Final scene assembly...")
t1 = time.time()
out = Path(str(p) + "_wa.mp4")
subprocess.run([
    "ffmpeg", "-y", "-i", str(sub), "-i", str(mix_a),
    "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)
], check=True, capture_output=True)
print(f"  Done in {time.time()-t1:.1f}s")

# FFProbe check
print(f"\n=== FFProbe Verification ===")
r = subprocess.run(["ffprobe", "-v", "error",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
    capture_output=True, text=True)
dur = float(r.stdout.strip())

r2 = subprocess.run(["ffprobe", "-v", "error",
    "-select_streams", "v:0",
    "-show_entries", "stream=width,height,r_frame_rate",
    "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
    capture_output=True, text=True)
parts = r2.stdout.strip().split()
w = parts[0] if len(parts) > 0 else "?"
h = parts[1] if len(parts) > 1 else "?"
fps = parts[2] if len(parts) > 2 else "?"

print(f"  Duration: {dur:.2f}s")
print(f"  Resolution: {w}x{h}")
print(f"  FPS: {fps}")
print(f"  File size: {out.stat().st_size / 1048576:.1f}MB")

# Verify criteria
print(f"\n=== Test Results ===")
checks = []
dur_ok = abs(dur - 15.0) <= 0.1
checks.append(("Duration 15.0s (±0.1)", f"{dur:.2f}s", "PASS" if dur_ok else "FAIL"))
res_ok = w == "1920" and h == "1080"
checks.append(("Resolution 1920x1080", f"{w}x{h}", "PASS" if res_ok else "FAIL"))
fps_ok = fps == "30/1" or fps == "30"
checks.append(("FPS 30", fps, "PASS" if fps_ok else "FAIL"))

for name, got, status in checks:
    print(f"  [{status}] {name} (got: {got})")

print(f"\nTotal time: {time.time()-t0:.1f}s")

# Cleanup
for f in [kb1, kb2, vclip, concat_raw, sub, mix_a, out]:
    if f and f.exists():
        f.unlink()
