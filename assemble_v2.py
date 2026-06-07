import json
import math
import os
import subprocess
from pathlib import Path

PROJECT = Path("projects/twisted-truths-ep1")
AUDIO = PROJECT / "audio"
FOOTAGE = PROJECT / "footage"
RENDER = PROJECT / "render"
RENDER.mkdir(parents=True, exist_ok=True)

MONEY_WORDS = {
    "money", "dollars", "million", "thousand", "bank", "investment", "profit",
    "revenue", "pay", "salary", "cash", "fund", "budget", "asset", "value"
}
LOSS_WORDS = {
    "loss", "debt", "risk", "failure", "crime", "fraud", "danger", "stolen",
    "betrayal", "collapse", "dark", "struggle", "pain", "broken", "gaslighting"
}
NAME_BLACKLIST = {"She", "It", "The", "By", "When", "That", "Her", "His", "A", "An", "In"}


def ffmpeg(cmd):
    print("ffmpeg", " ".join(cmd))
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error"] + cmd, check=True)


def ffprobe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip() or 0.0)


def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:06.3f}"


def make_subtitles(scenes):
    lines = [
        "[Script Info]",
        "Title: twisted-truths-ep1 word-by-word subtitles",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Default,Arial Bold,72,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,2,2,60,60,150,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    current_time = 0.0
    for scene in scenes:
        narration = scene["narration"].strip()
        words = [w for w in narration.replace("\n", " ").split() if w]
        if not words:
            current_time += float(scene["duration"])
            continue

        audio_path = RENDER / f"{scene['id']}_trimmed.wav"
        if not audio_path.exists():
            audio_path = AUDIO / f"{scene['id']}.wav"
        duration = ffprobe_duration(audio_path)
        word_duration = duration / len(words)

        for j, raw_word in enumerate(words):
            word = raw_word.strip(".,?!:;:\"'()[]")
            lower = word.lower()
            tag = ""
            if lower in MONEY_WORDS or (word.istitle() and word not in NAME_BLACKLIST and len(word) > 1):
                tag = "{\\c&H0000FFFF&}"
            elif lower in LOSS_WORDS:
                tag = "{\\c&H000000FF&}"

            start = current_time + j * word_duration
            end = start + word_duration
            text = f"{tag}{raw_word}"
            lines.append(
                f"Dialogue: 0,{format_timestamp(start)},{format_timestamp(end)},Default,,0,0,0,,{{\\pos(960,842)}}{text}"
            )

        current_time += duration

    subtitle_file = RENDER / "FINAL_v2.ass"
    subtitle_file.write_text("\n".join(lines))
    return subtitle_file


def detect_and_trim_duplicates(input_wav, output_wav):
    try:
        import librosa
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise SystemExit(
            "librosa and soundfile are required for duplicate audio detection. "
            "Install with pip install librosa soundfile"
        ) from exc

    y, sr = librosa.load(str(input_wav), sr=None)
    intervals = librosa.effects.split(y, top_db=25, frame_length=2048, hop_length=512)
    if len(intervals) < 2:
        sf.write(str(output_wav), y, sr)
        return output_wav

    keep = [intervals[0]]
    prev_feat = None
    for start, end in intervals:
        segment = y[start:end]
        if len(segment) < sr * 0.05:
            continue
        mfcc = librosa.feature.mfcc(y=segment, sr=sr, n_mfcc=13)
        feat = np.mean(mfcc, axis=1)
        norm = np.linalg.norm(feat)
        if norm > 0:
            feat = feat / norm
        if prev_feat is not None:
            similarity = float(np.dot(prev_feat, feat))
            segment_duration = (end - start) / sr
            if similarity > 0.96 and segment_duration < 0.75:
                print(f"Trim duplicate segment: similarity={similarity:.2f}, duration={segment_duration:.2f}s")
                continue
        keep.append((start, end))
        prev_feat = feat

    if len(keep) == len(intervals) and all((int(a[0]) == int(b[0]) and int(a[1]) == int(b[1])) for a, b in zip(keep, intervals)):
        sf.write(str(output_wav), y, sr)
        return output_wav

    trimmed = np.concatenate([y[start:end] for start, end in keep])
    sf.write(str(output_wav), trimmed, sr)
    return output_wav


def generate_whoosh(path):
    ffmpeg([
        "-f", "lavfi",
        "-i", "anoisesrc=color=white:duration=0.9",
        "-af", "highpass=f=500,lowpass=f=4000,volume=-18dB",
        "-c:a", "pcm_s16le",
        str(path),
    ])
    return path


def build_scene_clip(scene, subtitle_path):
    scene_id = scene["id"]
    audio_in = AUDIO / f"{scene_id}.wav"
    if not audio_in.exists():
        raise FileNotFoundError(f"Missing audio for {scene_id}")

    trimmed = RENDER / f"{scene_id}_trimmed.wav"
    detect_and_trim_duplicates(audio_in, trimmed)
    duration = ffprobe_duration(trimmed)

    footage_file = FOOTAGE / f"{scene_id}.mp4"
    if not footage_file.exists():
        raise FileNotFoundError(f"Missing footage for {scene_id}")

    clip_out = RENDER / f"{scene_id}_clip_v2.mp4"
    ffmpeg([
        "-stream_loop", "-1",
        "-i", str(footage_file),
        "-i", str(trimmed),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", f"{duration}",
        "-filter_complex",
        (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease," 
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black," 
            "zoompan=z='zoom+0.0008':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080,fps=25,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        str(clip_out),
    ])
    return clip_out, duration


def concatenate_clips(clip_paths, output_path):
    concat_txt = RENDER / "FINAL_v2_clips.txt"
    concat_txt.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))
    ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(output_path),
    ])
    return output_path


