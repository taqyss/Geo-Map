#!/usr/bin/env python3
"""
GeoMap Lens - Telegram Bot Entry Point
WID3013 Practical CV Skill Assignment

Listens for incoming map photos in Telegram.
On receiving a photo:
  1. Downloads the image to disk
  2. Triggers run_pipeline.py (CV → LLM → Telegram reply)
  3. Cleans up temp file after pipeline completes

Usage:
    python bot.py

Requirements:
    pip install python-telegram-bot
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
import os
import subprocess
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# Must match the token in run_pipeline.py

BOT_TOKEN = ""   # from BotFather

# Path to run_pipeline.py — assumes same folder as this script
PIPELINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_pipeline.py")

# Folder to save received images before processing
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "received_images")

# ─────────────────────────────────────────────────────────────────────────────

# Set up logging so errors and activity are visible in the terminal
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def check_config():
    """Validate configuration before starting the bot."""
    errors = []
    if "YOUR_" in BOT_TOKEN:
        errors.append("BOT_TOKEN is not set — fill it in at the top of bot.py")
    if not os.path.exists(PIPELINE_SCRIPT):
        errors.append(f"run_pipeline.py not found at: {PIPELINE_SCRIPT}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /start with usage instructions."""
    await update.message.reply_text(
        "👋 Welcome to GeoMap Lens!\n\n"
        "Send me any geography map image and I will:\n"
        "  1️⃣  Run CV analysis (blur, layout, OCR, colour)\n"
        "  2️⃣  Generate an academic map report\n"
        "  3️⃣  Send you the annotated image + full report\n\n"
        "Just send a photo to get started."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Core handler — triggered when a photo is sent to the bot.
    Downloads the image, runs the full pipeline, then cleans up.
    """
    chat_id = update.message.chat_id
    logger.info(f"Photo received from chat_id={chat_id}")

    # ── Acknowledge receipt immediately ──────────────────────────────────────
    await update.message.reply_text(
        "🗺️ Map received! Running CV analysis...\n"
        "This may take 20–40 seconds depending on image size."
    )

    # ── Download the highest-resolution version of the photo ─────────────────
    photo   = update.message.photo[-1]          # last element = largest size
    file    = await context.bot.get_file(photo.file_id)
    img_path = os.path.join(DOWNLOAD_DIR, f"{photo.file_id}.jpg")

    try:
        await file.download_to_drive(img_path)
        logger.info(f"Image saved → {img_path}")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        await update.message.reply_text(
            "❌ Failed to download the image. Please try again."
        )
        return

    # ── Run the full pipeline as a subprocess ────────────────────────────────
    # run_pipeline.py handles Steps 1–3 (CV → LLM → Telegram send)
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [sys.executable, PIPELINE_SCRIPT, img_path],
            timeout=300,           # 5-minute hard timeout
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env
        )

        if result.returncode == 0:
            logger.info("Pipeline completed successfully")
        else:
            logger.warning(f"Pipeline exited with code {result.returncode}")
            logger.warning(result.stderr)
            await update.message.reply_text(
                "⚠️ Pipeline finished with warnings. "
                "Check the terminal for details.\n\n"
                "You may still have received a partial report above."
            )

    except subprocess.TimeoutExpired:
        logger.error("Pipeline timed out after 300 seconds")
        await update.message.reply_text(
            "⏱️ Analysis timed out. "
            "Try a smaller or clearer image."
        )

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        await update.message.reply_text(
            f"❌ An error occurred: {e}"
        )

    finally:
        # ── Clean up downloaded image and generated files ─────────────────────
        for suffix in ["", "_cv_results.json", "_annotated.png"]:
            path = os.path.splitext(img_path)[0] + suffix + (
                ".jpg" if suffix == "" else ""
            )
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Cleaned up: {path}")


async def handle_non_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Politely redirect users who send text or documents instead of a photo."""
    await update.message.reply_text(
        "Please send a map as a *photo* (not a file/document).\n"
        "In Telegram: tap the 📎 icon → Photo.",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    check_config()

    print("=" * 62)
    print("  GEOMAP LENS — Telegram Bot")
    print(f"  Pipeline : {PIPELINE_SCRIPT}")
    print(f"  Downloads: {DOWNLOAD_DIR}")
    print("=" * 62)
    print("  Bot is running. Send a map photo to Telegram.")
    print("  Press Ctrl+C to stop.")
    print("=" * 62)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_non_photo))

    app.run_polling()


if __name__ == "__main__":
    main()
