"""Theme constants and shared GUI helpers."""

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG = "#0f172a"
PANEL = "#18181b"
CARD = "#1e293b"
BORDER = "#334155"
ACCENT = "#6366f1"
ACCENT_HOVER = "#818cf8"
MUTED = "#94a3b8"
TEXT = "#e2e8f0"
SUCCESS = "#34d399"
DANGER = "#f87171"

PREVIEW_LANDSCAPE = (960, 720)
PREVIEW_PORTRAIT = (720, 960)
PREVIEW_MARGIN = 80
PREVIEW_WORK_MAX = 1600
DEBOUNCE_MS = 150
ESTIMATE_DEBOUNCE_MS = 400
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
RESIZE_PRESETS = (720, 1080, 1440, 1920)
TRBL_SIDES = ("top", "right", "bottom", "left")
TRBL_LABELS = ("T", "R", "B", "L")

# Preview-only crop guides, written in portrait form (short side first).
# On landscape photos each guide is rotated (4:5 -> 5:4, 960×1080 -> 1080×960).
# Drawn as the largest centered frame of that ratio; never written to exports.
#   (key, ratio or None, pixel sizes, color)
ASPECT_GUIDES = (
    ("4:5", (4, 5), (), "#f472b6"),
    ("9:16", (9, 16), ((1080, 1920), (540, 960)), "#38bdf8"),
    ("960x1080", None, ((960, 1080),), "#facc15"),
    ("640x1080", None, ((640, 1080),), "#34d399"),
)


def oriented_guide(guide, orientation):
    """
    Resolve a guide for 'portrait' or 'landscape'.
    Returns (button_label, full_label, ratio_w, ratio_h, color).
    """
    _key, ratio, sizes, color = guide
    flip = orientation == "landscape"

    def turn(pair):
        return (pair[1], pair[0]) if flip else pair

    ratio_text = "{}:{}".format(*turn(ratio)) if ratio else ""
    sizes_text = " / ".join("{}×{}".format(*turn(s)) for s in sizes)
    rw, rh = turn(ratio or sizes[0])
    button = ratio_text or sizes_text
    full = " · ".join(t for t in (ratio_text, sizes_text) if t)
    return button, full, rw, rh, color

POSITION_GRID = [
    ("top-left", "top-middle", "top-right"),
    ("middle-left", "center", "middle-right"),
    ("bottom-left", "bottom-middle", "bottom-right"),
]


def truncate_path(path, max_len=42):
    path = (path or "").strip()
    if len(path) <= max_len:
        return path or "No folder selected"
    return "…" + path[-(max_len - 1):]
