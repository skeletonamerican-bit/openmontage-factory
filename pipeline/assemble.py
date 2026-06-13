import os, json, subprocess, math, shutil, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import get_channel_config, SCENE_DUR, PHOTO_DUR, VIDEO_DUR, FPS, RESOLUTION, CRF, AUDIO_BITRATE, TEST_MODE, PHOTO_COUNT, CROSSFADE, retry, Timer, MIN_VIDEO_SIZE_MB, THUMBNAIL_FRAME

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

KEN_BURNS_VARIANTS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "zoom_in_slow", "zoom_out_slow"]


def _validate_inputs(inputs, context=""):
    for f in inputs:
        if not f:
            continue
        if not os.path.exists(str(f)):
            raise FileNotFoundError(f"{context}: Missing input file: {f}")
        if os.path.getsize(str(f)) == 0:
            raise ValueError(f"{context}: Empty input file: {f}")


def assemble_video(channel, script, assets, tts):
    cfg = get_channel_config(channel)
    scenes = script if isinstance(script, list) else script.get("scenes", script)
    audio_files = tts.get("audio_files", [])
    scene_assets = assets.get("scene_assets", {})
    music_path = assets.get("music")

    is_test = bool(TEST_MODE)
    scene_dur = 8 if is_test else SCENE_DUR

    # Validate audio files exist and are non-empty
    audio_files = [f for f in audio_files if f and os.path.exists(f) and os.path.getsize(f) > 1000]

    n = len(scenes)
    last_act_scene = n // 3 - 1
    second_act_scene = 2 * n // 3 - 1
    last_scene = n - 1

    frames_dir = OUTPUT_DIR / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    with Timer(f"[{channel}] Frame generation"):
        frame_paths = []
        cut_timestamps = []
        t = 0.0

        for si in range(n):
            sa = scene_assets.get(si, {})
            photos = sa.get("photos", [])
            # Validate photos exist
            photos = [p for p in photos if p and os.path.exists(p) and os.path.getsize(p) > 1000]
            vid_path = sa.get("video") if sa.get("video") and os.path.exists(sa["video"]) and os.path.getsize(sa["video"]) > 1000 else None

            frame_count = PHOTO_COUNT
            frame_durs = _frame_durations(scene_dur, frame_count)

            for fi in range(frame_count):
                fd = frame_durs[fi]
                out = frames_dir / f"scene_{si:03d}_frame{fi}.mp4"

                ken_type = _ken_burns_params(si, fi, frame_count)

                if fi == 0 and vid_path:
                    _make_video_frame(vid_path, fd, out)
                elif fi < len(photos):
                    _make_ken_burns_frame(photos[fi], fd, ken_type, out)
                else:
                    _make_color_frame(fd, out, narration=scenes[si].get("narration", ""))

                _validate_inputs([out], f"frame scene_{si}_frame{fi}")

                is_last = (si in (last_act_scene, second_act_scene, last_scene)) and fi == frame_count - 1
                if is_last:
                    faded = frames_dir / f"scene_{si:03d}_frame{fi}_faded.mp4"
                    _fade_out(str(out), str(faded), fd)
                    out = faded

                is_first = (si in (last_act_scene + 1, second_act_scene + 1)) and fi == 0
                if is_first:
                    faded = frames_dir / f"scene_{si:03d}_frame{fi}_faded_in.mp4"
                    _fade_in(str(out), str(faded), fd)
                    out = faded

                frame_paths.append(str(out))
                if t > 0:
                    cut_timestamps.append(t)
                t += fd

    _validate_inputs(frame_paths, "frame_paths")

    concat_file = OUTPUT_DIR / "concat_list.txt"
    with open(concat_file, "w") as f:
        for fp in frame_paths:
            f.write(f"file '{os.path.abspath(fp)}'\n")

    channel_slug = channel.lower().replace(" ", "_")
    raw_video = OUTPUT_DIR / f"{channel_slug}_raw.mp4"
    color_grade = cfg.get("color_grade", "")

    vf_parts = [f"fps={FPS}"]
    if color_grade:
        vf_parts.append(color_grade)

    with Timer(f"[{channel}] Video encode"):
        _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "medium",
            "-crf", str(CRF), "-pix_fmt", "yuv420p",
            "-vf", ",".join(vf_parts),
            "-an",
            "-movflags", "+faststart",
            str(raw_video),
        ])

    _validate_inputs([raw_video], "raw_video")
    total_dur = _get_duration(str(raw_video))

    with Timer(f"[{channel}] Audio build"):
        master_audio = OUTPUT_DIR / f"{channel_slug}_master_audio.mp3"
        _build_audio_track(audio_files, scene_dur, cut_timestamps, channel, scenes, total_dur, master_audio)

    _validate_inputs([master_audio], "master_audio")

    video_with_audio = OUTPUT_DIR / f"{channel_slug}_audiod.mp4"
    _validate_inputs([raw_video, master_audio], "video+audio mux")
    _run_ffmpeg([
        "-i", str(raw_video), "-i", str(master_audio),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-map", "0:v", "-map", "1:a",
        "-shortest", str(video_with_audio),
    ])

    _validate_inputs([video_with_audio], "video_with_audio")

    if music_path and os.path.exists(music_path) and os.path.getsize(music_path) > 100:
        mixed_path = OUTPUT_DIR / f"{channel_slug}_mixed.mp4"
        _mix_music(str(video_with_audio), str(music_path), str(mixed_path), total_dur)
        shutil.move(str(mixed_path), str(video_with_audio))

    subtitle_path = OUTPUT_DIR / f"{channel_slug}.ass"
    with Timer(f"[{channel}] Subtitles"):
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

    # Validate output
    if not _validate_mp4(output_path, channel):
        raise RuntimeError(f"[{channel}] Final video validation failed: under {MIN_VIDEO_SIZE_MB}MB")

    # Thumbnail extraction
    thumbnail_path = _extract_thumbnail(output_path, channel, channel_slug)

    # Stats
    ai_video_count = sum(
        1 for si in range(n)
        for fi in range(PHOTO_COUNT)
        if fi == 0 and scene_assets.get(si, {}).get("video") and os.path.exists(scene_assets[si]["video"])
    )
    ken_burns_count = n * PHOTO_COUNT - ai_video_count
    stats = {
        "duration": total_dur,
        "size_mb": output_path.stat().st_size / (1024 * 1024),
        "scenes": n,
        "ai_video_count": ai_video_count,
        "ken_burns_count": ken_burns_count,
    }

    shutil.rmtree(frames_dir)
    for p in [raw_video, master_audio, video_with_audio, concat_file, subtitle_path]:
        if p.exists():
            p.unlink()

    return str(output_path), thumbnail_path, stats


