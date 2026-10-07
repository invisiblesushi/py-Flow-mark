"""Image resize, watermark placement, and JPEG compression."""

from PIL import Image, ImageDraw, ImageFont

from .config import SUBSAMPLING_MAP, normalize_position, normalize_trbl, combine_trbl, resolve_path


def _sizing_base(image):
    """Longest side — keeps watermark size consistent across orientations."""
    return max(image.width, image.height)


def resize_image(image, size_px=0, mode=None):
    """
    Optionally downscale so the longest side equals size_px. Never upscales.

    size_px: 0 / None = keep original. Positive = target longest side.
    mode: legacy arg; 'original' forces no resize.
    """
    if mode is not None and str(mode).strip().lower() in ("original", "none", ""):
        return image

    try:
        size_px = int(size_px or 0)
    except (TypeError, ValueError):
        return image

    if size_px <= 0:
        return image

    w, h = image.size
    current = max(w, h)
    if current <= size_px:
        return image

    scale = size_px / float(current)
    new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def anchor_xy(container_w, container_h, item_w, item_h, position, inset):
    """
    Place an item inside a container using a 3x3 anchor and TRBL insets.
    Always clamps so the item stays fully inside the container.
    """
    pos = normalize_position(position) or "bottom-right"
    inset = normalize_trbl(inset, 0)

    content_w = max(1, container_w - inset["left"] - inset["right"])
    content_h = max(1, container_h - inset["top"] - inset["bottom"])
    item_w = min(item_w, content_w)
    item_h = min(item_h, content_h)

    if pos in ("top-left", "middle-left", "bottom-left"):
        x = inset["left"]
    elif pos in ("top-right", "middle-right", "bottom-right"):
        x = container_w - item_w - inset["right"]
    else:
        x = inset["left"] + (content_w - item_w) // 2

    if pos in ("top-left", "top-middle", "top-right"):
        y = inset["top"]
    elif pos in ("middle-left", "center", "middle-right"):
        y = inset["top"] + (content_h - item_h) // 2
    else:
        y = container_h - item_h - inset["bottom"]

    x = int(max(0, min(x, container_w - item_w)))
    y = int(max(0, min(y, container_h - item_h)))
    return x, y, item_w, item_h


def add_text_watermark(image, text="", font_size_percent=3.0, position="bottom-middle",
                       padding=35, margin=None):
    """Add a text watermark at a 3x3 grid position."""
    if not text:
        return image

    inset = combine_trbl(padding, margin)

    watermark_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark_layer)

    font_size = max(12, int(_sizing_base(image) * (float(font_size_percent) / 100.0)))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x, y, _, _ = anchor_xy(
        image.width, image.height, text_width, text_height, position, inset,
    )

    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
    return Image.alpha_composite(image.convert("RGBA"), watermark_layer)


def add_sticker_watermark(image, sticker_path, size_percent=15, position="bottom-right",
                          padding=35, margin=None):
    """Add a PNG sticker at a 3x3 grid position using TRBL padding."""
    sticker = Image.open(sticker_path).convert("RGBA")
    inset = combine_trbl(padding, margin)

    content_w = max(1, image.width - inset["left"] - inset["right"])
    content_h = max(1, image.height - inset["top"] - inset["bottom"])

    size_percent = max(1, min(100, float(size_percent)))
    target_width = max(1, int(_sizing_base(image) * (size_percent / 100.0)))
    target_width = min(target_width, content_w)
    aspect = sticker.height / sticker.width if sticker.width else 1.0
    target_height = max(1, int(round(target_width * aspect)))
    if target_height > content_h:
        target_height = content_h
        target_width = max(1, int(round(target_height / aspect))) if aspect else target_width
        target_width = min(target_width, content_w)

    sticker = sticker.resize((target_width, target_height), Image.Resampling.LANCZOS)

    x, y, _, _ = anchor_xy(
        image.width, image.height, sticker.width, sticker.height, position, inset,
    )

    watermark_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    watermark_layer.paste(sticker, (x, y), sticker)
    return Image.alpha_composite(image.convert("RGBA"), watermark_layer)


def apply_watermarks(image, config, sticker_required=False):
    """
    Apply text and/or sticker watermarks from a config dict.
    Returns (image, warning_message_or_None).
    """
    config = config or {}
    text_cfg = config.get("text") or {}
    sticker_cfg = config.get("sticker") or {}
    warning = None

    image = image.convert("RGBA")

    if text_cfg.get("enabled", True) and text_cfg.get("content"):
        image = add_text_watermark(
            image,
            text=text_cfg.get("content", ""),
            font_size_percent=text_cfg.get("font_size_percent", 3.0),
            position=text_cfg.get("position", "bottom-middle"),
            padding=text_cfg.get("padding", 35),
            margin=text_cfg.get("margin"),
        )

    if sticker_cfg.get("enabled", False):
        sticker_path = resolve_path(sticker_cfg.get("path"))
        if sticker_path and sticker_path.is_file():
            image = add_sticker_watermark(
                image,
                sticker_path,
                size_percent=sticker_cfg.get("size_percent", 15),
                position=sticker_cfg.get("position", "bottom-right"),
                padding=sticker_cfg.get("padding", 35),
                margin=sticker_cfg.get("margin"),
            )
        else:
            warning = f"Sticker not found: {sticker_cfg.get('path') or '(empty)'}"
            if sticker_required:
                raise FileNotFoundError(warning)

    return image, warning


def compress_image(image, output_path, jpeg_options=None, quality=None):
    """
    Save as JPEG with quality / progressive / subsampling.
    Always preserves EXIF when present (Orientation already normalized).
    """
    jpeg_options = jpeg_options or {}
    if quality is None:
        quality = int(jpeg_options.get("quality", 85))
    quality = max(1, min(95, int(quality)))

    progressive = bool(jpeg_options.get("progressive", True))
    sub_key = str(jpeg_options.get("subsampling", "4:2:0"))
    subsampling = SUBSAMPLING_MAP.get(sub_key, 2)

    exif_data = image.info.get("exif")

    rgb_image = Image.new("RGB", image.size, (255, 255, 255))
    if image.mode == "RGBA":
        rgb_image.paste(image, mask=image.split()[3])
    else:
        rgb_image.paste(image.convert("RGB"))

    save_kwargs = {
        "format": "JPEG",
        "optimize": True,
        "quality": quality,
        "progressive": progressive,
        "subsampling": subsampling,
    }
    if exif_data:
        save_kwargs["exif"] = exif_data

    rgb_image.save(output_path, **save_kwargs)
