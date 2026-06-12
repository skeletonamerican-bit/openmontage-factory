import os, json, subprocess, math, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import get_channel_config, SCENE_DUR, PHOTO_DUR, VIDEO_DUR, FPS, RESOLUTION, CRF, AUDIO_BITRATE, TEST_MODE, PHOTO_COUNT

FONT_PATH = "/tmp/fonts/Montserrat/static/Montserrat-ExtraBold.ttf"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

KEYWORDS = {
    "secret", "truth", "never", "always", "shocking", "revealed", "hidden",
    "dark", "mystery", "deadly", "danger", "fear", "war", "death", "life",
    "money", "power", "mind", "brain", "kill", "crime", "evil", "terrifying",
    "amazing", "incredible", "unexpected", "banned", "illegal", "controversial",
    "terrifying", "disturbing", "forbidden", "deadly", "fatal", "nightmare",
}


def assemble_video(channel, script, assets, tts):
    cfg = get_channel_config(channel)
    scenes = script if isinstance(script, list) else script.get("scenes", script)
    audio_files = tts.get("audio_files", [])
    scene_assets = assets.get("scene_assets", {})
    music_path = assets.get("music")

    is_test = bool(TEST_MODE)
    scene_dur = 8 if is_test else SCENE_DUR
    frame_count = PHOTO_COUNT
    frame_durs = _frame_durations(scene_dur, frame_count)

    n = len(scenes)
    last_act_scene = n // 3 - 1
    second_act_scene = 2 * n // 3 - 1
    last_scene = n - 1

    frames_dir = OUTPUT_DIR / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    def _run_frame_task(func, args):
        func(*args)

    tasks = []
    frame_paths = []
    cut_timestamps = []
    t = 0.0

    for si in range(n):
        sa = scene_assets.get(si, {})
        photos = sa.get("photos", [])
        vid_path = sa.get("video") if sa.get("video") and os.path.exists(sa["video"]) else None

        for fi in range(frame_count):
            fd = frame_durs[fi]
            out = frames_dir / f"scene_{si:03d}_frame{fi}.mp4"

            if fi == 0 and vid_path:
                tasks.append((_make_video_frame, (vid_path, fd, out)))
            elif fi < len(photos):
                tasks.append((_make_ken_burns_frame, (photos[fi], fd, _ken_burns_params(si, fi), out)))
            else:
                tasks.append((_make_color_frame, (fd, out)))

            is_last = (si in (last_act_scene, second_act_scene, last_scene)) and fi == frame_count - 1
            if is_last:
                faded = frames_dir / f"scene_{si:03d}_frame{fi}_faded.mp4"
                tasks.append((_fade_out, (str(out), str(faded), fd)))
                out = faded

            is_first = (si in (last_act_scene + 1, second_act_scene + 1)) and fi == 0
            if is_first:
                faded = frames_dir / f"scene_{si:03d}_frame{fi}_faded_in.mp4"
                tasks.append((_fade_in, (str(out), str(faded), fd)))
                out = faded

            frame_paths.append(str(out))
            if t > 0:
                cut_timestamps.append(t)
            t += fd

    with ThreadPoolExecutor(max_workers=4) as ex:
        for f in as_completed([ex.submit(_run_frame_task, func, a) for func, a in tasks]):
            f.result()

    concat_file = OUTPUT_DIR / "concat_list.txt"
    with open(concat_file, "w") as f:
        for fp in frame_paths:
            f.write(f"file '{os.path.abspath(fp)}'\n")

    channel_slug = channel.lower().replace(" ", "_")
    raw_video = OUTPUT_DIR / f"{channel_slug}_raw.mp4"
    color_grade = cfg.get("color_grade", "")

    _run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "medium",
        "-crf", str(CRF), "-pix_fmt", "yuv420p",
        "-vf", f"fps={FPS}{',' + color_grade if color_grade else ''}",
        "-an",
        "-movflags", "+faststart",
        str(raw_video),
    ])

    total_dur = _get_duration(str(raw_video))

    master_audio = OUTPUT_DIR / f"{channel_slug}_master_audio.mp3"
    _build_audio_track(audio_files, scene_dur, cut_timestamps, channel, scenes, total_dur, master_audio)

    video_with_audio = OUTPUT_DIR / f"{channel_slug}_audiod.mp4"
    _run_ffmpeg([
        "-i", str(raw_video), "-i", str(master_audio),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-map", "0:v", "-map", "1:a",
        "-shortest", str(video_with_audio),
    ])

    if music_path and os.path.exists(music_path):
        mixed_path = OUTPUT_DIR / f"{channel_slug}_mixed.mp4"
        _mix_music(str(video_with_audio), str(music_path), str(mixed_path), total_dur)
        shutil.move(str(mixed_path), str(video_with_audio))

    subtitle_path = OUTPUT_DIR / f"{channel_slug}.ass"
    _generate_subtitles_ass(scenes, scene_dur, subtitle_path)

    output_path = OUTPUT_DIR / f"{channel_slug}_final.mp4"
    _run_ffmpeg([
        "-i", str(video_with_audio),
        "-vf", f"subtitles={subtitle_path}",
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "medium",
        "-crf", str(CRF), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ])

    shutil.rmtree(frames_dir)
    for p in [raw_video, master_audio, video_with_audio, concat_file, subtitle_path]:
        if p.exists():
            p.unlink()

    return str(output_path)


