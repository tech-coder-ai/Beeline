"""Deterministic storyboard renderer (Pillow).

Not a substitute for a diffusion model - it exists so every downstream stage
(timeline, render, QC, publishing) can be built and tested on a laptop with
no GPU. It still honours the important contracts: same seed -> same image,
and each character keeps the same palette in every scene (continuity).
"""
from __future__ import annotations

import io
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.providers.images.base import ImageRequest

FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"), Path("/Library/Fonts")]

MOOD_SKIES = {
    "reflective": ("#2b3a67", "#e9b872"),
    "tense": ("#1f1d2b", "#7a3e48"),
    "joyful": ("#4fa3d1", "#ffe39f"),
    "peaceful": ("#7fb7be", "#f4e9cd"),
    "dramatic": ("#14213d", "#fca311"),
    "mysterious": ("#0f2027", "#2c5364"),
    "triumphant": ("#f7971e", "#ffd200"),
    "sad": ("#3a4750", "#9aa5b1"),
}
DEFAULT_SKIES = [("#355c7d", "#f8b195"), ("#2a5d67", "#f6e7b4"), ("#3d5a80", "#e0fbfc"), ("#5c4d7d", "#f2c6b4")]


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _gradient(w: int, h: int, top: str, bottom: str) -> Image.Image:
    t, b = _hex(top), _hex(bottom)
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        f = y / max(1, h - 1)
        px.line([(0, y), (w, y)], fill=tuple(int(t[i] + (b[i] - t[i]) * f) for i in range(3)))
    return img


def _sky_for(mood: str, rnd: random.Random) -> tuple[str, str]:
    for key, sky in MOOD_SKIES.items():
        if key in (mood or "").lower():
            return sky
    return rnd.choice(DEFAULT_SKIES)


