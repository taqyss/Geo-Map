# Geo-Map

WID3013 Practical CV Skill Assignment — Arts & Social (Geography)

Telegram bot that takes a photo of a map (choropleth, topographic, physical, political, climate, etc.) and returns:

- An annotated image showing detected regions (title area, legend, scale bar) and dominant colour swatches
- A structured academic-style report covering map classification, detected features, extracted text, colour analysis, and an academic summary

It combines a traditional computer vision pipeline (OpenCV, pytesseract, scikit-learn) with an LLM (via OpenRouter) for the final report generation.

## How it works

```
Telegram photo
      │
      ▼
   bot.py            (receives photo, triggers pipeline)
      │
      ▼
run_pipeline.py
      │
      ├── Step 1: geomap_cv.py   (OpenCV/pytesseract/sklearn — blur check, CLAHE,
      │                            layout detection, OCR, K-Means colour analysis,
      │                            annotated image output)
      │
      ├── Step 2: OpenRouter API (vision LLM, prompted with SKILL.md + CV results
      │                            + map image → generates the report)
      │
      └── Step 3: Telegram Bot API (sends original image, annotated image,
                                      and report back to the user)
```

## Files in this repo

| File | Purpose |
|---|---|
| `bot.py` | Telegram bot entry point. Listens for photos, downloads them, runs the pipeline, cleans up temp files. |
| `run_pipeline.py` | Orchestrates the full pipeline: CV processing → LLM report → Telegram reply. |
| `geomap_cv.py` | Standalone CV script. Can be run directly on any image (`python geomap_cv.py <image>`) for testing without Telegram. |
| `SKILL.md` | System prompt / instructions for the LLM report-generation step. Defines the report format, classification rules, and ethical boundaries (e.g. no political claims on contested borders). |

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Tesseract OCR (separate from the pip package)

`pytesseract` is just a Python wrapper — you need the Tesseract binary installed separately.

- **Windows**: download from https://github.com/UB-Mannheim/tesseract/wiki
  If `pytesseract` can't find it automatically, set the path in `geomap_cv.py`:
  ```python
  TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
  ```
- **macOS**: `brew install tesseract`
- **Linux**: `sudo apt install tesseract-ocr`

### 3. Get your API keys

- **OpenRouter API key**: sign up at https://openrouter.ai and create a key (starts with `sk-or-...`)
- **Telegram bot token**: message [@BotFather](https://t.me/BotFather) on Telegram, create a new bot, copy the token
- **Telegram chat ID**: the numeric ID of the chat the bot should reply to (you can get this from the bot's `getUpdates` response after messaging it once, or via [@userinfobot](https://t.me/userinfobot) for your own user ID)

### 4. Fill in credentials

Open `run_pipeline.py` and `bot.py` and fill in the empty config strings at the top of each file:

**`run_pipeline.py`**
```python
OPENROUTER_API_KEY = "sk-or-..."
TELEGRAM_BOT_TOKEN = "123456:ABC-..."
TELEGRAM_CHAT_ID   = "123456789"
```

**`bot.py`**
```python
BOT_TOKEN = "123456:ABC-..."   # must match TELEGRAM_BOT_TOKEN above
```

**Never commit real tokens to GitHub.** If you accidentally push a token, regenerate it immediately via BotFather / OpenRouter dashboard — treat it as compromised.

### 5. Run the bot

```bash
python bot.py
```

Send `/start` to your bot on Telegram for instructions, then send a photo of a map.

## Running the CV step standalone (for testing)

You don't need Telegram or an API key to test the CV pipeline on its own:

```bash
python geomap_cv.py path/to/map.png
```

This prints all CV results to the terminal and saves:
- `<name>_annotated.png` — image with detected regions boxed and colour swatches
- `<name>_cv_results.json` — full structured results

## Running the full pipeline standalone (no Telegram)

```bash
python run_pipeline.py path/to/map.png
```

This runs CV → LLM report generation → prints the report, then attempts to send to Telegram (requires valid Telegram credentials in config; will fail gracefully on the Telegram step if not configured, but CV + report will still print).

## Choosing an LLM model

`run_pipeline.py` sets:

```python
MODEL = "google/gemini-2.5-flash"
```

Any **vision-capable** model on OpenRouter works. Model availability changes over time — if you get a `404 No endpoints found` error, check https://openrouter.ai/models?modality=text%2Bimage-%3Etext for currently available models and update `MODEL` accordingly.

## Known limitations

- **Title area detection** is a fixed heuristic (always assumes the top 15% of the image), regardless of whether a title is actually present there.
- **Legend box detection** uses geometric heuristics (corner position, aspect ratio, size) and can mismatch on maps where landmass shapes happen to satisfy the same criteria (e.g. picking a chunk of Indonesia instead of the actual legend in the opposite corner). Legend *content* via OCR is generally reliable even when the bounding box is wrong.
- **OCR quality** depends heavily on image resolution and font size — small map labels may not be captured.
- **Colour analysis** requires `scikit-learn`; if not installed, this step is skipped and the map type classification falls back to keyword-based rules only.

## Troubleshooting

**`UnicodeEncodeError: 'charmap' codec can't encode...` (Windows)**
Caused by Windows console using cp1252 instead of UTF-8. Fixed by setting `PYTHONIOENCODING=utf-8` when running scripts/subprocesses. Already handled in `bot.py`'s subprocess call — if running scripts manually in a terminal, run `set PYTHONIOENCODING=utf-8` first (Windows cmd).

**`404 No endpoints found for <model>`**
The model in `MODEL` (in `run_pipeline.py`) has been deprecated/removed from OpenRouter. Swap to a currently available vision model (see "Choosing an LLM model" above).

**Pipeline exits with code 1 and no clear error in bot logs**
Run `run_pipeline.py` directly from a terminal on the same image — the bot's subprocess capture can swallow some error details, but running directly shows the full traceback.
