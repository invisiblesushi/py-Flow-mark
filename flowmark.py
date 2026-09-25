import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"

DEFAULT_CONFIG = {
    "input_folder": "",
    "output_folder": "",
    "max_workers": 4,
    "jpeg_quality": 98,
    "text": {
        "enabled": True,
        "content": "",
        "font_size_percent": 3.0,
        "padding": 25,
        "margin": 10,
    },
    "sticker": {
        "enabled": False,
        "path": "Sticker.png",
        "size_percent": 15,
        "position": "middle",
        "padding": 25,
        "margin": 10,
    },
}


# ---------- Config ----------

def _deep_merge(base, override):
    """Merge override into base (dicts only); override wins for leaf values."""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path=None):
    """Load config.json; fall back to built-in defaults for missing keys."""
    path = Path(path) if path else CONFIG_PATH
    config = dict(DEFAULT_CONFIG)
    config["text"] = dict(DEFAULT_CONFIG["text"])
    config["sticker"] = dict(DEFAULT_CONFIG["sticker"])

    if not path.is_file():
        print(f"⚠️ Config not found at {path}, using built-in defaults.")
        return config

    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        config = _deep_merge(config, loaded)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ Failed to read config ({e}), using built-in defaults.")

    return config


def resolve_path(value, base_dir=SCRIPT_DIR):
    """Resolve a path; relative paths are relative to the config/script folder."""
    if not value:
        return None
    path = Path(str(value).strip().strip('"'))
    if not path.is_absolute():
        path = base_dir / path
    return path


# ---------- Image Processing Functions ----------

def _sizing_base(image):
    """
    Longest side of the image.

    Using width alone makes portrait watermarks look much smaller than
    landscape ones of the same resolution. The longest side keeps absolute
    watermark size consistent across orientations.
    """
    return max(image.width, image.height)


def add_text_watermark(image, text="", font_size_percent=3.0, padding=25, margin=10):
    """
    Add a text watermark (no icon).
    Bottom-center aligned with padding and margin.
    Works on both vertical and horizontal images.
    """
    if not text:
        return image

    watermark_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark_layer)

    # Font size as % of longest side (same look on portrait and landscape)
    font_size = max(12, int(_sizing_base(image) * (float(font_size_percent) / 100.0)))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (image.width - text_width) / 2
    y = image.height - text_height - padding - margin

    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return Image.alpha_composite(image.convert("RGBA"), watermark_layer)


def add_sticker_watermark(image, sticker_path, size_percent=15, position="middle", padding=25, margin=10):
    """
    Add a PNG sticker watermark along the bottom of the image.

    size_percent: sticker width as a percentage of the image's longest side (1-100).
    position: "left", "middle", or "right".
    """
    sticker = Image.open(sticker_path).convert("RGBA")

    size_percent = max(1, min(100, float(size_percent)))
    target_width = max(1, int(_sizing_base(image) * (size_percent / 100.0)))
    # Keep within the image width (matters for tall portraits with a large %)
    max_width = max(1, image.width - 2 * (padding + margin))
    target_width = min(target_width, max_width)
    aspect = sticker.height / sticker.width
    target_height = max(1, int(target_width * aspect))
    sticker = sticker.resize((target_width, target_height), Image.Resampling.LANCZOS)

    position = (position or "middle").strip().lower()
    if position in ("l", "left"):
        x = padding + margin
    elif position in ("r", "right"):
        x = image.width - sticker.width - padding - margin
    else:
        x = (image.width - sticker.width) // 2

    y = image.height - sticker.height - padding - margin

    watermark_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    watermark_layer.paste(sticker, (int(x), int(y)), sticker)

    return Image.alpha_composite(image.convert("RGBA"), watermark_layer)


def compress_image(image, output_path, quality=98):
    """
    Compress image and save as JPEG,
    preserving EXIF metadata.
    """
    exif_data = image.info.get("exif")

    rgb_image = Image.new("RGB", image.size, (255, 255, 255))
    rgb_image.paste(image, mask=image.split()[3] if image.mode == "RGBA" else None)

    if exif_data:
        rgb_image.save(output_path, "JPEG", optimize=True, quality=quality, exif=exif_data)
    else:
        rgb_image.save(output_path, "JPEG", optimize=True, quality=quality)


# ---------- Worker Function ----------

def process_image(file, output_folder, watermark_text="", sticker_path=None,
                  sticker_size_percent=15, sticker_position="middle",
                  text_options=None, sticker_options=None, jpeg_quality=98):
    """Process a single image file."""
    text_options = text_options or {}
    sticker_options = sticker_options or {}

    try:
        image = Image.open(file)
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGBA")

        if watermark_text:
            image = add_text_watermark(
                image,
                watermark_text,
                font_size_percent=text_options.get("font_size_percent", 3.0),
                padding=text_options.get("padding", 25),
                margin=text_options.get("margin", 10),
            )

        if sticker_path:
            image = add_sticker_watermark(
                image,
                sticker_path,
                size_percent=sticker_size_percent,
                position=sticker_position,
                padding=sticker_options.get("padding", 25),
                margin=sticker_options.get("margin", 10),
            )

        output_path = output_folder / (file.stem + ".jpg")
        compress_image(image, output_path, quality=jpeg_quality)

        return f"✅ {file.name}"
    except Exception as e:
        return f"❌ {file.name} failed: {e}"


# ---------- Folder Processor (Multithreaded) ----------

