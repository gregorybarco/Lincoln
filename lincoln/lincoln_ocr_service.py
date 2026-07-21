"""
Lincoln OCR Service  v0.6.0
==============================
Extracts text from images for chat injection.
Supports two extraction modes:

  1. Tesseract OCR (via pytesseract + WSL Tesseract binary)
     Best for: Bloomberg terminal screenshots, option chain tables,
     OMON rate tables, fixed-width terminal text, printed documents.
     Requires: pip install pytesseract Pillow
               WSL: sudo apt install tesseract-ocr

  2. Vision model query (via Ollama with a multimodal model)
     Best for: Bloomberg OVDV 3D vol surface charts, financial diagrams,
     handwritten notes, images where OCR would be unreliable.
     Requires: a vision-capable model loaded in Ollama
               (e.g. llava, gemma3:12b, qwen2.5vl)

The caller chooses the mode. The file upload route uses Tesseract by default
and falls back to a descriptive note if Tesseract is unavailable.

WSL Tesseract install command (run once in Ubuntu terminal):
  sudo apt install tesseract-ocr tesseract-ocr-rus tesseract-ocr-hin
    tesseract-ocr-urd tesseract-ocr-pan tesseract-ocr-ben tesseract-ocr-ara
    tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-jpn
    tesseract-ocr-chi-sim tesseract-ocr-chi-tra

Supported languages for OCR: eng, rus, urd, hin, pan, ben, ara, fra, deu, jpn, chi_sim, chi_tra
"""

import base64
import io
import subprocess
import tempfile
from pathlib import Path


def extract_text_tesseract(
    image_bytes: bytes,
    lang:        str = "eng",
    psm:         int = 6,
) -> str:
    """
    Extract text from an image using Tesseract OCR via WSL.

    Args:
        image_bytes : Raw image bytes (PNG, JPG, BMP, TIFF, etc.)
        lang        : Tesseract language code(s), e.g. 'eng', 'eng+rus', 'hin'
        psm         : Page segmentation mode.
                      6 = uniform block of text (best for Bloomberg tables)
                      3 = auto (best for mixed content)
                      11 = sparse text (best for scattered terminal output)

    Returns:
        Extracted text string. Returns an error message if Tesseract is unavailable.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return (
            "(OCR unavailable: pytesseract and/or Pillow not installed. "
            "Run: pip install pytesseract Pillow)"
        )

    try:
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed (Tesseract handles JPEG artifacts better on RGB)
        if image.mode not in ("RGB", "L", "RGBA"):
            image = image.convert("RGB")

        # High-DPI upscaling for small-text images (Bloomberg terminal font is dense)
        width, height = image.size
        if width < 1200:
            scale = 2
            image = image.resize((width * scale, height * scale), Image.LANCZOS)

        config = f"--psm {psm} --oem 3"
        text   = pytesseract.image_to_string(image, lang=lang, config=config)
        return text.strip() if text.strip() else "(No text extracted from image)"

    except Exception as exc:
        return f"(OCR extraction failed: {exc})"


def extract_text_vision_model(
    image_bytes: bytes,
    model:       str,
    prompt:      str = "",
    ollama_url:  str = "http://localhost:11434",
) -> str:
    """
    Send an image to a vision-capable Ollama model and return its description.
    Best for charts, 3D vol surfaces, and diagrams where OCR is not applicable.

    Args:
        image_bytes : Raw image bytes
        model       : Vision-capable Ollama model name (e.g. 'llava', 'gemma3:12b')
        prompt      : Instruction for the model. Defaults to a financial extraction prompt.
        ollama_url  : Ollama base URL

    Returns:
        Model's text description / extraction of the image content.
    """
    import requests

    if not prompt:
        prompt = (
            "Extract and describe all visible data from this financial image. "
            "If it is a table or chart, list the values systematically. "
            "If it is a Bloomberg terminal screenshot, identify the function, "
            "ticker, date, and all visible numerical values. "
            "Be precise and complete."
        )

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model":  model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip() or "(No response from vision model)"

    except requests.exceptions.ConnectionError:
        return f"(Vision model unavailable: cannot connect to Ollama at {ollama_url})"
    except Exception as exc:
        return f"(Vision model extraction failed: {exc})"


def extract_image(
    image_bytes:  bytes,
    mode:         str = "ocr",
    lang:         str = "eng",
    psm:          int = 6,
    vision_model: str = "",
    vision_prompt: str = "",
    ollama_url:   str = "http://localhost:11434",
) -> str:
    """
    Unified image extraction entry point.

    Args:
        image_bytes   : Raw image bytes
        mode          : 'ocr' for Tesseract, 'vision' for vision model
        lang          : Tesseract language (OCR mode)
        psm           : Tesseract PSM (OCR mode)
        vision_model  : Ollama model name (vision mode)
        vision_prompt : Custom prompt (vision mode)
        ollama_url    : Ollama base URL (vision mode)

    Returns:
        Extracted text string.
    """
    if mode == "vision" and vision_model:
        return extract_text_vision_model(
            image_bytes,
            model=vision_model,
            prompt=vision_prompt,
            ollama_url=ollama_url,
        )

    return extract_text_tesseract(image_bytes, lang=lang, psm=psm)


# ── Bloomberg-specific extractors ─────────────────────────────────────────────

def extract_bloomberg_table(image_bytes: bytes) -> str:
    """
    Optimised extraction for Bloomberg terminal table screenshots.
    Uses PSM 6 (uniform block) with English language.
    Bloomberg uses a fixed-width terminal font -- PSM 6 handles this best.
    """
    return extract_text_tesseract(image_bytes, lang="eng", psm=6)


def extract_bloomberg_vol_surface(image_bytes: bytes, vision_model: str, ollama_url: str) -> str:
    """
    Extraction for Bloomberg OVDV 3D volatility surface charts.
    OCR cannot read 3D charts -- requires a vision model.
    """
    prompt = (
        "This is a Bloomberg OVDV (Options Volatility Surface) screenshot. "
        "Describe the volatility surface structure: "
        "1. What is the ticker and date shown? "
        "2. What is the approximate ATM implied volatility level? "
        "3. Describe the short-dated skew (moneyness < 80% and > 120%). "
        "4. Describe the term structure (vol vs expiry at ATM). "
        "5. Note any unusual features: spikes, inversions, elevated short-dated vol. "
        "Be precise with numerical values where visible."
    )
    return extract_text_vision_model(
        image_bytes,
        model=vision_model,
        prompt=prompt,
        ollama_url=ollama_url,
    )
