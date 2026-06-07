import json
import math
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MONEY_WORDS = {
    "money", "cash", "profit", "wealth", "investment", "bank", "crypto", "earnings", "bonus", "revenue"
}
LOSS_WORDS = {
    "loss", "debt", "risk", "failure", "drop", "steal", "crime", "dark", "danger", "broken"
}


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)


def run(cmd):
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def load_script(channel):
    path = ROOT / "projects" / channel / "script.json"
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")
    return json.loads(path.read_text())


def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:06.3f}"


def make_subtitles(script, path):
    lines = []
    lines.append("[Script Info]")
    lines.append("Title: OpenMontage subtitles")
    lines.append("ScriptType: v4.00+")
    lines.append("PlayResX: 1920")
    lines.append("PlayResY: 1080")
    lines.append("ScaledBorderAndShadow: yes")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append(
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding"
    )
    lines.append(
        "Style: Default,DejaVu Sans,52,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1"
    )
    lines.append("")
    lines.append("[Events]")
    lines.append(
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"
    )

    current_time = 0.0
    for scene in script["scenes"]:
        narration = scene["narration"].strip()
        words = [w for w in narration.split() if w]
        if not words:
            current_time += float(scene["duration"])
            continue

        word_duration = float(scene["duration"]) / max(len(words), 1)
        for idx, word in enumerate(words):
            cleaned = word.strip(".,?!:;\"'()[]")
            lower = cleaned.lower()
            color = ""
            if lower in MONEY_WORDS:
                color = "{\\c&H00FFFF&}"
            elif lower in LOSS_WORDS:
                color = "{\\c&H0000FF&}"

            start = current_time + idx * word_duration
            end = start + word_duration
            text = f"{color}{word}" if color else word
            lines.append(
                f"Dialogue: 0,{format_timestamp(start)},{format_timestamp(end)},Default,,0,0,0,,{text}"
            )

        current_time += float(scene["duration"])

    path.write_text("\n".join(lines))


def build_scene_source(scene, channel, index, output_dir):
    scene_id = scene["id"]
    duration = float(scene["duration"])
    scene_video = output_dir / f"scene_{index:02d}.mp4"
    image_file = ROOT / "projects" / channel / "images" / f"{scene_id}.png"
    footage_dir = ROOT / "projects" / channel / "footage"
    audio_file = ROOT / "projects" / channel / "audio" / f"{scene_id}.wav"

    if scene_video.exists():
        print(f"Skipping existing scene video: {scene_video}")
        return scene_video

    source = None
    if scene["type"] == "broll":
        candidates = sorted(footage_dir.glob(f"{scene_id}_*.mp4"))
        if candidates:
            source = candidates[0]

    if source is None and image_file.exists():
        source = image_file

    if source is None:
        raise FileNotFoundError(f"No source media found for {scene_id}")

    if source.suffix.lower() == ".mp4":
        run([
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-t",
            str(duration),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-an",
            str(scene_video),
        ])
    else:
        if scene.get("ken_burns", False):
            frames = max(1, int(duration * 30))
            zoom_filter = (
                "scale=1920:1080,zoompan="
                f"z='if(gte(zoom,1.3),1.3,zoom+0.0008)':"
                "x='iw/2-(iw/zoom/2)':"
                "y='ih/2-(ih/zoom/2)':"
                f"d=1:s=1920x1080"
            )
            run([
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(source),
                "-vf",
                zoom_filter,
                "-frames:v",
                str(frames),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                str(scene_video),
            ])
        else:
            run([
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(source),
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                str(scene_video),
            ])

    return scene_video


def join_audio(audio_files, output_path):
    list_file = output_path.parent / "audio_concat.txt"
    with open(list_file, "w") as f:
        for item in audio_files:
            f.write(f"file '{item.as_posix()}'\n")
    run([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        str(output_path),
    ])


