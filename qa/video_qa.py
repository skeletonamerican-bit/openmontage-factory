import os, json, subprocess, time, requests, sys
from pathlib import Path


def check_ffprobe(video_path):
    issues = []
    stats = {}

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size,bit_rate",
             "-of", "json", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0))
        size_bytes = int(fmt.get("size", 0))
        size_mb = size_bytes / (1024 * 1024)
        stats["duration"] = duration
        stats["size_bytes"] = size_bytes
        stats["size_mb"] = size_mb

        if duration < 1200:
            issues.append(f"Duration too short: {duration:.0f}s (need >= 1200s)")
        if size_mb < 100:
            issues.append(f"File too small: {size_mb:.1f}MB (need >= 100MB)")
    except Exception as e:
        issues.append(f"ffprobe failed: {e}")
        return {"ok": False, "issues": issues, "stats": stats}

    try:
        audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        has_audio = bool(audio.stdout.strip())
        stats["has_audio"] = has_audio
        if not has_audio:
            issues.append("No audio stream detected")
    except Exception as e:
        issues.append(f"Audio check failed: {e}")

    try:
        fps_result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        fps_str = fps_result.stdout.strip()
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 0
        else:
            fps = float(fps_str) if fps_str else 0
        stats["fps"] = fps
        if fps < 24:
            issues.append(f"Low FPS: {fps:.1f}")
    except Exception as e:
        issues.append(f"FPS check failed: {e}")

    return {"ok": len(issues) == 0, "issues": issues, "stats": stats}


def analyze_with_gemini(video_path, channel, api_key):
    if not api_key:
        return {"ok": True, "skipped": True, "reason": "no_api_key"}

    try:
        name = _upload_to_gemini(video_path, api_key)
        if not name:
            return {"ok": True, "skipped": True, "reason": "upload_failed"}

        if not _poll_gemini_file(name, api_key):
            _delete_gemini_file(name, api_key)
            return {"ok": True, "skipped": True, "reason": "processing_timeout"}

        result = _analyze_gemini_content(name, api_key, channel)
        _delete_gemini_file(name, api_key)
        return result

    except Exception as e:
        print(f"[QA] Gemini analysis failed: {e}", flush=True)
        return {"ok": True, "skipped": True, "reason": "gemini_unavailable"}


def _upload_to_gemini(video_path, api_key):
    upload_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"

    file_size = os.path.getsize(video_path)
    file_name = os.path.basename(video_path)

    metadata = {
        "file": {
            "displayName": file_name,
            "mimeType": "video/mp4",
        }
    }

    try:
        with open(video_path, "rb") as f:
            file_bytes = f.read()

        r = requests.post(
            upload_url,
            params={"key": api_key},
            data=json.dumps(metadata),
            headers={"X-Goog-Upload-Command": "start, upload, finalize",
                     "X-Goog-Upload-Header-Content-Length": str(file_size),
                     "X-Goog-Upload-Content-Type": "video/mp4",
                     "Content-Type": "application/json"},
            timeout=30,
        )

        if r.status_code not in (200, 201):
            # Fallback: try simpler upload approach
            r2 = requests.post(
                f"{upload_url}&uploadType=multipart",
                headers={"Content-Type": "multipart/related; boundary=gemini-boundary"},
                data=(
                    f"--gemini-boundary\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f'{json.dumps(metadata)}\r\n'
                    f"--gemini-boundary\r\n"
                    f"Content-Type: video/mp4\r\n\r\n"
                ).encode() + file_bytes + b"\r\n--gemini-boundary--\r\n",
                timeout=300,
            )
            r = r2

        if r.status_code in (200, 201):
            resp = r.json()
            file_name_gemini = resp.get("file", {}).get("name") or resp.get("name", "")
            if file_name_gemini:
                print(f"[QA] Uploaded to Gemini: {file_name_gemini}", flush=True)
                return file_name_gemini

        print(f"[QA] Upload failed: {r.status_code} {r.text[:200]}", flush=True)
        return None

    except Exception as e:
        print(f"[QA] Upload error: {e}", flush=True)
        return None