def process_folder(input_folder, watermark_text="", output_folder=None, max_workers=4,
                   sticker_path=None, sticker_size_percent=15, sticker_position="middle",
                   text_options=None, sticker_options=None, jpeg_quality=98):
    """Process all images with optional text and/or sticker watermark using multithreading."""
    input_folder = Path(input_folder)

    if output_folder:
        output_folder = Path(output_folder)
    else:
        output_folder = input_folder / "output"

    output_folder.mkdir(parents=True, exist_ok=True)

    sticker_resolved = Path(sticker_path).resolve() if sticker_path else None
    images = [
        f for f in input_folder.iterdir()
        if f.suffix.lower() in [".jpg", ".jpeg", ".png"]
        and (sticker_resolved is None or f.resolve() != sticker_resolved)
    ]
    if not images:
        print("⚠️ No images found in this folder.")
        return

    total = len(images)
    print(f"🧵 Starting multithreaded processing with {max_workers} workers...")
    print(f"📸 Found {total} images\n")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_image,
                f,
                output_folder,
                watermark_text,
                sticker_path,
                sticker_size_percent,
                sticker_position,
                text_options,
                sticker_options,
                jpeg_quality,
            ): f
            for f in images
        }
        for i, future in enumerate(as_completed(futures), 1):
            print(f"[{i}/{total}] {future.result()}")

    print(f"\n🎉 Done! All {total} images saved in: {output_folder}")


# ---------- CLI helpers ----------

def _prompt_yes_no(prompt, default=False):
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_with_default(prompt, default=""):
    """Prompt; empty input keeps default. Shows default in brackets when set."""
    if default not in (None, ""):
        raw = input(f"{prompt} [{default}]: ").strip().strip('"')
        return raw if raw else str(default)
    raw = input(f"{prompt}: ").strip().strip('"')
    return raw


def _normalize_position(position):
    position = (position or "middle").strip().lower()
    if position in ("l", "left"):
        return "left"
    if position in ("r", "right"):
        return "right"
    if position in ("m", "middle", "c", "center"):
        return "middle"
    return None


def _prompt_sticker_options(sticker_cfg):
    """Ask for sticker path, size %, and position — defaults from config."""
    cfg_path = resolve_path(sticker_cfg.get("path") or "Sticker.png")
    default_hint = str(cfg_path) if cfg_path and cfg_path.is_file() else (sticker_cfg.get("path") or "")

    while True:
        raw = _prompt_with_default("Path to PNG sticker", default_hint)
        sticker_path = resolve_path(raw) if raw else cfg_path
        if sticker_path and sticker_path.is_file() and sticker_path.suffix.lower() == ".png":
            break
        print("❌ Please provide a valid PNG file path.")

    default_size = sticker_cfg.get("size_percent", 15)
    while True:
        raw_size = _prompt_with_default(
            "Sticker size as % of image's longer side",
            default_size,
        )
        try:
            size_percent = float(raw_size)
            if 1 <= size_percent <= 100:
                break
        except (TypeError, ValueError):
            pass
        print("❌ Enter a number between 1 and 100.")

    default_pos = sticker_cfg.get("position", "middle")
    while True:
        raw_pos = _prompt_with_default("Sticker position — left / middle / right", default_pos)
        position = _normalize_position(raw_pos)
        if position:
            break
        print("❌ Choose left, middle, or right.")

    return sticker_path, size_percent, position


# ---------- Main Script ----------

if __name__ == "__main__":
    print("\n=== 🖼️ FlowMark - Multithreaded Watermark Tool ===\n")

    config = load_config()
    text_cfg = config["text"]
    sticker_cfg = config["sticker"]
    print(f"📄 Loaded defaults from: {CONFIG_PATH}\n")

    folder = _prompt_with_default("Input folder path to process images", config.get("input_folder", ""))
    if not folder or not os.path.isdir(folder):
        print("❌ Invalid folder path.")
        exit()

    use_text = _prompt_yes_no("Add text watermark?", default=bool(text_cfg.get("enabled", True)))
    watermark_text = ""
    if use_text:
        watermark_text = _prompt_with_default(
            "Enter watermark text",
            text_cfg.get("content", ""),
        )

    use_sticker = _prompt_yes_no("Add PNG sticker watermark?", default=bool(sticker_cfg.get("enabled", False)))
    sticker_path = None
    sticker_size_percent = sticker_cfg.get("size_percent", 15)
    sticker_position = _normalize_position(sticker_cfg.get("position", "middle")) or "middle"
    if use_sticker:
        sticker_path, sticker_size_percent, sticker_position = _prompt_sticker_options(sticker_cfg)

    if not watermark_text and not sticker_path:
        print("❌ Nothing to apply. Enable text and/or sticker watermark.")
        exit()

    output_raw = _prompt_with_default(
        "Output folder (blank/default = 'output' subfolder under input)",
        config.get("output_folder", ""),
    )
    output_folder = output_raw if output_raw else None

    try:
        workers = int(
            _prompt_with_default("Number of threads", config.get("max_workers", 4))
        )
    except ValueError:
        workers = int(config.get("max_workers", 4))

    process_folder(
        folder,
        watermark_text=watermark_text,
        output_folder=output_folder,
        max_workers=workers,
        sticker_path=sticker_path,
        sticker_size_percent=sticker_size_percent,
        sticker_position=sticker_position,
        text_options=text_cfg,
        sticker_options=sticker_cfg,
        jpeg_quality=int(config.get("jpeg_quality", 98)),
    )
