"""Interactive CLI for FlowMark."""

import os

from .batch import process_folder
from .config import CONFIG_PATH, SCRIPT_DIR, default_workers, load_config, normalize_position, resolve_path


def _prompt_yes_no(prompt, default=False):
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_with_default(prompt, default=""):
    if default not in (None, ""):
        raw = input(f"{prompt} [{default}]: ").strip().strip('"')
        return raw if raw else str(default)
    raw = input(f"{prompt}: ").strip().strip('"')
    return raw


def _prompt_sticker_options(sticker_cfg):
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
        position = normalize_position(raw_pos)
        if position:
            break
        print("❌ Choose left, middle, or right.")

    return sticker_path, size_percent, position


def main():
    print("\n=== 🖼️ FlowMark - Multithreaded Watermark Tool ===\n")

    config = load_config()
    text_cfg = config["text"]
    sticker_cfg = config["sticker"]
    print(f"📄 Loaded defaults from: {CONFIG_PATH}\n")

    folder = _prompt_with_default("Input folder path to process images", config.get("input_folder", ""))
    if not folder or not os.path.isdir(folder):
        print("❌ Invalid folder path.")
        return
    config["input_folder"] = folder

    use_text = _prompt_yes_no("Add text watermark?", default=bool(text_cfg.get("enabled", True)))
    text_cfg["enabled"] = use_text
    if use_text:
        text_cfg["content"] = _prompt_with_default(
            "Enter watermark text",
            text_cfg.get("content", ""),
        )
    else:
        text_cfg["content"] = ""

    use_sticker = _prompt_yes_no("Add PNG sticker watermark?", default=bool(sticker_cfg.get("enabled", False)))
    sticker_cfg["enabled"] = use_sticker
    if use_sticker:
        sticker_path, size_percent, position = _prompt_sticker_options(sticker_cfg)
        try:
            sticker_cfg["path"] = str(sticker_path.relative_to(SCRIPT_DIR))
        except ValueError:
            sticker_cfg["path"] = str(sticker_path)
        sticker_cfg["size_percent"] = size_percent
        sticker_cfg["position"] = position

    if not (text_cfg.get("enabled") and text_cfg.get("content")) and not sticker_cfg.get("enabled"):
        print("❌ Nothing to apply. Enable text and/or sticker watermark.")
        return

    output_raw = _prompt_with_default(
        "Output folder (blank/default = 'output' subfolder under input)",
        config.get("output_folder", ""),
    )
    config["output_folder"] = output_raw if output_raw else ""

    try:
        config["max_workers"] = default_workers()
        print(f"🧵 Using {config['max_workers']} threads (CPU count)")
    except Exception:
        config["max_workers"] = 4

    process_folder(folder, config=config)


if __name__ == "__main__":
    main()
