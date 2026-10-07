"""Preview image helpers (placeholders, folder samples, fit-to-panel)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .theme import IMAGE_EXTS, PREVIEW_WORK_MAX


def make_placeholder(size, label):
    w, h = size
    img = Image.new("RGB", size, (30, 41, 59))
    draw = ImageDraw.Draw(img)
    step = 40
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=(51, 65, 85), width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=(51, 65, 85), width=1)
    draw.rectangle([0, 0, w - 1, h - 1], outline=(99, 102, 241), width=2)
    text = f"{label}\n{w}×{h}"
    try:
        bbox = draw.multiline_textbbox((0, 0), text, align="center")
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = w // 4, 40
    draw.multiline_text(((w - tw) / 2, (h - th) / 2), text, fill=(148, 163, 184), align="center")
    return img.convert("RGBA")


def fit_for_display(image, max_width, max_height):
    """Scale image to fit inside max_width x max_height (aspect preserved)."""
    max_width = max(32, int(max_width))
    max_height = max(32, int(max_height))
    w, h = image.size
    scale = min(max_width / w, max_height / h)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    if new_size == (w, h):
        return image
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _cap_for_preview(image, max_side=PREVIEW_WORK_MAX):
    w, h = image.size
    longest = max(w, h)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    return image.resize(
        (max(1, int(w * scale)), max(1, int(h * scale))),
        Image.Resampling.LANCZOS,
    )


def find_folder_preview_images(folder):
    folder = Path(folder) if folder else None
    if not folder or not folder.is_dir():
        return None, None

    landscape = portrait = None
    try:
        files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS)
    except OSError:
        return None, None

    for path in files:
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGBA")
                w, h = im.size
                if w >= h and landscape is None:
                    landscape = _cap_for_preview(im.copy())
                elif h > w and portrait is None:
                    portrait = _cap_for_preview(im.copy())
            if landscape is not None and portrait is not None:
                break
        except Exception:
            continue
    return landscape, portrait