def _frame_durations(total, count):
    if total == 15:
        return [5.0, 5.0, 5.0]
    base = total / count
    return [total - base * (count - 1)] + [base] * (count - 1)


def _ken_burns_params(scene_idx, frame_idx):
    variants = ["zoom_in", "zoom_out", "pan_left"]
    return variants[(scene_idx + frame_idx) % 3]


def _make_video_frame(video_path, duration, out_path):
    _run_ffmpeg([
        "-i", str(video_path),
        "-vf", f"scale=w=1920:h=1080:force_original_aspect_ratio=1,pad=w=1920:h=1080:x=(ow-iw)/2:y=(oh-ih)/2:color=#14141e,fps={FPS}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration), "-an",
        "-preset", "fast",
        str(out_path),
    ])


def _make_ken_burns_frame(image_path, duration, ken_type, out_path):
    d = int(duration * FPS)
    if ken_type == "zoom_in":
        zoom = f"zoompan=z='min(1+0.04*on/{d},1.04)':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "zoom_out":
        zoom = f"zoompan=z='max(1.04-0.04*on/{d},1.0)':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "pan_left":
        zoom = f"zoompan=z='1.02':x='iw/2-(iw/zoom/2)+30*cos(PI*on/{d})':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "pan_right":
        zoom = f"zoompan=z='1.02':x='iw/2-(iw/zoom/2)-30*cos(PI*on/{d})':d={d}:s=1920x1080:fps={FPS}"
    else:
        zoom = f"zoompan=z='1':d={d}:s=1920x1080:fps={FPS}"

    _run_ffmpeg([
        "-loop", "1", "-i", str(image_path),
        "-vf", f"scale=w=1920:h=1080:force_original_aspect_ratio=1,pad=w=1920:h=1080:x=(ow-iw)/2:y=(oh-ih)/2:color=#14141e,{zoom}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration), "-an",
        "-preset", "fast",
        str(out_path),
    ])


def _make_still_frame(image_path, duration, out_path):
    _run_ffmpeg([
        "-loop", "1", "-i", str(image_path),
        "-vf", f"scale=w=1920:h=1080:force_original_aspect_ratio=1,pad=w=1920:h=1080:x=(ow-iw)/2:y=(oh-ih)/2:color=#14141e,fps={FPS}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration), "-an",
        "-preset", "fast",
        str(out_path),
    ])


def _fade_out(in_path, out_path, duration):
    fade_dur = min(0.5, duration * 0.5)
    start = max(0, duration - fade_dur)
    _run_ffmpeg([
        "-i", str(in_path),
        "-vf", f"fade=t=out:st={start}:d={fade_dur}:color=black",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast",
        str(out_path),
    ])


def _fade_in(in_path, out_path, duration):
    fade_dur = min(0.5, duration * 0.5)
    _run_ffmpeg([
        "-i", str(in_path),
        "-vf", f"fade=t=in:d={fade_dur}:color=black",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast",
        str(out_path),
    ])


def _make_color_frame(duration, out_path, color="14141e"):
    _run_ffmpeg([
        "-f", "lavfi", "-i", f"color=c={color}:s={RESOLUTION}:d={duration}:r={FPS}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast",
        str(out_path),
    ])


