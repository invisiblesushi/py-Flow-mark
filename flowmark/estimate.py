"""JPEG export size estimation helpers."""

import io
from pathlib import Path

from PIL import Image, ImageOps

from .config import resolve_path, effective_jpeg_options
from .image_ops import apply_watermarks, compress_image, resize_image


def format_bytes(num_bytes):
    """Human-readable byte size."""
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "—"
    if n < 1024:
        return f"{int(n)} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / (1024 ** 2):.2f} MB"
    return f"{n / (1024 ** 3):.2f} GB"


def list_input_images(folder, sticker_path=None):
    """Image files in folder, excluding the sticker PNG if it lives there."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    sticker_resolved = Path(sticker_path).resolve() if sticker_path else None
    files = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        if sticker_resolved and f.resolve() == sticker_resolved:
            continue
        files.append(f)
    return files


def estimate_export_savings(folder, config):
    """
    Run resize + watermarks + JPEG settings on the first image.
    Returns a dict used for GUI estimate text, or None if no images.
    """
    config = config or {}
    sticker_cfg = config.get("sticker") or {}
    sticker_path = None
    if sticker_cfg.get("enabled"):
        sticker_path = resolve_path(sticker_cfg.get("path"))

    images = list_input_images(folder, sticker_path=sticker_path)
    if not images:
        return None

    sample = images[0]
    original_size = sample.stat().st_size

    image = Image.open(sample)
    try:
        exif_obj = image.getexif()
    except Exception:
        exif_obj = None

    image = ImageOps.exif_transpose(image)
    image = image.convert("RGBA")

    exif_bytes = None
    if exif_obj:
        try:
            exif_obj[0x0112] = 1
            exif_bytes = exif_obj.tobytes()
        except Exception:
            exif_bytes = None

    resize_cfg = config.get("resize") or {}
    image = resize_image(
        image,
        size_px=resize_cfg.get("size_px", 0),
        mode=resize_cfg.get("mode"),
    )
    image, _warning = apply_watermarks(image, config)
    if exif_bytes:
        image.info["exif"] = exif_bytes

    buf = io.BytesIO()
    compress_image(image, buf, jpeg_options=effective_jpeg_options(config))
    export_size = buf.tell()

    saved = original_size - export_size
    ratio = (export_size / original_size) if original_size else 1.0
    pct_saved = (1.0 - ratio) * 100.0 if original_size else 0.0

    folder_original = sum(f.stat().st_size for f in images)
    folder_export_est = int(folder_original * ratio)
    folder_saved_est = folder_original - folder_export_est

    return {
        "sample_name": sample.name,
        "sample_count": len(images),
        "original_size": original_size,
        "export_size": export_size,
        "saved": saved,
        "pct_saved": pct_saved,
        "folder_original": folder_original,
        "folder_export_est": folder_export_est,
        "folder_saved_est": folder_saved_est,
    }


def format_savings_estimate(result):
    """Multi-line summary for the GUI."""
    if not result:
        return "Select an input folder with images to estimate JPEG savings."

    sample_line = (
        f"Sample ({result['sample_name']}): "
        f"{format_bytes(result['original_size'])} -> {format_bytes(result['export_size'])} "
        f"(saves {result['pct_saved']:.0f}%, {format_bytes(result['saved'])})"
    )
    n = result["sample_count"]
    folder_line = (
        f"Folder estimate ({n} image{'s' if n != 1 else ''}): "
        f"{format_bytes(result['folder_original'])} -> ~{format_bytes(result['folder_export_est'])} "
        f"(saves ~{format_bytes(result['folder_saved_est'])})"
    )
    return sample_line + "\n" + folder_line
