#!/usr/bin/env python3
"""
LoRA Dataset Tool — CLI entrypoint.
Run from the parent directory of lora-db/ (or point --dir at any image folder).

Usage:
    python lora_tool.py
    python lora_tool.py --dir ./my-images
    python lora_tool.py --dir ./lora-db --skip-caption
    python lora_tool.py --dir ./lora-db --skip-pack
"""

import argparse
import os
import sys
from pathlib import Path

# ── colour helpers (no deps) ───────────────────────────────────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def cyan(t):   return _c("36", t)
def bold(t):   return _c("1",  t)
def red(t):    return _c("31", t)


def print_banner():
    print()
    print(bold("╔══════════════════════════════════════╗"))
    print(bold("║      LoRA Dataset Preparation Tool   ║"))
    print(bold("╚══════════════════════════════════════╝"))
    print()


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        ans = input(cyan(prompt + suffix)).strip().lower()
        if ans == "":
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print(yellow("  Please answer y or n."))


def find_images(directory: Path) -> list[Path]:
    images = sorted(
        [p for p in directory.iterdir()
         if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
    )
    return images


def check_env():
    """Verify .env is loadable and WAVESPEED_API_KEY is present."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print(red("  ✗ python-dotenv not installed. Run: pip install python-dotenv"))
        sys.exit(1)

    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print(yellow("  ⚠  No .env file found in current directory. "
                     "WAVESPEED_API_KEY must be set in environment."))

    key = os.environ.get("WAVESPEED_API_KEY", "").strip()
    if not key:
        print(red("  ✗ WAVESPEED_API_KEY is not set. "
                  "Add it to .env or export it in your shell."))
        sys.exit(1)
    return key


def run_caption(image_dir: Path):
    """Import and execute the caption module."""
    from caption import run_caption_pipeline
    run_caption_pipeline(image_dir)


def run_pack(image_dir: Path):
    """Import and execute the pack module."""
    from pack import run_pack_pipeline
    run_pack_pipeline(image_dir)


def main():
    parser = argparse.ArgumentParser(
        description="LoRA Dataset Tool — caption images and pack them for training.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dir", "-d",
        type=Path,
        default=Path("lora-db"),
        help="Directory containing images (default: ./lora-db)",
    )
    parser.add_argument(
        "--skip-caption",
        action="store_true",
        help="Skip the caption step entirely.",
    )
    parser.add_argument(
        "--skip-pack",
        action="store_true",
        help="Skip asking about packing at the end.",
    )
    args = parser.parse_args()

    print_banner()

    # ── resolve directory ──────────────────────────────────────────────────
    image_dir = args.dir.resolve()
    if not image_dir.exists():
        print(red(f"  ✗ Directory not found: {image_dir}"))
        sys.exit(1)
    if not image_dir.is_dir():
        print(red(f"  ✗ Not a directory: {image_dir}"))
        sys.exit(1)

    print(f"  {bold('Image directory:')} {cyan(str(image_dir))}")

    images = find_images(image_dir)
    if not images:
        print(red(f"  ✗ No .png/.jpg files found in {image_dir}"))
        sys.exit(1)

    print(f"  {bold('Images found:')} {green(str(len(images)))}\n")
    for img in images:
        print(f"    • {img.name}")
    print()

    # ── caption step ───────────────────────────────────────────────────────
    if not args.skip_caption:
        print(bold("── Step 1: Caption Images ─────────────────────────────"))
        print()

        # Check how many already have captions
        already_captioned = [img for img in images
                             if img.with_suffix(".txt").exists()]
        pending = [img for img in images
                   if not img.with_suffix(".txt").exists()]

        if already_captioned:
            print(f"  {yellow(str(len(already_captioned)))} image(s) already have .txt captions.")
        if pending:
            print(f"  {green(str(len(pending)))} image(s) need captioning.\n")
        else:
            print(f"  {green('All images already captioned!')}")
            if not confirm("  Re-caption all images anyway?", default=False):
                print(yellow("  Skipping caption step.\n"))
                args.skip_caption = True

        if not args.skip_caption:
            check_env()
            run_caption(image_dir)
    else:
        print(yellow("  [--skip-caption] Skipping caption step.\n"))

    # ── pack step ─────────────────────────────────────────────────────────
    if not args.skip_pack:
        print()
        print(bold("── Step 2: Pack Images ────────────────────────────────"))
        print()

        # Check for existing zip
        zip_path = image_dir / "images_packed.zip"
        if zip_path.exists():
            print(yellow(f"  ⚠  Found existing pack: {zip_path.name}"))
            if not confirm("  Overwrite existing zip?", default=False):
                print(yellow("  Skipping pack step.\n"))
                args.skip_pack = True

        if not args.skip_pack:
            if confirm("  Pack images into an uncompressed zip?", default=True):
                run_pack(image_dir)
            else:
                print(yellow("  Skipping pack step."))
    else:
        print(yellow("  [--skip-pack] Skipping pack step.\n"))

    print()
    print(bold(green("  ✓ All done!")))
    print()


if __name__ == "__main__":
    main()
