"""Thumbnail: the most populated scene image, cover-cropped to 1280x720, with the localized title."""
from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from app.providers.images.placeholder import _font


def make_thumbnail(image_path: Path, title: str, width: int = 1280, height: int = 720) -> bytes:
    img = Image.open(image_path).convert("RGB")
    scale = max(width / img.width, height / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    img = img.crop((left, top, left + width, top + height))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(height // 2, height):  # bottom gradient for legibility
        a = int(200 * (y - height / 2) / (height / 2))
        od.line([(0, y), (width, y)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    font = _font(64, bold=True)
    lines = textwrap.wrap(title.split(" | ")[0], 28)[:3]  # main title only; suffixes are for search, not thumbnails
    y = height - 56 - len(lines) * 76
    for line in lines:
        d.text((60, y), line, font=font, fill="#ffffff", stroke_width=4, stroke_fill="#000000")
        y += 76
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()
