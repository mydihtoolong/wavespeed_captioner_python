# LoRA Dataset Tool

**Automatically caption training images and pack them for LoRA fine-tuning — powered by [WaveSpeed AI](https://wavespeed.ai).**

Uploads your images to WaveSpeed's CDN, generates detailed text captions via the `wavespeed-ai/image-captioner` model, and optionally crops + packs everything into a training-ready ZIP. Works on Windows, macOS, and Linux.

---

## What it does

1. **Uploads** every `.jpg` / `.png` in your `lora-db/` folder to WaveSpeed's CDN and caches the URLs locally (re-uploads only when the 7-day TTL expires)
2. **Captions** each image by calling the WaveSpeed image-captioner API and writes a `.txt` file next to each image (`IMG_001.jpg` → `IMG_001.txt`)
3. **Packs** (optional) — resizes images to a target height, centre-crops to 9:16, converts to PNG, and bundles everything into an uncompressed `.zip`

---

## Requirements

- **Python 3.10 or newer** — download from [python.org](https://www.python.org/downloads/)
- A **WaveSpeed API key** — get one free at [wavespeed.ai/accesskey](https://wavespeed.ai/accesskey)
- Internet connection (for upload + captioning)

---

## Installation

### Option A — Automatic (recommended)

Run the one-shot installer. It creates a virtual environment, installs all dependencies (`wavespeed`, `Pillow`, `python-dotenv`), and sets up the `lora-db/` folder:

```bash
python install.py
```

That's it. Follow the on-screen instructions at the end.

### Option B — Manual

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows CMD
.venv\Scripts\activate.bat

# Windows PowerShell
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install wavespeed>=1.0.8 Pillow>=10.0.0 python-dotenv>=1.0.0

# 3. Create the image directory
mkdir lora-db
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your details:

```bash
cp .env.example .env
```

```dotenv
# Required
WAVESPEED_API_KEY=your_api_key_here

# Caption settings (passed to wavespeed-ai/image-captioner)
CAPTION_FOCUS=general          # e.g. general, objects, people, text, colors
CAPTION_DETAIL_LEVEL=medium    # low | medium | high

# Rate limiting — increase if you see 429 errors
API_SLEEP_SECONDS=2.0
```

> **Never commit `.env` to version control.** The installer adds it to `.gitignore` automatically.

---

## Usage

### Typical workflow

```bash
# Activate your venv first (see above), then:
python lora_tool.py
```

The tool will:
1. Show you what images it found in `lora-db/`
2. Upload any that aren't cached (or whose cache has expired)
3. Generate captions, writing `IMG_001.txt` next to each `IMG_001.jpg`
4. Ask if you want to pack the images into a ZIP

### All CLI flags

```bash
# Point at a different image directory (default is ./lora-db)
python lora_tool.py --dir ./my-photos

# Skip captioning, go straight to the pack prompt
python lora_tool.py --skip-caption

# Skip the pack prompt entirely
python lora_tool.py --skip-pack
```

### Run steps standalone

```bash
# Caption only
python caption.py --dir ./lora-db

# Re-caption everything, even if .txt files already exist
python caption.py --dir ./lora-db --force

# Pack only (default height = 1000 px → output is 562×1000)
python pack.py --dir ./lora-db

# Pack at a custom height
python pack.py --dir ./lora-db --height 1500
```

---

## Directory layout

After a full run your project will look like this:

```
project/
├── install.py              ← run once to set everything up
├── lora_tool.py            ← main entrypoint
├── caption.py              ← upload + caption logic (also standalone)
├── pack.py                 ← resize/crop + zip logic (also standalone)
├── requirements.txt
├── .env                    ← your secrets — never commit this
├── .env.example            ← template
└── lora-db/
    ├── IMG_001.jpg
    ├── IMG_001.txt         ← generated caption
    ├── IMG_002.png
    ├── IMG_002.txt
    ├── .upload_cache.json  ← tracks CDN URLs and upload timestamps
    └── images_packed.zip   ← output of the pack step
```

---

## How the upload cache works

After each upload, `lora-db/.upload_cache.json` stores:

| Field | Description |
|---|---|
| `url` | WaveSpeed CDN URL for this image |
| `uploaded_at` | ISO-8601 timestamp of the upload |
| `captioned_at` | Timestamp of the last successful caption |
| `wavespeed_task_id` | Task ID returned by WaveSpeed (for auditing) |
| `local_correlation_id` | Short UUID generated per run (for local tracing) |

On every run the tool checks whether each cached URL is **younger than 7 days** — WaveSpeed's CDN storage TTL. If the URL has expired, the image is re-uploaded automatically before captioning.

---

## Crop logic (pack step)

The pack step uses a **resize-then-centre-crop** approach that works correctly for any source aspect ratio — square, ultra-wide, ultra-tall:

1. Compute the scale factor that makes the image cover the target box without letterboxing: `scale = max(target_w / src_w, target_h / src_h)`
2. Resize with LANCZOS resampling
3. Centre-crop the overflow to exactly `target_w × target_h`

Examples at the default `--height 1000` (target: 562 × 1000):

| Source | After resize | After crop |
|---|---|---|
| 9:21 portrait 2000×4667 | 562×1311 | **562×1000** |
| 1:1 square 4000×4000 | 1000×1000 | **562×1000** |
| 16:9 landscape 3840×2160 | 1778×1000 | **562×1000** |

All outputs are saved as **PNG** regardless of the original format. The ZIP uses `ZIP_STORED` (no compression) for maximum trainer compatibility.

---

## Troubleshooting

**`WAVESPEED_API_KEY is not set`** — Make sure you've copied `.env.example` to `.env` and filled in your key. The `.env` file must be in the same directory as `lora_tool.py`.

**`429 Too Many Requests`** — Increase `API_SLEEP_SECONDS` in your `.env` (try `5.0`).

**Caption file is empty or garbled** — The raw API response will be logged. Check your `CAPTION_FOCUS` and `CAPTION_DETAIL_LEVEL` values match what the WaveSpeed playground accepts.

**Pack produces blurry images** — The resize uses LANCZOS, which is the highest-quality downsampling filter available in Pillow. If source images are very low resolution you may want to source higher-res originals before running the pack step.

**`venv` not found on Windows** — Make sure you installed Python from [python.org](https://www.python.org/downloads/) and ticked "Add Python to PATH" during installation.

---

## License

MIT
