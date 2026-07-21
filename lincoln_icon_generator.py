"""
Lincoln Icon Generator  v0.6.0
================================
Generates lincoln.ico from an inline SVG.
Run once: python lincoln_icon_generator.py
Requires: pip install Pillow cairosvg (or just Pillow for the fallback raster path)

The icon is a capital L in clean geometric style on a dark rounded-rectangle
background, using Lincoln's beige/gold accent colour on dark charcoal.
"""

import os
import sys
from pathlib import Path

OUTPUT_PATH = Path(__file__).resolve().parent / "lincoln.ico"

# Lincoln SVG icon -- Letter L, geometric, dark bg, gold accent
_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <!-- Dark charcoal background with rounded corners -->
  <rect width="64" height="64" rx="12" ry="12" fill="#1e1e2e"/>
  <!-- Gold accent bar (left vertical of L) -->
  <rect x="16" y="12" width="10" height="36" rx="3" fill="#c9a84c"/>
  <!-- Gold accent bar (bottom horizontal of L) -->
  <rect x="16" y="38" width="26" height="10" rx="3" fill="#c9a84c"/>
</svg>"""


def generate_ico_from_svg():
    """Generate .ico file from the SVG definition above."""

    # Try cairosvg first (vector-quality render)
    try:
        import cairosvg
        import io
        from PIL import Image

        png_bytes = cairosvg.svg2png(bytestring=_SVG.encode(), output_width=256, output_height=256)
        img       = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        sizes     = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        imgs      = [img.resize(s, Image.LANCZOS) for s in sizes]
        imgs[0].save(str(OUTPUT_PATH), format="ICO", sizes=sizes, append_images=imgs[1:])
        print(f"[Lincoln] Icon generated (cairosvg): {OUTPUT_PATH}")
        return True

    except ImportError:
        pass
    except Exception as exc:
        print(f"[Lincoln] cairosvg render failed: {exc}")

    # Fallback: draw icon programmatically with Pillow (no SVG dependency)
    try:
        from PIL import Image, ImageDraw, ImageFont

        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        imgs  = []

        for w, h in sizes:
            img  = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Rounded rectangle background (charcoal)
            radius = max(2, w // 5)
            draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=(30, 30, 46, 255))

            # L shape in gold (#c9a84c)
            gold       = (201, 168, 76, 255)
            bar_w      = max(2, w // 6)
            margin     = max(2, w // 5)
            v_top      = max(2, h // 6)
            v_bottom   = h - margin - bar_w
            h_right    = w - margin

            # Vertical bar
            draw.rectangle([margin, v_top, margin + bar_w, v_bottom + bar_w], fill=gold)
            # Horizontal bar
            draw.rectangle([margin, v_bottom, h_right, v_bottom + bar_w], fill=gold)

            imgs.append(img)

        imgs[0].save(str(OUTPUT_PATH), format="ICO", sizes=sizes, append_images=imgs[1:])
        print(f"[Lincoln] Icon generated (Pillow fallback): {OUTPUT_PATH}")
        return True

    except ImportError:
        print("[Lincoln] Pillow not installed -- cannot generate icon.")
        print("[Lincoln] Run: pip install Pillow")
        return False
    except Exception as exc:
        print(f"[Lincoln] Icon generation failed: {exc}")
        return False


if __name__ == "__main__":
    ok = generate_ico_from_svg()
    sys.exit(0 if ok else 1)