def _build_audio_track(audio_files, scene_dur, cut_timestamps, channel, scenes, total_dur, out_path):
    cfg = get_channel_config(channel)
    sfx_type = cfg.get("sfx", "boom")
    sfx_file = _generate_sfx_short(sfx_type)

    filter_parts = []
    audio_idx = 0
    valid_scenes_count = sum(1 for s in scenes if s.get("narration", "").strip())

    for ai in range(min(len(audio_files), valid_scenes_count)):
        af = audio_files[ai]
        offset = ai * scene_dur
        if af and os.path.exists(af) and os.path.getsize(af) > 0:
            filter_parts.append(
                f"[{audio_idx}:a]adelay={int(offset*1000)}|{int(offset*1000)}[a{audio_idx}]"
            )
            audio_idx += 1

    sfx_idx = audio_idx
    for ct in cut_timestamps:
        filter_parts.append(
            f"[{sfx_idx}:a]adelay={int(ct*1000)}|{int(ct*1000)}[sfx{sfx_idx}]"
        )
        sfx_idx += 1

    inputs = []
    for ai in range(min(len(audio_files), valid_scenes_count)):
        af = audio_files[ai]
        if af and os.path.exists(af) and os.path.getsize(af) > 0:
            inputs.extend(["-i", str(af)])

    for _ in cut_timestamps:
        inputs.extend(["-i", str(sfx_file)])

    if not filter_parts:
        _run_ffmpeg([
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(total_dur), str(out_path),
        ])
        return

    all_labels = [f"a{i}" for i in range(audio_idx)] + [f"sfx{i}" for i in range(audio_idx, sfx_idx)]
    mix_join = "".join(f"[{l}]" for l in all_labels)
    filter_complex = ";".join(filter_parts) + f";{mix_join}amix=inputs={len(all_labels)}:duration=first[aout]"

    _run_ffmpeg(inputs + [
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-ac", "2", "-ar", "44100",
        "-b:a", AUDIO_BITRATE,
        str(out_path),
    ])

    dur = _get_duration(str(out_path))
    if dur < total_dur:
        tmp_path = str(out_path).replace(".mp3", "_tmp.mp3")
        _run_ffmpeg([
            "-i", str(out_path),
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-filter_complex",
            f"[0:a][1:a]concat=n=2:v=0:a=1[a]",
            "-map", "[a]",
            "-ac", "2", "-ar", "44100",
            "-t", str(total_dur),
            tmp_path,
        ])
        shutil.move(tmp_path, str(out_path))


def _generate_sfx_short(sfx_type):
    sfx_file = OUTPUT_DIR / f"sfx_{sfx_type}.mp3"
    dur_map = {"boom": 0.4, "thud": 0.3, "static": 0.5}
    dur = dur_map.get(sfx_type, 0.3)
    if not sfx_file.exists():
        _run_ffmpeg([
            "-f", "lavfi", "-i",
            f"anoisesrc=d={dur}:c=brown:r=44100:a=0.5",
            str(sfx_file),
        ])
    return str(sfx_file)


def _generate_subtitles_ass(scenes, scene_dur, out_path):
    scene_keywords = set()
    for s in scenes:
        for kw in s.get("keywords", []):
            scene_keywords.add(kw.lower().strip())

    all_keywords = KEYWORDS | scene_keywords

    lines = [
        "[Script Info]",
        "; OpenMontage subtitles",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Montserrat ExtraBold,62,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,0,2,30,30,80,1",
        "Style: Keyword,Montserrat ExtraBold,62,&H0000D7FF,&H000000FF,&H00000000,&H00000000,0,0,0,0,105,105,0,0,1,4,0,2,30,30,80,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for si, scene in enumerate(scenes):
        narration = scene.get("narration", "").strip()
        if not narration:
            continue

        words = narration.split()
        if not words:
            continue

        offset = si * scene_dur
        time_per_word = scene_dur / len(words)

        char_width = 38
        space_width = 15
        line_y = 920
        max_line_width = 1800

        current_x = 50
        current_line_words = []
        current_line_width = 0
        all_ass_lines = []

        for wi, word in enumerate(words):
            word_clean = word.strip(".,!?;:\"'()[]{}")
            word_w = len(word) * char_width

            if current_line_width + word_w + space_width > max_line_width and current_line_words:
                all_ass_lines.append((current_line_words, current_x, offset))
                current_line_words = []
                current_x = 50
                current_line_width = 0
                line_y -= 60

            current_line_words.append((word, word_clean, word_w, wi))
            current_line_width += word_w + space_width

        if current_line_words:
            all_ass_lines.append((current_line_words, current_x, offset))

        for line_words, start_x, base_offset in all_ass_lines:
            cx = start_x
            for word, word_clean, w_w, wi in line_words:
                word_start = offset + wi * time_per_word
                word_end = offset + scene_dur

                is_keyword = word_clean.lower() in all_keywords
                style_name = "Keyword" if is_keyword else "Default"

                if is_keyword:
                    tag = f"{{\\fscx89\\fscy89\\t(0,80,\\fscx105\\fscy105)\\c&H00D7FF&}}{word}"
                else:
                    tag = f"{{\\fscx85\\fscy85\\t(0,80,\\fscx100\\fscy100)}}{word}"

                start_ts = _time_str(word_start)
                end_ts = _time_str(word_end)
                lines.append(
                    f"Dialogue: 0,{start_ts},{end_ts},{style_name},,0,0,0,,"
                    f"{{\\pos({int(cx)},{int(line_y)})}}{tag}"
                )
                cx += w_w + space_width

    out_path.write_text("\n".join(lines))


def _time_str(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _mix_music(video_path, music_path, out_path, dur):
    _run_ffmpeg([
        "-i", str(video_path), "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume=0.12,aloop=loop=-1:size={int(44100*dur)}[music];"
        f"[0:a][music]amix=inputs=2:duration=first[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-shortest", str(out_path),
    ])


def _run_ffmpeg(args):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
    subprocess.run(cmd, check=True, capture_output=True)


def _get_duration(video_path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, OSError):
        return 30.0