def add_whoosh_sfx(video_path, whoosh_path, scene_durations, output_path):
    offsets = []
    current = 0.0
    for dur in scene_durations[:-1]:
        current += dur
        offsets.append(int(current * 1000))

    if not offsets:
        ffmpeg(["-i", str(video_path), "-c", "copy", str(output_path)])
        return output_path

    audio_tracks = ["-i", str(video_path)]
    for _ in offsets:
        audio_tracks += ["-i", str(whoosh_path)]

    filter_parts = []
    for idx, offset in enumerate(offsets):
        filter_parts.append(f"[{idx+1}:a]adelay={offset}|{offset},volume=0.12[s{idx}]")
    mix_inputs = "".join(f"[s{idx}]" for idx in range(len(offsets)))
    filter_parts.append(f"[0:a]{mix_inputs}amix=inputs={len(offsets)+1}:dropout_transition=0[aout]")
    filter_complex = ";".join(filter_parts)

    ffmpeg(audio_tracks + ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(output_path)])
    return output_path


def burn_subtitles(video_path, subtitle_path, output_path):
    ffmpeg([
        "-i", str(video_path),
        "-vf", f"ass={subtitle_path}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ])
    return output_path


def main():
    script = json.loads((PROJECT / "script.json").read_text())
    scenes = script["scenes"]

    print("[1/4] Generating scene clips with Ken Burns and trimmed audio...")
    clip_paths = []
    durations = []
    for scene in scenes:
        clip_path, dur = build_scene_clip(scene, None)
        clip_paths.append(clip_path)
        durations.append(dur)

    print("[2/4] Concatenating clips...")
    merged = RENDER / "FINAL_v2_merged.mp4"
    concatenate_clips(clip_paths, merged)

    print("[3/4] Generating subtitles and whoosh SFX...")
    subtitle_file = make_subtitles(scenes)
    whoosh_path = generate_whoosh(RENDER / "whoosh.wav")
    sfx_video = RENDER / "FINAL_v2_with_whoosh.mp4"
    add_whoosh_sfx(merged, whoosh_path, durations, sfx_video)

    print("[4/4] Burning subtitles into final render...")
    final = RENDER / "FINAL_v2.mp4"
    burn_subtitles(sfx_video, subtitle_file, final)

    print(f"DONE: {final}")


if __name__ == "__main__":
    main()
