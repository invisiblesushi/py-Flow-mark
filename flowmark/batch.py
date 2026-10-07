"""Multithreaded folder processing."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps

from .cloud import CloudUploadError, maybe_cloud_upload
from .config import default_workers, effective_jpeg_options, load_config, resolve_path
from .image_ops import apply_watermarks, compress_image, resize_image


# #region agent log
def _agent_dbg(hypothesis_id, location, message, data=None):
    import json
    import time
    try:
        with open(
            r"C:\Users\danie\Documents\GitHub\py-Flow-mark\debug-cc9b70.log",
            "a",
            encoding="utf-8",
        ) as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "cc9b70",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data or {},
                        "timestamp": int(time.time() * 1000),
                        "runId": "post-fix",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
# #endregion


def process_image(file, output_folder, config):
    """
    Process a single image: transpose → resize → watermarks → JPEG.
    Returns (ok, message, output_path_or_None).
    """
    try:
        image = Image.open(file)
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

        output_path = Path(output_folder) / (file.stem + ".jpg")
        compress_image(image, output_path, jpeg_options=effective_jpeg_options(config))

        return True, f"✅ {file.name}", output_path
    except Exception as e:
        return False, f"❌ {file.name} failed: {e}", None


def process_folder(input_folder, config=None, output_folder=None, max_workers=None,
                   progress_callback=None):
    """
    Process all images using a full config dict.

    progress_callback(message: str) is optional (used by GUI).
    Returns dict with keys: output_folder, processed, failed, album_url.
    """
    config = config or load_config()
    input_folder = Path(input_folder)

    if output_folder:
        output_folder = Path(output_folder)
    elif config.get("output_folder"):
        output_folder = Path(config["output_folder"])
    else:
        output_folder = input_folder / "output"

    output_folder.mkdir(parents=True, exist_ok=True)

    workers = int(max_workers if max_workers is not None else default_workers())

    sticker_cfg = config.get("sticker") or {}
    sticker_resolved = None
    if sticker_cfg.get("enabled"):
        sp = resolve_path(sticker_cfg.get("path"))
        if sp:
            sticker_resolved = sp.resolve()

    images = [
        f for f in input_folder.iterdir()
        if f.suffix.lower() in [".jpg", ".jpeg", ".png"]
        and (sticker_resolved is None or f.resolve() != sticker_resolved)
    ]
    # Stable alphabetical order for batch + upload album order
    images = sorted(images, key=lambda p: p.name.lower())
    if not images:
        msg = "⚠️ No images found in this folder."
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        return {
            "output_folder": output_folder,
            "processed": [],
            "failed": 0,
            "album_url": None,
        }

    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    total = len(images)
    log(f"🧵 Starting with {workers} workers — {total} images")

    # #region agent log
    _agent_dbg(
        "A",
        "batch.py:process_folder",
        "input images order (sorted)",
        {"count": total, "first15": [p.name for p in images[:15]]},
    )
    # #endregion

    # Keep results aligned with input order (not as_completed order)
    results = [None] * total  # (ok, message, out_path)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_image, images[i], output_folder, config): i
            for i in range(total)
        }
        done = 0
        for future in as_completed(futures):
            idx = futures[future]
            ok, message, out_path = future.result()
            results[idx] = (ok, message, out_path)
            done += 1
            log(f"[{done}/{total}] {message}")

    processed = []
    failed = 0
    for ok, _message, out_path in results:
        if ok and out_path is not None:
            processed.append(out_path)
        else:
            failed += 1

    # #region agent log
    _agent_dbg(
        "A",
        "batch.py:process_folder",
        "processed list order after batch",
        {
            "count": len(processed),
            "first15": [p.name for p in processed[:15]],
            "matches_sorted_input": [p.name for p in processed[:15]]
            == [images[i].stem + ".jpg" for i in range(min(15, len(images)))],
        },
    )
    # #endregion

    log(f"🎉 Done! Saved to: {output_folder}")

    album_url = None
    cloud = config.get("cloud_upload") or {}
    if cloud.get("enabled") and processed:
        try:
            album_url = maybe_cloud_upload(
                processed,
                config,
                progress_callback=progress_callback,
            )
            if album_url:
                log(f"🔗 Album link: {album_url}")
        except CloudUploadError as e:
            log(f"☁️ Upload failed: {e}")
        except Exception as e:
            log(f"☁️ Upload failed: {e}")
    elif cloud.get("enabled") and not processed:
        log("☁️ Skipping cloud upload — no successful exports")

    return {
        "output_folder": output_folder,
        "processed": processed,
        "failed": failed,
        "album_url": album_url,
    }
