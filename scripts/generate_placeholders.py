import json, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CHANNEL_COLORS = {
    "weirdhistory": {"bg": [(26, 10, 0), (59, 26, 0), (92, 46, 0), (139, 94, 60), (212, 160, 96)]},
    "crimeledger": {"bg": [(10, 15, 26), (0, 26, 46), (0, 61, 92), (46, 92, 110), (139, 160, 180)]},
    "mindtactics": {"bg": [(10, 10, 10), (26, 0, 0), (46, 0, 0), (92, 0, 0), (139, 0, 0)]},
}

W, H = 1920, 1080

def make_gradient(size, color_top, color_bot):
    img = Image.new("RGB", size)
    for y in range(size[1]):
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * y / size[1])
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * y / size[1])
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * y / size[1])
        for x in range(size[0]):
            img.putpixel((x, y), (r, g, b))
    return img

def place_text(draw, text, pos, font, fill):
    draw.text(pos, text, font=font, fill=fill)

def generate_photos(channel, scenes, out_dir):
    colors = CHANNEL_COLORS.get(channel, CHANNEL_COLORS["weirdhistory"])["bg"]
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        font_ch = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font_large = ImageFont.load_default()
        font_small = font_large
        font_ch = font_large

    for i, scene in enumerate(scenes):
        sid = scene.get("id", i + 1)
        prefix = f"s{i:03d}"
        p1 = out_dir / f"{prefix}_photo1.jpg"
        p2 = out_dir / f"{prefix}_photo2.jpg"
        if p1.exists() and p2.exists():
            continue
        c1 = colors[(i * 2) % len(colors)]
        c2 = colors[(i * 2 + 1) % len(colors)]
        c3 = colors[(i * 3) % len(colors)]
        title = scene.get("title", f"Scene {sid}")[:60]

        for idx, (p, ct, cb) in enumerate([(p1, c1, c2), (p2, c2, c3)]):
            if p.exists():
                continue
            img = make_gradient((W, H), ct, cb)
            draw = ImageDraw.Draw(img)
            place_text(draw, f"{channel.upper()}", (20, 20), font_ch, (255, 255, 255, 38))
            bbox = draw.textbbox((0, 0), f"Scene {sid}", font=font_large)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            place_text(draw, f"Scene {sid}", ((W - tw)//2, H//2 - th - 20), font_large, (255, 255, 255, 230))
            bbox2 = draw.textbbox((0, 0), title, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            place_text(draw, title, ((W - tw2)//2, H//2 + 40), font_small, (255, 255, 255, 180))
            img.save(str(p), "JPEG", quality=70)
            print(f"  {p.name} OK")

def generate_videos(channel, scenes, out_dir):
    colors = CHANNEL_COLORS.get(channel, CHANNEL_COLORS["weirdhistory"])["bg"]
    for i, scene in enumerate(scenes):
        sid = scene.get("id", i + 1)
        prefix = f"s{i:03d}"
        v = out_dir / f"{prefix}_video.mp4"
        if v.exists():
            continue
        c = colors[i % len(colors)]
        hex_c = f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={hex_c}:s={W}x{H}:d=5.2:r=30",
            "-vf", (
                f"drawtext=text='{channel.upper()}':"
                f"fontcolor=white@0.12:fontsize=28:x=20:y=20:"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf,"
                f"drawtext=text='Scene {sid}':"
                f"fontcolor=white@0.85:fontsize=72:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            ),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", str(v)
        ]
        subprocess.run(cmd, capture_output=True)
        if v.exists():
            print(f"  {v.name} OK")
        else:
            print(f"  {v.name} FAILED")

def main():
    for channel in ["weirdhistory", "crimeledger", "mindtactics"]:
        print(f"\n=== {channel} ===")
        sp = Path(f"projects/{channel}/script.json")
        if not sp.exists():
            print(f"  SKIP: no script.json")
            continue
        data = json.loads(sp.read_text())
        scenes = data.get("scenes", [])
        out_dir = Path(f"projects/{channel}/footage")
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"  {len(scenes)} scenes -> {out_dir}")
        generate_photos(channel, scenes, out_dir)
        generate_videos(channel, scenes, out_dir)
    print("\nDone generating placeholders")

if __name__ == "__main__":
    main()
