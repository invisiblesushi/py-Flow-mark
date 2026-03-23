import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- Image Processing Functions ----------

def add_text_watermark(image, text="", opacity=150, padding=25, margin=10):
    """
    Add a text watermark (no icon).
    Bottom-right aligned with padding and margin.
    Works on both vertical and horizontal images.
    """
    watermark_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark_layer)

    # Text font size = 2% of image width
    font_size = max(12, int(image.width * 0.03))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Bottom-right position with padding + margin
    x = (image.width - text_width) / 2
    y = image.height - text_height - padding - margin

    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return Image.alpha_composite(image.convert("RGBA"), watermark_layer)


def compress_image(image, output_path, quality=98):
    """
    Compress image and save as JPEG at 98% quality,
    preserving EXIF metadata.
    """
    exif_data = image.info.get('exif')

    # Convert RGBA to RGB (fill transparent areas with white)
    rgb_image = Image.new("RGB", image.size, (255, 255, 255))
    rgb_image.paste(image, mask=image.split()[3] if image.mode == 'RGBA' else None)

    if exif_data:
        rgb_image.save(output_path, "JPEG", optimize=True, quality=quality, exif=exif_data)
    else:
        rgb_image.save(output_path, "JPEG", optimize=True, quality=quality)


# ---------- Worker Function ----------

def process_image(file, output_folder, watermark_text):
    """Process a single image file."""
    try:
        image = Image.open(file)
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGBA")

        # Add watermark
        image = add_text_watermark(image, watermark_text)

        # Save as JPG
        output_path = output_folder / (file.stem + ".jpg")
        compress_image(image, output_path, quality=98)

        return f"✅ {file.name}"
    except Exception as e:
        return f"❌ {file.name} failed: {e}"


# ---------- Folder Processor (Multithreaded) ----------

def process_folder(input_folder, watermark_text="", output_folder=None, max_workers=4):
    """Process all images with text watermark using multithreading."""
    input_folder = Path(input_folder)

    # Use custom output path if given, else default to input_folder/output
    if output_folder:
        output_folder = Path(output_folder)
    else:
        output_folder = input_folder / "output"

    output_folder.mkdir(parents=True, exist_ok=True)

    images = [f for f in input_folder.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
    if not images:
        print("⚠️ No images found in this folder.")
        return

    total = len(images)
    print(f"🧵 Starting multithreaded processing with {max_workers} workers...")
    print(f"📸 Found {total} images\n")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_image, f, output_folder, watermark_text): f for f in images}
        for i, future in enumerate(as_completed(futures), 1):
            print(f"[{i}/{total}] {future.result()}")

    print(f"\n🎉 Done! All {total} images saved in: {output_folder}")


# ---------- Main Script ----------

if __name__ == "__main__":
    print("\n=== 🖼️ FlowMark - Multithreaded Text Watermark Tool ===\n")

    folder = input("Input folder path to process images: ").strip()
    if not os.path.isdir(folder):
        print("❌ Invalid folder path.")
        exit()

    watermark_text = input("Enter watermark text (default: © FlowMark): ").strip() or ""

    output_folder = input("Enter custom output folder (leave blank for default 'output' subfolder): ").strip()
    output_folder = output_folder if output_folder else None

    try:
        workers = int(input("Number of threads (default: 4): ").strip() or 4)
    except ValueError:
        workers = 4

    process_folder(folder, watermark_text=watermark_text, output_folder=output_folder, max_workers=workers)
