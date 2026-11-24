"""Preview image helpers (placeholders, folder samples, fit-to-panel)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

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


def _hex_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def centered_ratio_box(width, height, ratio_w, ratio_h):
    """Largest centered (x0, y0, x1, y1) box with ratio_w:ratio_h inside width x height."""
    target = ratio_w / float(ratio_h)
    if width / float(height) > target:
        box_h = height
        box_w = int(round(height * target))
    else:
        box_w = width
        box_h = int(round(width / target))
    x0 = (width - box_w) // 2
    y0 = (height - box_h) // 2
    return x0, y0, x0 + box_w, y0 + box_h


def draw_aspect_overlays(image, guides):
    """
    Draw crop-guide frames on a copy of the (display-sized) preview image.

    guides: iterable of (label, ratio_w, ratio_h, color_hex).
    With a single guide, the area outside it is dimmed to show the crop.
    """
    guides = list(guides)
    if not guides:
        return image
    out = image.convert("RGBA")
    w, h = out.size
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    line = max(2, round(min(w, h) / 250))
    font_size = max(11, round(min(w, h) / 32))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    boxes = [(label, centered_ratio_box(w, h, rw, rh), _hex_rgb(color)) for label, rw, rh, color in guides]

    if len(boxes) == 1:
        x0, y0, x1, y1 = boxes[0][1]
        shade = (0, 0, 0, 140)
        for rect in ((0, 0, w, y0), (0, y1, w, h), (0, y0, x0, y1), (x1, y0, w, y1)):
            if rect[2] > rect[0] and rect[3] > rect[1]:
                draw.rectangle((rect[0], rect[1], rect[2] - 1, rect[3] - 1), fill=shade)

    for _label, (x0, y0, x1, y1), rgb in boxes:
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=rgb + (255,), width=line)

    # Labels go at each frame's top-left; push a label down until it clears
    # every label already placed (frames often share the same top edge).
    pad = max(3, font_size // 4)
    placed = []
    for label, (x0, y0, _x1, _y1), rgb in boxes:
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        lx = x0 + line + pad
        ly = y0 + line + pad
        while True:
            rect = (lx - pad, ly - pad, lx + tw + pad, ly + th + pad)
            hit = next((r for r in placed if rect[0] < r[2] and r[0] < rect[2]
                        and rect[1] < r[3] and r[1] < rect[3]), None)
            if hit is None:
                break
            ly = hit[3] + pad + 2
        placed.append(rect)
        draw.rectangle(rect, fill=(0, 0, 0, 170))
        draw.text((lx - tb[0], ly - tb[1]), label, font=font, fill=rgb + (255,))
    return Image.alpha_composite(out, layer)
