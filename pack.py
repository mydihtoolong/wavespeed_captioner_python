#!/usr/bin/env python3
"""
pack.py — Resize + centre-crop images to 9:16, convert to PNG, pack into uncompressed ZIP.

Designed to be called by lora_tool.py, but also runnable standalone:
    python pack.py --dir ./lora-db
    python pack.py --dir ./lora-db --height 1500

Resize-then-crop logic (works for ANY source aspect ratio — 1:1, 16:9, 9:21, etc.):
    1. Compute scale = max(target_w / src_w, target_h / src_h)
       This is the smallest scale factor that makes BOTH dimensions >= target,
       i.e. the image "covers" the target box without any letterboxing.
    2. Resize the image using that scale (LANCZOS).
       After this step the image is always >= target in both dimensions.
    3. Centre-crop to exactly target_w × target_h.
       Excess pixels are trimmed equally from both sides.

Examples at height=1000 (target 562×1000):
    9:21 portrait 2000×4667  → scale to 562×1311  → crop height → 562×1000
    1:1  square   4000×4000  → scale to 1000×1000 → crop width  → 562×1000
    16:9 landscape 3840×2160 → scale to 1778×1000 → crop width  → 562×1000

Output: <image_dir>/images_packed.zip  (ZIP_STORED — no compression)
"""

import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

# ── colour helpers ─────────────────────────────────────────────────────────
def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def cyan(t):   return _c("36", t)
def bold(t):   return _c("1",  t)
def red(t):    return _c("31", t)
def dim(t):    return _c("2",  t)


ZIP_FILENAME = "images_packed.zip"


def _crop_to_ratio(img, target_w: int, target_h: int):
    """
    Resize-then-centre-crop a PIL Image to exactly (target_w × target_h).

    Step 1 — Scale to cover: pick the scale factor that makes the image
    large enough in BOTH dimensions so no letterboxing is needed.
    Step 2 — Centre crop: trim the overflow equally from each side.
    """
    from PIL import Image

    src_w, src_h = img.size

    # Scale factor needed so that both dimensions are >= target
    scale = max(target_w / src_w, target_h / src_h)

    if scale != 1.0:
        new_w = max(round(src_w * scale), target_w)
        new_h = max(round(src_h * scale), target_h)
        resample = Image.LANCZOS
        img = img.resize((new_w, new_h), resample)

    # Centre crop
    src_w, src_h = img.size
    left = (src_w - target_w) // 2
    top  = (src_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def run_pack_pipeline(image_dir: Path, height: int = 1000):
    """Called by lora_tool.py (or standalone use)."""
    try:
        from PIL import Image
    except ImportError:
        print(red("  ✗ Pillow not installed. Run: pip install Pillow"))
        sys.exit(1)

    target_h = height
    target_w = round(target_h * 9 / 16)   # 9:16 → e.g. 562 × 1000

    images = sorted(
        [p for p in image_dir.iterdir()
         if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
    )
    if not images:
        print(red(f"  ✗ No images found in {image_dir}"))
        return

    zip_path = image_dir / ZIP_FILENAME

    print(f"  {dim(f'Target size: {target_w}×{target_h}  (9:16)  →  {zip_path.name}')}\n")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for idx, img_path in enumerate(images, 1):
            stem = img_path.stem
            out_name = stem + ".png"       # all outputs are PNG

            print(f"  [{idx}/{len(images)}] {img_path.name} → {out_name} ", end="", flush=True)

            try:
                img = Image.open(img_path)

                # Ensure RGB (handles palette / RGBA / greyscale)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")

                img = _crop_to_ratio(img, target_w, target_h)

                # Write PNG into memory, then straight into ZIP
                buf = BytesIO()
                img.save(buf, format="PNG", optimize=False)
                buf.seek(0)

                zf.writestr(out_name, buf.read())
                print(green("✓"))

            except Exception as e:
                print(red(f"✗ FAILED: {e}"))

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print()
    print(f"  {green('✓')} Packed {len(images)} images → {bold(zip_path.name)}  "
          f"{dim(f'({size_mb:.1f} MB)')}")
    print()


# ── standalone CLI ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Crop images to 9:16 and pack into an uncompressed ZIP.")
    parser.add_argument("--dir", "-d", type=Path, default=Path("lora-db"),
                        help="Directory containing images (default: ./lora-db)")
    parser.add_argument("--height", type=int, default=1000,
                        help="Target height in pixels (default: 1000). "
                             "Width is derived as height × 9/16.")
    args = parser.parse_args()

    image_dir = args.dir.resolve()
    if not image_dir.is_dir():
        print(red(f"  ✗ Not a directory: {image_dir}"))
        sys.exit(1)

    run_pack_pipeline(image_dir, height=args.height)
