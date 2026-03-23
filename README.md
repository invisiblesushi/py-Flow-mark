# FlowMark

FlowMark is a lightweight Python script for batch watermarking images with text and exporting them as high-quality JPG files.

## What It Does

- Adds a custom text watermark to each image.
- Preserves image orientation using EXIF transpose.
- Converts output to JPG with high quality (default: 98).
- Processes images in parallel with configurable thread count.
- Saves results to a dedicated output folder.

## Requirements

- Python 3.9+
- [Pillow](https://pillow.readthedocs.io/)

## Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/<your-username>/FlowMark.git
   cd FlowMark
   ```

2. Create and activate a virtual environment:

   Windows (PowerShell):
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   macOS/Linux:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install pillow
   ```

## Usage

Run the script:

```bash
python flowmark.py
```

You will be prompted for:

1. Input folder path (images to process)
2. Watermark text
3. Optional custom output folder
4. Number of threads (default: 4)

## Supported Input Formats

- `.jpg`
- `.jpeg`
- `.png`

## Output

- All processed files are exported as `.jpg`.
- By default, output goes to `<input_folder>/output`.

## Project Structure

```text
FlowMark/
  flowmark.py
  icons_/                 # optional assets (not used by current script)
  ATTRIBUTION.txt
  .gitignore
  README.md
```

## Notes

- Watermark position is currently near the bottom area of the image.
- If `arial.ttf` is not available, Pillow's default font is used.

## Attribution

If you use assets in `icons_/`, review and keep attribution details from `ATTRIBUTION.txt`.

## License

No project license is defined yet. Add a `LICENSE` file before publishing if you want others to reuse your code.