def build_video_chain(scene_videos, output_path):
    inputs = []
    for video in scene_videos:
        inputs.extend(["-i", str(video)])

    filter_commands = []
    total_duration = 0.0
    last_label = None
    for index, video in enumerate(scene_videos):
        duration = float(video.stem.split("_")[-1]) if False else 0.0
        # durations are computed from script later
        pass

    # Use sequential xfade chain
    filter_parts = []
    cumulative = 0.0
    for i, video in enumerate(scene_videos):
        if i == 0:
            continue
        prev_duration = video_durations[i - 1]
        offset = cumulative + prev_duration - 0.3
        if i == 1:
            filter_parts.append(
                f"[0:v][1:v]xfade=transition=fade:duration=0.3:offset={offset}[v1]"
            )
        else:
            filter_parts.append(
                f"[v{i-1}][{i}:v]xfade=transition=fade:duration=0.3:offset={offset}[v{i}]"
            )
        cumulative += prev_duration

    filter_complex = ";".join(filter_parts)
    last_label = f"[v{len(scene_videos) - 1}]"
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_complex, "-map", last_label, "-c:v", "libx264", "-crf", "18", "-preset", "medium", str(output_path)]
    run(cmd)


def build_video_with_subtitles(video_path, subtitles_path, output_path):
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"ass={subtitles_path}",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "copy",
        str(output_path),
    ])


def mix_with_music(video_path, voice_path, output_path, duration):
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(voice_path),
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=220:duration={duration}",
        "-filter_complex",
        "[2:a]volume=0.06[music];[1:a]volume=1.0[voice];[voice][music]amix=inputs=2:dropout_transition=0,volume=1.0[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ])


def create_thumbnail(video_path, output_path, channel, topic):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = f"{channel.replace('_', ' ').title()} - {topic}"
    run([
        "ffmpeg",
        "-y",
        "-ss",
        "45",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        (
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{text}':fontcolor=white:fontsize=64:box=1:boxcolor=black@0.6:x=(w-text_w)/2:y=h-120"
        ),
        str(output_path),
    ])


def build_shorts(video_path, output_dir, start_times):
    output_dir.mkdir(parents=True, exist_ok=True)
    for idx, start in enumerate(start_times, start=1):
        out_path = output_dir / f"short_{idx}.mp4"
        run([
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(video_path),
            "-t",
            "15",
            "-vf",
            "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out_path),
        ])


def main():
    channel = os.getenv("CHANNEL")
    topic = os.getenv("TOPIC", "")
    if not channel:
        raise SystemExit("Missing CHANNEL environment variable")

    script = load_script(channel)
    output_dir = ROOT / "projects" / channel
    build_dir = output_dir / "build"
    ensure_dir(build_dir)

    scene_videos = []
    scene_audio_files = []
    durations = []
    for idx, scene in enumerate(script["scenes"], start=1):
        scene_video = build_scene_source(scene, channel, idx, build_dir)
        scene_videos.append(scene_video)
        durations.append(float(scene["duration"]))
        scene_audio_files.append(output_dir / "audio" / f"{scene['id']}.wav")

    audio_master = build_dir / "final_voice.wav"
    join_audio(scene_audio_files, audio_master)

    temp_video = build_dir / "temp_video.mp4"
    # Build xfade chain for video segments
    inputs = []
    for video in scene_videos:
        inputs.extend(["-i", str(video)])

    filter_parts = []
    for i in range(1, len(scene_videos)):
        offset = sum(durations[: i + 1]) - 0.3 * i
        if i == 1:
            filter_parts.append(
                f"[0:v][1:v]xfade=transition=fade:duration=0.3:offset={offset}[v1]"
            )
        else:
            filter_parts.append(
                f"[v{i-1}][{i}:v]xfade=transition=fade:duration=0.3:offset={offset}[v{i}]"
            )

    if not filter_parts:
        raise RuntimeError("No scene videos generated")

    filter_complex = ";".join(filter_parts)
    run([
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        filter_complex,
        "-map",
        f"[v{len(scene_videos) - 1}]",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        str(temp_video),
    ])

    subtitles_path = build_dir / "subtitles.ass"
    make_subtitles(script, subtitles_path)

    subtitled_video = build_dir / "temp_video_subtitles.mp4"
    build_video_with_subtitles(temp_video, subtitles_path, subtitled_video)

    final_video = output_dir / "final.mp4"
    total_duration = sum(durations)
    mix_with_music(subtitled_video, audio_master, final_video, total_duration)

    thumbnail = output_dir / "thumbnail.jpg"
    create_thumbnail(final_video, thumbnail, channel, topic)

    build_shorts(final_video, output_dir, [0, 20, 40])

    print(f"Final video saved to: {final_video}")
    print(f"Thumbnail saved to: {thumbnail}")


if __name__ == "__main__":
    main()
