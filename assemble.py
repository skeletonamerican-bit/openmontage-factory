"""Final assembly: TTS + Footage + Music → MP4"""
import subprocess, json
from pathlib import Path

PROJ    = Path("/workspaces/OpenMontage/projects/weirdhistory")
AUDIO   = PROJ / "audio"
FOOTAGE = PROJ / "footage"
MUSIC   = PROJ / "music" / "background.mp3"
RENDER  = PROJ / "render"
RENDER.mkdir(exist_ok=True)

script  = json.loads((PROJ / "script.json").read_text())
scenes  = script["scenes"]
clips   = []

print("[1/3] Processing scenes...")
for i, scene in enumerate(scenes):
    sid     = scene["id"]
    wav     = AUDIO   / f"{sid}.wav"
    mp4     = FOOTAGE / f"{sid}.mp4"
    out     = RENDER  / f"{sid}_clip.mp4"

    if not wav.exists():
        print(f"  SKIP {sid} — no audio"); continue
    if not mp4.exists():
        print(f"  SKIP {sid} — no footage"); continue

    # Get audio duration
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1", str(wav)],
        capture_output=True, text=True)
    dur = float(r.stdout.strip() or scene["duration"])

    # Merge: loop footage to audio length, then burn audio
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(mp4),
        "-i", str(wav),
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", str(dur),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(out)
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        clips.append(out)
        print(f"  OK [{i+1}/{len(scenes)}] {sid}")
    else:
        print(f"  ERR {sid}: {r.stderr.decode()[-100:]}")

print(f"\n[2/3] Concatenating {len(clips)} clips...")
list_file = RENDER / "clips.txt"
with open(list_file, "w") as f:
    for c in clips:
        f.write(f"file '{c.resolve()}'\n")

merged = RENDER / "merged.mp4"
subprocess.run([
    "ffmpeg", "-y", "-loglevel", "error",
    "-f", "concat", "-safe", "0",
    "-i", str(list_file),
    "-c", "copy", str(merged)
], check=True)
print(f"  Merged: {merged.stat().st_size//1024//1024}MB")

print("\n[3/3] Adding background music...")
final = RENDER / "FINAL_weirdhistory.mp4"
subprocess.run([
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(merged),
    "-i", str(MUSIC),
    "-filter_complex",
    "[1:a]volume=0.12,aloop=loop=-1:size=2e+09[bg];"
    "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=3[aout]",
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
    str(final)
], check=True)

size  = final.stat().st_size // 1024 // 1024
print(f"\n{'='*50}")
print(f"DONE: {final.name}")
print(f"Size: {size} MB")
print(f"Path: {final}")
print(f"{'='*50}")
