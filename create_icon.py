"""Generate Hermes app icon."""
from PIL import Image, ImageDraw, ImageFont
import sys

sizes = [16, 32, 48, 64, 128, 256]
images = []

for sz in sizes:
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, sz // 16)
    d.rounded_rectangle([pad, pad, sz - pad, sz - pad], radius=sz // 6, fill=(124, 58, 237), outline=(167, 139, 250), width=max(1, sz // 32))
    font_size = sz // 2
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), "H", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((sz - tw) / 2, (sz - th) / 2 - sz // 10), "H", fill=(255, 255, 255), font=font)
    images.append(img)

out = sys.argv[1] if len(sys.argv) > 1 else "hermes.ico"
images[0].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
print(f"Icon saved: {out}")
