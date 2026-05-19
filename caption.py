#!/usr/bin/env python3
"""
caption.py — Upload images to WaveSpeed CDN and generate captions.

Designed to be called by lora_tool.py, but also runnable standalone:
    python caption.py --dir ./lora-db

Cache file: <image_dir>/.upload_cache.json
  {
    "IMG_001.jpg": {
      "url": "https://...",
      "uploaded_at": "2026-05-19T12:00:00",
      "wavespeed_task_id": "task_abc123"   ← stored per caption run
    }
  }
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
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


# ── constants ──────────────────────────────────────────────────────────────
CACHE_FILENAME  = ".upload_cache.json"
MODEL_ID        = "wavespeed-ai/image-captioner"
URL_TTL_DAYS    = 7          # WaveSpeed keeps uploaded files for 7 days
DEFAULT_SLEEP   = 2.0        # seconds between API calls (overridden by .env)


# ── cache helpers ──────────────────────────────────────────────────────────

def load_cache(image_dir: Path) -> dict:
    cache_path = image_dir / CACHE_FILENAME
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print(yellow("  ⚠  Cache file corrupt or unreadable — starting fresh."))
    return {}


def save_cache(image_dir: Path, cache: dict):
    cache_path = image_dir / CACHE_FILENAME
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def url_still_valid(entry: dict) -> bool:
    """Return True if the cached upload URL is less than 7 days old."""
    uploaded_at_str = entry.get("uploaded_at", "")
    if not uploaded_at_str:
        return False
    try:
        uploaded_at = datetime.fromisoformat(uploaded_at_str)
        # Make timezone-aware if naive
        if uploaded_at.tzinfo is None:
            uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - uploaded_at
        return age < timedelta(days=URL_TTL_DAYS)
    except ValueError:
        return False


# ── upload phase ───────────────────────────────────────────────────────────

def upload_images(images: list[Path], image_dir: Path, cache: dict) -> dict:
    """
    Upload all images that either:
    - Have no cache entry, OR
    - Have a cache entry but the URL is older than URL_TTL_DAYS.

    Returns the updated cache dict.
    """
    import wavespeed

    to_upload = []
    for img in images:
        key = img.name
        entry = cache.get(key, {})
        if not entry or not url_still_valid(entry):
            reason = "(never uploaded)" if not entry else "(URL expired)"
            to_upload.append((img, reason))

    if not to_upload:
        print(green("  ✓ All images have valid cached URLs — skipping upload."))
        return cache

    print(f"  Uploading {bold(str(len(to_upload)))} image(s) to WaveSpeed CDN...\n")

    for img, reason in to_upload:
        print(f"  ↑  {img.name} {dim(reason)} ", end="", flush=True)
        try:
            url = wavespeed.upload(str(img))
            cache[img.name] = {
                "url": url,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "wavespeed_task_id": None,  # filled in after caption
            }
            save_cache(image_dir, cache)
            print(green("✓"))
        except Exception as e:
            print(red(f"✗ FAILED: {e}"))
            print(red(f"     Skipping {img.name} — no URL available."))

    print()
    return cache


# ── caption phase ──────────────────────────────────────────────────────────

def extract_caption_text(output: object) -> str:
    """
    Robustly extract text from wavespeed.run() output.

    The SDK returns whatever the model outputs under output["outputs"].
    For image-captioner this is a list with one text string.
    We handle edge cases gracefully.
    """
    # Standard path: output is a dict with "outputs" list
    if isinstance(output, dict):
        outputs = output.get("outputs", [])
        if outputs and isinstance(outputs[0], str):
            return outputs[0].strip()
        # Fallback: join all string outputs
        parts = [o for o in outputs if isinstance(o, str)]
        if parts:
            return " ".join(parts).strip()
        # Last resort: dump the whole dict as a string for debugging
        return json.dumps(output, ensure_ascii=False)

    # Sometimes SDKs return a bare string or list
    if isinstance(output, str):
        return output.strip()
    if isinstance(output, list) and output:
        return str(output[0]).strip()

    return str(output).strip()


def caption_images(
    images: list[Path],
    image_dir: Path,
    cache: dict,
    focus: str,
    detail_level: str,
    force: bool,
    sleep_seconds: float,
):
    """Run the image-captioner for each image that lacks a .txt file."""
    import wavespeed

    pending = []
    for img in images:
        txt_path = img.with_suffix(".txt")
        if force or not txt_path.exists():
            url = cache.get(img.name, {}).get("url")
            if url:
                pending.append((img, url))
            else:
                print(yellow(f"  ⚠  No URL for {img.name} — was upload skipped? Skipping caption."))

    if not pending:
        print(green("  ✓ All images already have caption files. Use --force to re-caption."))
        return

    print(f"  Captioning {bold(str(len(pending)))} image(s)...\n")
    print(f"  {dim('Settings:')} focus={bold(focus)}  detail_level={bold(detail_level)}\n")

    for idx, (img, url) in enumerate(pending, 1):
        txt_path = img.with_suffix(".txt")
        local_id = str(uuid.uuid4())[:8]   # short internal correlation ID

        print(f"  [{idx}/{len(pending)}] {img.name}  {dim(f'id={local_id}')} ", end="", flush=True)

        payload = {
            "image": url,
            "focus": focus,
            "detail_level": detail_level,
            "disable_safety_checker": True,
            "enable_sync_mode": False,     # SDK polls; we don't need sync mode
        }

        try:
            output = wavespeed.run(MODEL_ID, payload)
            caption = extract_caption_text(output)

            # Save caption to .txt
            txt_path.write_text(caption, encoding="utf-8")

            # Store the wavespeed task ID in cache for auditability
            # The SDK's run() returns a dict; task id may be under "id" or "task_id"
            task_id = None
            if isinstance(output, dict):
                task_id = output.get("id") or output.get("task_id") or output.get("request_id")

            if img.name in cache:
                cache[img.name]["wavespeed_task_id"] = task_id
                cache[img.name]["captioned_at"] = datetime.now(timezone.utc).isoformat()
                cache[img.name]["local_correlation_id"] = local_id
            save_cache(image_dir, cache)

            print(green("✓"))
            print(f"     {dim(caption[:120] + ('...' if len(caption) > 120 else ''))}")

        except Exception as e:
            print(red(f"✗ FAILED"))
            print(red(f"     {e}"))

        # Rate-limit guard — sleep between all calls except after the last one
        if idx < len(pending):
            time.sleep(sleep_seconds)

    print()


# ── public entry point ─────────────────────────────────────────────────────

def run_caption_pipeline(image_dir: Path, force: bool = False):
    """Called by lora_tool.py (or standalone use)."""
    from dotenv import load_dotenv
    load_dotenv(Path(".env"))   # no-op if missing

    # ── config from environment ────────────────────────────────────────────
    api_key = os.environ.get("WAVESPEED_API_KEY", "").strip()
    if not api_key:
        print(red("  ✗ WAVESPEED_API_KEY not set."))
        sys.exit(1)

    os.environ["WAVESPEED_API_KEY"] = api_key   # SDK reads this env var

    focus        = os.environ.get("CAPTION_FOCUS", "general").strip()
    detail_level = os.environ.get("CAPTION_DETAIL_LEVEL", "medium").strip()
    sleep_str    = os.environ.get("API_SLEEP_SECONDS", str(DEFAULT_SLEEP)).strip()

    try:
        sleep_seconds = float(sleep_str)
    except ValueError:
        print(yellow(f"  ⚠  API_SLEEP_SECONDS='{sleep_str}' is not a number. Using {DEFAULT_SLEEP}s."))
        sleep_seconds = DEFAULT_SLEEP

    # ── gather images ──────────────────────────────────────────────────────
    images = sorted(
        [p for p in image_dir.iterdir()
         if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
    )
    if not images:
        print(red(f"  ✗ No images found in {image_dir}"))
        return

    print(f"  {dim('focus='+ focus + '  detail_level=' + detail_level + '  sleep=' + str(sleep_seconds) + 's')}\n")

    # ── phase 1: upload ────────────────────────────────────────────────────
    print(bold("  Phase 1 — Upload"))
    cache = load_cache(image_dir)
    cache = upload_images(images, image_dir, cache)

    # ── phase 2: caption ───────────────────────────────────────────────────
    print(bold("  Phase 2 — Caption"))
    caption_images(images, image_dir, cache, focus, detail_level, force, sleep_seconds)

    # Summary
    captioned = [img for img in images if img.with_suffix(".txt").exists()]
    print(f"  {green('✓')} {len(captioned)}/{len(images)} images captioned.")
    print(f"  {dim('Caption files written to:')} {image_dir}\n")


# ── standalone CLI ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Caption images via WaveSpeed image-captioner.")
    parser.add_argument("--dir", "-d", type=Path, default=Path("lora-db"),
                        help="Directory containing images (default: ./lora-db)")
    parser.add_argument("--force", action="store_true",
                        help="Re-caption images that already have .txt files.")
    args = parser.parse_args()

    image_dir = args.dir.resolve()
    if not image_dir.is_dir():
        print(red(f"  ✗ Not a directory: {image_dir}"))
        sys.exit(1)

    run_caption_pipeline(image_dir, force=args.force)
