"""
Image Stamping for Ailey Blog Posts
====================================
Adds Ailey's signature (bottom-right) and blog title (top-left)
to generated images AFTER mflux generation.

mflux should NOT render any text — this module handles all text overlay
using PIL with proper readability (dark semi-transparent background strips).
"""

import os
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

_DIR = os.path.dirname(os.path.abspath(__file__))
_SIGN_PATH = os.path.join(_DIR, "ailey_sign.png")

# Font preferences (in order of priority)
_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
]

# Sign dimensions relative to image width
_SIGN_MAX_WIDTH_RATIO = 0.18   # sign max 18% of image width
_SIGN_MARGIN = 16              # px from edge

# Title bar config
_TITLE_FONT_SIZE_RATIO = 0.035  # font size as ratio of image width
_TITLE_MIN_FONT = 18
_TITLE_MAX_FONT = 48
_TITLE_PADDING_X = 20
_TITLE_PADDING_Y = 10
_TITLE_MAX_CHARS = 60
_TITLE_MAX_LINE_CHARS = 35  # Wrap long titles to multiple lines


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load the best available bold font at the given size."""
    for path in _FONT_PATHS:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _load_sign() -> Optional[Image.Image]:
    """Load the Ailey signature PNG (RGBA)."""
    if os.path.isfile(_SIGN_PATH):
        try:
            return Image.open(_SIGN_PATH).convert("RGBA")
        except Exception:
            pass
    return None


def _truncate_title(title: str, max_chars: int = _TITLE_MAX_CHARS) -> str:
    """Truncate title to max_chars, adding ellipsis if needed."""
    title = title.strip()
    if len(title) <= max_chars:
        return title
    return title[: max_chars - 1].rstrip() + "…"


def _wrap_title(title: str, max_line_chars: int = _TITLE_MAX_LINE_CHARS) -> list:
    """Wrap a title into multiple lines, breaking at word boundaries.
    
    Returns a list of lines. Truncates the overall title first.
    """
    title = _truncate_title(title)
    if len(title) <= max_line_chars:
        return [title]
    
    words = title.split()
    lines = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip() if current_line else word
        if len(test) <= max_line_chars:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    
    # Cap at 3 lines max
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1][:max_line_chars - 1].rstrip() + "…"
    
    return lines


def stamp_blog_image(
    image_path: str,
    blog_title: str,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Stamp a blog image with:
    - Top-left: Blog title on a semi-transparent dark strip
    - Bottom-right: Ailey signature (A!LEY) logo

    The image is modified IN-PLACE unless output_path is given.

    Args:
        image_path: Path to the generated PNG image
        blog_title: The blog post title to overlay
        output_path: Optional different output path (default: overwrite)

    Returns:
        Path to the stamped image, or None on failure
    """
    if not os.path.isfile(image_path):
        print(f"[ImageStamp] ❌ Image not found: {image_path}")
        return None

    if not output_path:
        output_path = image_path

    try:
        # Open as RGBA for compositing
        img = Image.open(image_path).convert("RGBA")
        img_w, img_h = img.size

        # Create overlay layer
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # ── 1. Title bar (top-left) ──────────────────────────────
        if blog_title and blog_title.strip():
            title_lines = _wrap_title(blog_title)
            font_size = max(
                _TITLE_MIN_FONT,
                min(_TITLE_MAX_FONT, int(img_w * _TITLE_FONT_SIZE_RATIO)),
            )
            font = _load_font(font_size)

            # Measure each line and compute total block height
            line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in title_lines]
            line_heights = [bb[3] - bb[1] for bb in line_bboxes]
            line_widths = [bb[2] - bb[0] for bb in line_bboxes]
            line_spacing = int(font_size * 0.25)
            total_text_h = sum(line_heights) + line_spacing * (len(title_lines) - 1)
            max_text_w = max(line_widths) if line_widths else 0

            # Semi-transparent dark strip behind title
            strip_w = max_text_w + _TITLE_PADDING_X * 2
            strip_h = total_text_h + _TITLE_PADDING_Y * 2
            # Full-width strip looks cleaner
            strip_w = max(strip_w, int(img_w * 0.6))
            strip_x0 = 0
            strip_y0 = 0

            draw.rectangle(
                [strip_x0, strip_y0, strip_x0 + strip_w, strip_y0 + strip_h],
                fill=(0, 0, 0, 140),  # ~55% opacity black
            )

            # Render each line with shadow
            text_x = _TITLE_PADDING_X
            text_y = _TITLE_PADDING_Y
            for i, line in enumerate(title_lines):
                # Shadow
                draw.text(
                    (text_x + 1, text_y + 1), line,
                    fill=(0, 0, 0, 180), font=font,
                )
                # Main text
                draw.text(
                    (text_x, text_y), line,
                    fill=(255, 255, 255, 240), font=font,
                )
                text_y += line_heights[i] + line_spacing

        # ── 2. Ailey signature (bottom-right) ───────────────────
        sign = _load_sign()
        if sign:
            # Scale sign proportionally
            max_sign_w = int(img_w * _SIGN_MAX_WIDTH_RATIO)
            sign_scale = max_sign_w / sign.width
            new_w = int(sign.width * sign_scale)
            new_h = int(sign.height * sign_scale)
            sign_resized = sign.resize((new_w, new_h), Image.LANCZOS)

            # Position: bottom-right with margin
            sign_x = img_w - new_w - _SIGN_MARGIN
            sign_y = img_h - new_h - _SIGN_MARGIN

            # Optional: subtle dark backing behind signature for contrast
            backing_pad = 6
            draw.rectangle(
                [
                    sign_x - backing_pad,
                    sign_y - backing_pad,
                    sign_x + new_w + backing_pad,
                    sign_y + new_h + backing_pad,
                ],
                fill=(0, 0, 0, 80),  # ~30% opacity
            )

            # Paste sign onto overlay
            overlay.paste(sign_resized, (sign_x, sign_y), sign_resized)

        # ── Composite and save ───────────────────────────────────
        result = Image.alpha_composite(img, overlay)

        # Save as PNG (lossless) or convert to RGB for JPEG
        if output_path.lower().endswith(".jpg") or output_path.lower().endswith(".jpeg"):
            result = result.convert("RGB")
        result.save(output_path)

        print(f"[ImageStamp] ✅ Stamped: {os.path.basename(output_path)} "
              f"(title: {blog_title[:40]}…)")
        return output_path

    except Exception as e:
        print(f"[ImageStamp] ❌ Error stamping image: {e}")
        return None


