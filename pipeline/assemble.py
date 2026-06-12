import os, json, subprocess, math
from pathlib import Path
from config import get_channel_config, SCENE_DUR, PHOTO_DUR, VIDEO_DUR, CROSSFADE, FPS, RESOLUTION, CRF, AUDIO_BITRATE, TEST_MODE

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def assemble_video(channel, script, assets, tts):
    cfg = get_channel_config(channel)
    scenes = script if isinstance(script, list) else script.get("scenes", script)
    audio_files = tts.get("audio_files", [])
    images = assets.get("images", [])
    videos = assets.get("videos", [])
    music_path = assets.get("music")
    sfx_path = assets.get("sfx")

    scene_dur = SCENE_DUR if not TEST_MODE else 8
    photo_dur = PHOTO_DUR
    video_dur = VIDEO_DUR

    video_segments = []
    concat_file = OUTPUT_DIR / "concat_list.txt"

    for i, scene in enumerate(scenes):
        seg_dir = OUTPUT_DIR / f"seg_{i:03d}"
        seg_dir.mkdir(exist_ok=True)

        img_path = images[i] if i < len(images) else None
        vid_path = videos[i] if i < len(videos) else None
        audio_path = audio_files[i] if i < len(audio_files) else None

        seg_video = seg_dir / "video.mp4"
        seg_audio = seg_dir / "audio.mp3"
        seg_final = seg_dir / "final.mp4"

        if audio_path and os.path.getsize(audio_path) > 0:
            subprocess.run(
                ["cp", audio_path, str(seg_audio)],
                capture_output=True,
            )
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"anullsrc=r=44100:cl=mono",
                 "-t", str(scene_dur), str(seg_audio)],
                capture_output=True,
            )

        if img_path and os.path.exists(img_path):
            subprocess.run(
                ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                 "-i", str(seg_audio),
                 "-c:v", "libx264", "-t", str(scene_dur),
                 "-pix_fmt", "yuv420p",
                 "-vf", f"scale=w=1920:h=1080:force_original_aspect_ratio=1,pad=w=1920:h=1080:x=(ow-iw)/2:y=(oh-ih)/2:color=#14141e,fps={FPS}",
                 "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                 "-shortest", str(seg_video)],
                capture_output=True,
            )
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"color=c=14141e:s={RESOLUTION}:d={scene_dur}:r={FPS}",
                 "-i", str(seg_audio),
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                 "-shortest", str(seg_video)],
                capture_output=True,
            )

        video_segments.append(str(seg_video))

    with open(concat_file, "w") as f:
        for seg in video_segments:
            f.write(f"file '{os.path.abspath(seg)}'\n")

    channel_slug = channel.lower().replace(" ", "_")
    output_path = OUTPUT_DIR / f"{channel_slug}_final.mp4"

    color_grade = cfg.get("color_grade", "")
    filter_complex = ""
    if color_grade:
        filter_complex = f",{color_grade}"

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_file),
         "-c:v", "libx264", "-preset", "medium",
         "-crf", str(CRF),
         "-pix_fmt", "yuv420p",
         "-vf", f"fps={FPS}{filter_complex}",
         "-c:a", "aac", "-b:a", AUDIO_BITRATE,
         "-movflags", "+faststart",
         str(output_path)],
        check=True, capture_output=True,
    )

    if music_path and os.path.exists(music_path):
        mixed_path = OUTPUT_DIR / f"{channel_slug}_with_music.mp4"
        dur = _get_duration(str(output_path))
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(output_path),
             "-i", str(music_path),
             "-filter_complex",
             f"[1:a]volume=0.15,aloop=loop=-1:size={int(44100*dur)}[music];"
             f"[0:a][music]amix=inputs=2:duration=first[a]",
             "-map", "0:v", "-map", "[a]",
             "-c:v", "copy",
             "-c:a", "aac", "-b:a", AUDIO_BITRATE,
             "-shortest", str(mixed_path)],
            check=True, capture_output=True,
        )
        subprocess.run(["mv", str(mixed_path), str(output_path)], capture_output=True)

    cleanup(video_segments)
    return str(output_path)


def _get_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0


def cleanup(segments):
    for seg in segments:
        parent = Path(seg).parent
        if parent.exists():
            subprocess.run(["rm", "-rf", str(parent)], capture_output=True)