def _validate_mp4(filepath, channel):
    if not filepath.exists():
        print(f"[{channel}] MP4 file not found!", flush=True)
        return False
    size_mb = filepath.stat().st_size / (1024 * 1024)
    min_size = 1 if TEST_MODE else MIN_VIDEO_SIZE_MB
    print(f"[{channel}] Final video size: {size_mb:.1f}MB", flush=True)
    if size_mb < min_size:
        print(f"[{channel}] WARNING: video size {size_mb:.1f}MB < {min_size}MB minimum", flush=True)
        return False
    return True


def _extract_thumbnail(video_path, channel, channel_slug):
    thumbnail_path = OUTPUT_DIR / f"{channel_slug}_thumbnail.jpg"
    _run_ffmpeg([
        "-i", str(video_path),
        "-vf", f"select=eq(n\\,{THUMBNAIL_FRAME})",
        "-frames:v", "1",
        str(thumbnail_path),
    ])
    if thumbnail_path.exists():
        print(f"[{channel}] Thumbnail saved: {thumbnail_path}", flush=True)
    else:
        print(f"[{channel}] Thumbnail extraction failed, using fallback", flush=True)
        _run_ffmpeg([
            "-i", str(video_path),
            "-ss", "00:00:03",
            "-vframes", "1",
            str(thumbnail_path),
        ])
    return str(thumbnail_path) if thumbnail_path.exists() else None


def _frame_durations(total, count):
    if total == 15:
        return [5.0, 5.0, 5.0]
    base = total / count
    return [total - base * (count - 1)] + [base] * (count - 1)