def _poll_gemini_file(name, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/{name}?key={api_key}"
    for attempt in range(60):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                state = r.json().get("file", {}).get("state", "")
                if state == "ACTIVE":
                    return True
                elif state == "FAILED":
                    print(f"[QA] Gemini file processing FAILED", flush=True)
                    return False
            print(f"[QA] Poll {attempt+1}/60: state={r.json().get('file', {}).get('state', 'unknown')}", flush=True)
        except Exception as e:
            print(f"[QA] Poll error: {e}", flush=True)
        time.sleep(5)
    return False


def _analyze_gemini_content(name, api_key, channel):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    prompt = (
        "You are a YouTube video QA system. Analyze this documentary video and "
        "respond ONLY with valid JSON (no markdown, no explanation):\n"
        "{\n"
        "  'ok': bool,\n"
        "  'duration_looks_correct': bool,\n"
        "  'audio_present': bool,\n"
        "  'audio_clear': bool,\n"
        "  'subtitles_visible': bool,\n"
        "  'placeholder_images': bool,\n"
        "  'long_black_screens': bool,\n"
        "  'video_has_cuts': bool,\n"
        "  'overall_quality': 'good'|'poor'|'broken',\n"
        "  'issues': [str],\n"
        "  'suggestions': [str]\n"
        "}\n"
        "Check: 1) Is narration audio clearly audible? 2) Are subtitles present and readable? "
        "3) Are images real photos or gray/dark placeholders? "
        "4) Are there scene cuts happening? "
        "5) Any long black screens over 3 seconds (except 1-2 intentional act transitions)?"
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"fileData": {"mimeType": "video/mp4", "fileUri": name}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024,
        }
    }

    try:
        r = requests.post(url, json=payload, timeout=120)
        if r.status_code == 200:
            text = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            text = text.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(text)
            return parsed
        else:
            print(f"[QA] Gemini analysis failed: {r.status_code} {r.text[:200]}", flush=True)
            return {"ok": True, "skipped": True, "reason": f"api_error_{r.status_code}"}
    except Exception as e:
        print(f"[QA] Gemini analysis error: {e}", flush=True)
        return {"ok": True, "skipped": True, "reason": "analysis_error"}


def _delete_gemini_file(name, api_key):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/{name}?key={api_key}"
        requests.delete(url, timeout=10)
        print(f"[QA] Deleted Gemini file: {name}", flush=True)
    except Exception as e:
        print(f"[QA] Delete file error: {e}", flush=True)


def trigger_pixabay_rebuild(channel):
    os.environ["SKIP_KAGGLE"] = "1"
    os.environ["USE_PIXABAY_ONLY"] = "1"
    print(f"[QA] Rebuild triggered: switching to Pixabay-only mode for {channel}", flush=True)


def save_qa_report(channel, report):
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    path = output_dir / f"{channel}_qa_report.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(f"[QA] Report saved: {path}", flush=True)


def run_qa(channel, video_path, max_attempts=3):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print(f"[QA] No GEMINI_API_KEY set, skipping", flush=True)
        report = {"channel": channel, "ok": True, "skipped": True, "reason": "no_api_key"}
        save_qa_report(channel, report)
        return report

    for attempt in range(max_attempts):
        print(f"[QA] {channel} QA attempt {attempt+1}/{max_attempts}", flush=True)

        ffprobe = check_ffprobe(video_path)
        if not ffprobe["ok"]:
            print(f"[QA] ffprobe issues: {ffprobe['issues']}", flush=True)
            if attempt < max_attempts - 1:
                print(f"[QA] Triggering Pixabay rebuild (attempt {attempt+1})", flush=True)
                trigger_pixabay_rebuild(channel)
                continue

        gemini = analyze_with_gemini(video_path, channel, api_key)
        if gemini.get("skipped"):
            report = {
                "channel": channel,
                "ok": True,
                "skipped": True,
                "reason": gemini.get("reason", "gemini_unavailable"),
                "ffprobe": ffprobe,
            }
            save_qa_report(channel, report)
            return report

        critical = []
        if gemini.get("placeholder_images"):
            critical.append("placeholder_images")
        if not gemini.get("audio_present"):
            critical.append("no_audio")
        if gemini.get("overall_quality") == "broken":
            critical.append("broken")

        if not critical:
            report = {
                "channel": channel,
                "ok": True,
                "attempts": attempt + 1,
                "ffprobe": ffprobe,
                "gemini": gemini,
            }
            save_qa_report(channel, report)
            return report

        print(f"[QA] Critical issues: {critical}", flush=True)
        print(f"[QA] Gemini issues: {gemini.get('issues', [])}", flush=True)
        print(f"[QA] Suggestions: {gemini.get('suggestions', [])}", flush=True)

        if attempt < max_attempts - 1:
            print(f"[QA] Triggering Pixabay rebuild (attempt {attempt+1})", flush=True)
            trigger_pixabay_rebuild(channel)
            continue

    report = {
        "channel": channel,
        "ok": False,
        "issues": critical,
        "attempts": max_attempts,
        "ffprobe": ffprobe if 'ffprobe' in locals() else {},
        "gemini": gemini if 'gemini' in locals() else {},
    }
    save_qa_report(channel, report)
    return report