def _figure(draw: ImageDraw.ImageDraw, cx: int, base_y: int, height: int, palette: list[str], label: str,
            view: str = "front") -> None:
    """A simple, recognisable character token: body + head + signature accent colour."""
    main = palette[0] if palette else "#888888"
    accent = palette[1] if len(palette) > 1 else "#dddddd"
    body_w = int(height * (0.42 if view == "front" else 0.3 if view == "side" else 0.36))
    head_r = int(height * 0.17)
    body_top = base_y - int(height * 0.62)
    draw.rounded_rectangle([cx - body_w // 2, body_top, cx + body_w // 2, base_y], radius=body_w // 3,
                           fill=main, outline="#1b1b1b", width=max(2, height // 90))
    hx = cx + (int(head_r * 0.35) if view == "three_quarter" else int(head_r * 0.55) if view == "side" else 0)
    draw.ellipse([hx - head_r, body_top - head_r * 2 + head_r // 3, hx + head_r, body_top + head_r // 3],
                 fill=accent, outline="#1b1b1b", width=max(2, height // 90))
    # signature accessory (pendant / badge) - the "continuity requirement" made visible
    s = max(4, height // 22)
    draw.ellipse([cx - s, body_top + height // 8, cx + s, body_top + height // 8 + 2 * s], fill=accent)
    f = _font(max(14, height // 7), bold=True)
    initial = (label[:1] or "?").upper()
    tw = draw.textlength(initial, font=f)
    draw.text((cx - tw / 2, body_top + height // 4), initial, fill="#ffffff", font=f,
              stroke_width=2, stroke_fill="#1b1b1b")


class PlaceholderImageProvider:
    name = "placeholder"
    model = "pillow-storyboard-v1"

    def generate(self, req: ImageRequest) -> bytes:
        img = self._character_sheet(req) if req.kind == "character_sheet" else self._scene(req)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def health(self) -> dict[str, Any]:
        return {"ok": True, "detail": "Pillow storyboard renderer (no GPU required)"}

    # ------------------------------------------------------------------ scenes
    def _scene(self, req: ImageRequest) -> Image.Image:
        h = req.hints
        rnd = random.Random(req.seed)
        w, ht = req.width, req.height
        top, bottom = _sky_for(h.get("mood", ""), rnd)
        img = _gradient(w, ht, top, bottom)
        draw = ImageDraw.Draw(img)
        # layered hills give a sense of place; location name seeds their shape
        loc_rnd = random.Random(h.get("location", "") or req.seed)
        for layer in range(3):
            y0 = int(ht * (0.55 + 0.1 * layer))
            pts = [(0, ht)]
            for x in range(0, w + 80, 80):
                pts.append((x, y0 + int(loc_rnd.uniform(-1, 1) * ht * 0.05)))
            pts.append((w, ht))
            shade = 70 - layer * 18
            base = _hex(bottom)
            draw.polygon(pts, fill=tuple(max(0, c - shade) for c in base))
        img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
        draw = ImageDraw.Draw(img)
        chars: list[dict] = h.get("characters", [])
        scale = {"close_up": 0.62, "medium": 0.48, "over_shoulder": 0.5}.get(h.get("shot_type", ""), 0.36)
        fig_h = int(ht * scale)
        n = max(1, len(chars))
        for i, c in enumerate(chars):
            cx = int(w * (i + 1) / (n + 1))
            _figure(draw, cx, int(ht * 0.78), fig_h, c.get("palette", []), c.get("name", "?"),
                    view="three_quarter" if i % 2 else "front")
            nf = _font(max(14, ht // 34), bold=True)
            name = c.get("name", "")
            draw.text((cx - draw.textlength(name, font=nf) / 2, int(ht * 0.795)), name, fill="#ffffff",
                      font=nf, stroke_width=2, stroke_fill="#000000")
        # caption plate
        tf, sf = _font(max(16, ht // 22), bold=True), _font(max(12, ht // 40))
        title = h.get("title") or f"Scene {h.get('sequence', '')}"
        pad = ht // 40
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle([pad, pad, pad + int(w * 0.55), pad + ht // 7], radius=pad, fill=(0, 0, 0, 110))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((pad * 2, pad + pad // 2), title[:48], fill="#ffffff", font=tf)
        draw.text((pad * 2, pad + pad // 2 + int(tf.size * 1.3)), f"{h.get('location', '')}  ·  {h.get('mood', '')}"[:70],
                  fill="#e8e8e8", font=sf)
        tag = "placeholder art"
        draw.text((w - pad - draw.textlength(tag, font=sf), pad), tag, fill="#ffffffaa", font=sf)
        return img

    # --------------------------------------------------------- character sheet
    def _character_sheet(self, req: ImageRequest) -> Image.Image:
        h = req.hints
        w, ht = req.width, req.height
        img = _gradient(w, ht, "#f5f1e8", "#e4ddcc")
        draw = ImageDraw.Draw(img)
        palette = h.get("palette") or ["#888888", "#dddddd"]
        name = h.get("name", "Character")
        tf, sf = _font(max(20, ht // 14), bold=True), _font(max(12, ht // 34))
        draw.text((ht // 20, ht // 24), name, fill="#222222", font=tf)
        draw.text((ht // 20, ht // 24 + int(tf.size * 1.25)), f"{h.get('role', '')} · {h.get('species', '')}"[:80],
                  fill="#555555", font=sf)
        views = [("front", "FRONT"), ("three_quarter", "3/4"), ("side", "SIDE")]
        fig_h = int(ht * 0.55)
        for i, (view, label) in enumerate(views):
            cx = int(w * (0.14 + 0.18 * i))
            _figure(draw, cx, int(ht * 0.86), fig_h, palette, name, view=view)
            draw.text((cx - draw.textlength(label, font=sf) / 2, int(ht * 0.89)), label, fill="#444444", font=sf)
        # palette + stable features panel
        x0 = int(w * 0.62)
        draw.text((x0, int(ht * 0.25)), "Palette", fill="#222222", font=sf)
        for i, col in enumerate(palette[:4]):
            draw.rounded_rectangle([x0 + i * (ht // 8), int(ht * 0.31), x0 + i * (ht // 8) + ht // 10, int(ht * 0.31) + ht // 10],
                                   radius=6, fill=col, outline="#333333")
        draw.text((x0, int(ht * 0.48)), "Stable features", fill="#222222", font=sf)
        for i, feat in enumerate((h.get("features") or [])[:6]):
            draw.text((x0, int(ht * 0.54) + i * int(sf.size * 1.5)), f"• {feat}"[:46], fill="#333333", font=sf)
        tag = "placeholder art"
        draw.text((w - ht // 20 - draw.textlength(tag, font=sf), ht // 24), tag, fill="#999999", font=sf)
        return img