def _ken_burns_params(scene_idx, frame_idx, frame_count):
    idx = (scene_idx * frame_count + frame_idx) % len(KEN_BURNS_VARIANTS)
    return KEN_BURNS_VARIANTS[idx]


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
        zoom = f"zoompan=z='min(1+0.5*on/{d},1.15)':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "zoom_out":
        zoom = f"zoompan=z='max(1.15-0.5*on/{d},1.0)':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "zoom_in_slow":
        zoom = f"zoompan=z='min(1+0.4*on/{d},1.12)':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "zoom_out_slow":
        zoom = f"zoompan=z='max(1.12-0.4*on/{d},1.0)':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "pan_left":
        zoom = f"zoompan=z='1.05':x='iw/2-(iw/zoom/2)+120*sin(PI*on/{d})':d={d}:s=1920x1080:fps={FPS}"
    elif ken_type == "pan_right":
        zoom = f"zoompan=z='1.05':x='iw/2-(iw/zoom/2)-120*sin(PI*on/{d})':d={d}:s=1920x1080:fps={FPS}"
    else:
        zoom = f"zoompan=z='1.05':x='iw/2-(iw/zoom/2)+60*cos(2*PI*on/{d})':d={d}:s=1920x1080:fps={FPS}"

    _run_ffmpeg([
        "-loop", "1", "-i", str(image_path),
        "-vf", f"scale=w=1920:h=1080:force_original_aspect_ratio=1,pad=w=1920:h=1080:x=(ow-iw)/2:y=(oh-ih)/2:color=#14141e,{zoom}",
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


def _escape_drawtext(text):
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace(",", "\\,")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace(";", "\\;")
    text = text.replace("!", "\\!")
    return text


def _make_color_frame(duration, out_path, narration=""):
    base_color = "14141e"
    r = int(base_color[0:2], 16)
    g = int(base_color[2:4], 16)
    b = int(base_color[4:6], 16)

    vf = (
        f"geq=r='{r}+20*random(1)':g='{g}+20*random(1)':b='{b}+30*random(1)'"
        f",fps={FPS},scale={RESOLUTION}"
    )

    if narration:
        escaped = _escape_drawtext(narration)
        vf += (
            f",drawtext=text='{escaped}':fontsize=36:fontcolor=white@0.9:"
            f"x=(w-text_w)/2:y=h-th-60:box=1:boxcolor=black@0.5:boxborderw=10"
        )

    _run_ffmpeg([
        "-f", "lavfi", "-i", f"color=c=#{base_color}:s={RESOLUTION}:d={duration}:r={FPS}",
        "-vf", vf,
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

    # Only use valid audio files
    valid_audio = [af for af in audio_files[:valid_scenes_count]
                   if af and os.path.exists(af) and os.path.getsize(af) > 1000]

    for ai, af in enumerate(valid_audio):
        offset = ai * scene_dur
        filter_parts.append(
            f"[{audio_idx}:a]adelay={int(offset*1000)}|{int(offset*1000)}[a{audio_idx}]"
        )
        audio_idx += 1

    sfx_idx = audio_idx
    # Add SFX only if sfx_file is valid
    if sfx_file and os.path.exists(sfx_file) and os.path.getsize(sfx_file) > 100:
        for ct in cut_timestamps:
            filter_parts.append(
                f"[{sfx_idx}:a]adelay={int(ct*1000)}|{int(ct*1000)}[sfx{sfx_idx}]"
            )
            sfx_idx += 1

    inputs = []
    for af in valid_audio:
        inputs.extend(["-i", str(af)])

    if sfx_file and os.path.exists(sfx_file) and os.path.getsize(sfx_file) > 100:
        for _ in cut_timestamps:
            inputs.extend(["-i", str(sfx_file)])

    if not filter_parts:
        # No audio at all — generate silence
        _run_ffmpeg([
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(total_dur), str(out_path),
        ])
        return

    all_labels = [f"a{i}" for i in range(audio_idx)] + [f"sfx{i}" for i in range(audio_idx, sfx_idx)]
    if not all_labels:
        _run_ffmpeg([
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(total_dur), str(out_path),
        ])
        return

    mix_join = "".join(f"[{l}]" for l in all_labels)
    filter_complex = ";".join(filter_parts) + f";{mix_join}amix=inputs={len(all_labels)}:duration=first,loudnorm=I=-16:TP=-1:LRA=7[aout]"

    _run_ffmpeg(inputs + [
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-ac", "2", "-ar", "44100",
        "-b:a", AUDIO_BITRATE,
        str(out_path),
    ])

    _validate_inputs([out_path], "audio_track")
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
    if not sfx_file.exists() or os.path.getsize(sfx_file) < 100:
        _run_ffmpeg([
            "-f", "lavfi", "-i",
            f"anoisesrc=d={dur}:c=brown:r=44100:a=0.5",
            str(sfx_file),
        ])
        if not sfx_file.exists() or os.path.getsize(sfx_file) < 100:
            print(f"WARNING: Failed to create SFX {sfx_type}, skipping")
            return None
    return str(sfx_file)


def _generate_subtitles_ass(scenes, scene_dur, out_path):
    scene_keywords = set()
    for s in scenes:
        for kw in s.get("keywords", []):
            scene_keywords.add(kw.lower().strip())

    all_keywords = KEYWORDS | scene_keywords

    montserrat_font = "Montserrat ExtraBold"
    if os.path.exists(FONT_PATH):
        montserrat_font = FONT_PATH

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
        f"Style: Default,{montserrat_font},62,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,0,2,30,30,80,1",
        f"Style: Keyword,{montserrat_font},62,&H0000D7FF,&H000000FF,&H00000000,&H00000000,0,0,0,0,105,105,0,0,1,4,0,2,30,30,80,1",
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


@retry(max_attempts=2, delay=3)
def _run_ffmpeg(args):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
    result = subprocess.run(cmd, check=True, capture_output=True)
    return result


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
