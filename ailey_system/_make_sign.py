#!/usr/bin/env python3
"""Generate a transparent Ailey signature PNG for blog image overlays."""
from PIL import Image, ImageDraw, ImageFont
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "ailey_sign.png")

w, h = 220, 70
img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 40)
except Exception:
    font = ImageFont.load_default()

txt = "A\u0021LEY"  # A!LEY using unicode escape

# Pink glow (shadow layers)
for dx in (-2, -1, 0, 1, 2):
    for dy in (-2, -1, 0, 1, 2):
        if abs(dx) + abs(dy) > 0:
            draw.text((12 + dx, 12 + dy), txt, fill=(255, 20, 147, 80), font=font)

# Main text in hot pink
draw.text((12, 12), txt, fill=(255, 105, 180, 240), font=font)

# Tiny sparkle dots
for cx, cy, r, alpha in [(180, 15, 3, 200), (190, 35, 2, 160), (200, 20, 2, 180)]:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 182, 193, alpha))

# Underline swash
draw.line([(14, 56), (160, 52)], fill=(255, 20, 147, 120), width=2)

img.save(OUT)
print(f"Ailey sign saved: {OUT} ({img.size})")
