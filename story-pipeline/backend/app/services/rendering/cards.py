"""Title and end cards: typography over a blurred, darkened frame from the story itself."""
from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.providers.images.placeholder import _font


def _backdrop(image_path: Path, w: int, h: int, darken: float) -> Image.Image:
    img = Image.open(image_path).convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    img = img.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(radius=max(6, w // 90)))
    return Image.blend(img, Image.new("RGB", (w, h), (8, 10, 14)), darken)


def _centered(d: ImageDraw.ImageDraw, y: int, text: str, font, w: int, fill: str, spacing: float = 1.25) -> int:
    for line in text.splitlines():
        tw = d.textlength(line, font=font)
        d.text(((w - tw) / 2, y), line, font=font, fill=fill)
        y += int(font.size * spacing)
    return y


def _spaced(text: str) -> str:
    return " ".join(text.upper())  # letter-spaced eyebrow label


def title_card(image_path: Path, title: str, eyebrow: str, w: int, h: int) -> bytes:
    img = _backdrop(image_path, w, h, 0.55)
    d = ImageDraw.Draw(img)
    eb, tf = _font(max(12, h // 42), bold=True), _font(max(28, h // 11), bold=True)
    lines = "\n".join(textwrap.wrap(title, 22)[:3])
    block = int(eb.size * 2.2) + lines.count("\n") * int(tf.size * 1.15) + tf.size
    y = (h - block) // 2
    y = _centered(d, y, _spaced(eyebrow), eb, w, "#e8c77a")
    rule = w // 14
    d.line([((w - rule) / 2, y + eb.size // 3), ((w + rule) / 2, y + eb.size // 3)], fill="#e8c77a", width=max(2, h // 360))
    _centered(d, y + int(eb.size * 1.2), lines, tf, w, "#ffffff", 1.15)
    return _png(img)


def end_card(image_path: Path, moral: str, credit: str, w: int, h: int) -> bytes:
    img = _backdrop(image_path, w, h, 0.65)
    d = ImageDraw.Draw(img)
    tf, mf, cf = _font(max(26, h // 12), bold=True), _font(max(14, h // 30)), _font(max(10, h // 54))
    y = int(h * 0.36) if moral else int(h * 0.42)
    y = _centered(d, y, "The End", tf, w, "#ffffff")
    if moral:
        y = _centered(d, y + h // 40, "\n".join(textwrap.wrap(f"“{moral}”", 48)[:3]), mf, w, "#e8c77a", 1.35)
    _centered(d, h - int(h * 0.12), "\n".join(textwrap.wrap(credit, 90)[:2]), cf, w, "#b9c0c8", 1.4)
    return _png(img)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