def stamp_watermark(
    image_path: str,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Lightweight watermark — ONLY the Ailey signature (bottom-right).
    NO title bar, NO semi-transparent backing strip.

    Use this for gallery images, selfies, and autonomous art.
    For blog posts with title overlay, use stamp_blog_image() instead.

    Args:
        image_path: Path to the PNG/JPG image
        output_path: Optional different output path (default: overwrite)

    Returns:
        Path to the watermarked image, or None on failure
    """
    if not os.path.isfile(image_path):
        print(f"[ImageStamp] ❌ Image not found: {image_path}")
        return None

    if not output_path:
        output_path = image_path

    try:
        img = Image.open(image_path).convert("RGBA")
        img_w, img_h = img.size

        sign = _load_sign()
        if not sign:
            print("[ImageStamp] ⚠️ Signature file not found — skipping watermark")
            # Still return the path (image is fine, just no watermark)
            return output_path

        # Create overlay layer
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

        # Scale sign proportionally
        max_sign_w = int(img_w * _SIGN_MAX_WIDTH_RATIO)
        sign_scale = max_sign_w / sign.width
        new_w = int(sign.width * sign_scale)
        new_h = int(sign.height * sign_scale)
        sign_resized = sign.resize((new_w, new_h), Image.LANCZOS)

        # Position: bottom-right with margin
        sign_x = img_w - new_w - _SIGN_MARGIN
        sign_y = img_h - new_h - _SIGN_MARGIN

        # Paste sign directly onto overlay — no backing rectangle
        overlay.paste(sign_resized, (sign_x, sign_y), sign_resized)

        # Composite and save
        result = Image.alpha_composite(img, overlay)

        if output_path.lower().endswith((".jpg", ".jpeg")):
            result = result.convert("RGB")
        result.save(output_path)

        print(f"[ImageStamp] ✅ Watermark: {os.path.basename(output_path)}")
        return output_path

    except Exception as e:
        print(f"[ImageStamp] ❌ Error watermarking image: {e}")
        return None


# ── Instagram-specific stamp ─────────────────────────────────────────────
# Layout:
#   Top-left:     Post title (on semi-transparent strip)
#   Bottom-right:  A!ley signature logo
#   Bottom-left:   URL text "ask-ailey.sexngears.de"

_INSTA_URL = "ask-ailey.sexngears.de"
_INSTA_URL_FONT_RATIO = 0.025   # font size relative to image width
_INSTA_URL_MIN_FONT = 14
_INSTA_URL_MAX_FONT = 28


def stamp_instagram_image(
    image_path: str,
    title: str,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Stamp an Instagram image with Ailey branding:
    - Top-left:    Post title on semi-transparent dark strip
    - Bottom-right: A!ley signature logo
    - Bottom-left:  Portal URL (ask-ailey.sexngears.de)

    The image is modified IN-PLACE unless output_path is given.

    Args:
        image_path: Path to the generated PNG image
        title: The post title to overlay
        output_path: Optional different output path (default: overwrite)

    Returns:
        Path to the stamped image, or None on failure
    """
    if not os.path.isfile(image_path):
        print(f"[ImageStamp] ❌ Image not found: {image_path}")
        return None

    if not output_path:
        output_path = image_path

    try:
        img = Image.open(image_path).convert("RGBA")
        img_w, img_h = img.size

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # ── 1. Title bar (top-left) ──────────────────────────────
        if title and title.strip():
            title_lines = _wrap_title(title)
            font_size = max(
                _TITLE_MIN_FONT,
                min(_TITLE_MAX_FONT, int(img_w * _TITLE_FONT_SIZE_RATIO)),
            )
            font = _load_font(font_size)

            line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in title_lines]
            line_heights = [bb[3] - bb[1] for bb in line_bboxes]
            line_widths = [bb[2] - bb[0] for bb in line_bboxes]
            line_spacing = int(font_size * 0.25)
            total_text_h = sum(line_heights) + line_spacing * (len(title_lines) - 1)
            max_text_w = max(line_widths) if line_widths else 0

            strip_w = max_text_w + _TITLE_PADDING_X * 2
            strip_h = total_text_h + _TITLE_PADDING_Y * 2
            strip_w = max(strip_w, int(img_w * 0.55))

            draw.rectangle(
                [0, 0, strip_w, strip_h],
                fill=(0, 0, 0, 150),
            )

            text_x = _TITLE_PADDING_X
            text_y = _TITLE_PADDING_Y
            for i, line in enumerate(title_lines):
                draw.text((text_x + 1, text_y + 1), line, fill=(0, 0, 0, 180), font=font)
                draw.text((text_x, text_y), line, fill=(255, 255, 255, 240), font=font)
                text_y += line_heights[i] + line_spacing

        # ── 2. A!ley signature (bottom-right) ───────────────────
        sign = _load_sign()
        if sign:
            max_sign_w = int(img_w * _SIGN_MAX_WIDTH_RATIO)
            sign_scale = max_sign_w / sign.width
            new_w = int(sign.width * sign_scale)
            new_h = int(sign.height * sign_scale)
            sign_resized = sign.resize((new_w, new_h), Image.LANCZOS)

            sign_x = img_w - new_w - _SIGN_MARGIN
            sign_y = img_h - new_h - _SIGN_MARGIN

            backing_pad = 6
            draw.rectangle(
                [sign_x - backing_pad, sign_y - backing_pad,
                 sign_x + new_w + backing_pad, sign_y + new_h + backing_pad],
                fill=(0, 0, 0, 80),
            )
            overlay.paste(sign_resized, (sign_x, sign_y), sign_resized)

        # ── 3. URL text (bottom-left) ───────────────────────────
        url_font_size = max(
            _INSTA_URL_MIN_FONT,
            min(_INSTA_URL_MAX_FONT, int(img_w * _INSTA_URL_FONT_RATIO)),
        )
        url_font = _load_font(url_font_size)
        url_text = _INSTA_URL
        url_bbox = draw.textbbox((0, 0), url_text, font=url_font)
        url_w = url_bbox[2] - url_bbox[0]
        url_h = url_bbox[3] - url_bbox[1]

        url_x = _SIGN_MARGIN
        url_y = img_h - url_h - _SIGN_MARGIN - 4

        # Semi-transparent backing
        url_pad = 6
        draw.rectangle(
            [url_x - url_pad, url_y - url_pad,
             url_x + url_w + url_pad, url_y + url_h + url_pad],
            fill=(0, 0, 0, 100),
        )
        # Shadow + text
        draw.text((url_x + 1, url_y + 1), url_text, fill=(0, 0, 0, 160), font=url_font)
        draw.text((url_x, url_y), url_text, fill=(255, 255, 255, 200), font=url_font)

        # ── Composite and save ───────────────────────────────────
        result = Image.alpha_composite(img, overlay)

        if output_path.lower().endswith((".jpg", ".jpeg")):
            result = result.convert("RGB")
        result.save(output_path)

        print(f"[ImageStamp] ✅ Instagram stamp: {os.path.basename(output_path)} "
              f"(title: {title[:40]}…)")
        return output_path

    except Exception as e:
        print(f"[ImageStamp] ❌ Error stamping Instagram image: {e}")
        return None
