#!/usr/bin/env python3
"""
GeoMap Lens - Full Pipeline Runner (Option C)
WID3013 Practical CV Skill Assignment

Fully automated end-to-end pipeline:
  Step 1 — CV processing (geomap_cv.py)
  Step 2 — LLM report generation (OpenRouter API, vision model)
  Step 3 — Send image + report to Telegram (Bot API)

Usage:
    python run_pipeline.py <image_path>
    python run_pipeline.py worldmap.png
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
import os
import json
import base64
import subprocess
import requests

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# Fill these in before running.

OPENROUTER_API_KEY = ""   # sk-or-...
TELEGRAM_BOT_TOKEN = ""   # from BotFather
TELEGRAM_CHAT_ID   = ""     # your numeric Telegram user ID

# Vision-capable model via OpenRouter — Gemini Flash is fast and cheap
MODEL = "google/gemini-2.5-flash"

# Path to geomap_cv.py — assumes it is in the same folder as this script
GEOMAP_CV_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geomap_cv.py")
# Load SKILL.md as the LLM system prompt
_skill_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")
with open(_skill_path, encoding="utf-8", errors="replace") as f:
    SKILL_SYSTEM_PROMPT = f.read()

# ─────────────────────────────────────────────────────────────────────────────


def check_config():
    """Validate configuration before running."""
    missing = []
    if "YOUR_" in OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if "YOUR_" in TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if "YOUR_" in TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if not os.path.exists(GEOMAP_CV_SCRIPT):
        missing.append(f"geomap_cv.py not found at: {GEOMAP_CV_SCRIPT}")
    if missing:
        print("ERROR: Fill in the following in the CONFIGURATION section:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — CV PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def step1_cv_processing(image_path):
    """Run geomap_cv.py as a subprocess and return structured JSON results."""
    print("\n" + "─" * 50)
    print("[Step 1] Running CV preprocessing (geomap_cv.py)")
    print("─" * 50)

    result = subprocess.run(
        [sys.executable, GEOMAP_CV_SCRIPT, image_path],
        capture_output=True,
        text=True,
        timeout=120
    )

    print(result.stdout)

    if result.returncode != 0:
        print(f"[WARNING] CV script exited with error:\n{result.stderr}")

    # Load JSON results saved by geomap_cv.py
    json_path = os.path.splitext(image_path)[0] + "_cv_results.json"
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)

    print("[WARNING] No JSON results file found. Continuing without structured CV data.")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — LLM REPORT GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def build_cv_summary(cv_results):
    """Format CV results into a readable summary for the LLM prompt."""
    if not cv_results:
        return "[No CV results available — using visual analysis only]"

    pre     = cv_results.get("step1_preprocessing", {})
    layout  = cv_results.get("step2_layout", {})
    ocr     = cv_results.get("step3_ocr", {})
    colours = cv_results.get("step4_colour_analysis", {})

    lines = [
        "[CV Preprocessing Results — geomap_cv.py]",
        f"Map type estimate  : {cv_results.get('map_type_estimate', 'Unknown')}",
        f"Image dimensions   : {cv_results.get('dimensions', 'N/A')}",
        "",
        "Step 1 — Preprocessing (Laplacian variance + CLAHE):",
        f"  Blur score       : {pre.get('blur_score', 'N/A')}",
        f"  Image quality    : {pre.get('image_quality', 'N/A')}",
        f"  Enhancement      : {pre.get('enhancement_applied', 'N/A')}",
        "",
        "Step 2 — Layout Detection (Canny edges + contour analysis):",
        f"  Significant regions : {layout.get('significant_regions', 'N/A')}",
        f"  Legend detected     : {layout.get('legend_detected', 'N/A')}",
        f"  Legend location     : {layout.get('legend_location', 'N/A')}",
        f"  Scale bar detected  : {layout.get('scale_bar_detected', 'N/A')}",
    ]

    if ocr.get("status") == "success":
        lines += [
            "",
            "Step 3 — OCR Text Extraction (pytesseract PSM 11):",
            f"  Lines extracted  : {ocr.get('line_count', 0)}",
            f"  Sample text      : {', '.join(ocr.get('extracted_lines', [])[:8])}",
        ]
    else:
        lines += ["", f"Step 3 — OCR: {ocr.get('status', 'skipped')}"]

    if colours.get("status") == "success":
        top = colours.get("dominant_colors", [{}])[0]
        lines += [
            "",
            "Step 4 — Colour Analysis (K-Means k=5):",
            f"  Top colour       : {top.get('hex', 'N/A')} — {top.get('coverage_percent', 'N/A')}% coverage",
            f"  Colour variance  : {colours.get('color_variance', 'N/A')}",
            f"  Choropleth       : {colours.get('choropleth_detected', 'N/A')}",
            "  All dominant colours:",
        ]
        for c in colours.get("dominant_colors", []):
            lines.append(f"    #{c['rank']}: {c['hex']}  RGB{tuple(c['rgb'])}  {c['coverage_percent']}%")
    else:
        lines += ["", f"Step 4 — Colour Analysis: {colours.get('status', 'skipped')}"]

    return "\n".join(lines)


def encode_image(image_path):
    """Encode image as base64 for the OpenRouter API."""
    ext = os.path.splitext(image_path)[1].lower()
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".bmp": "image/bmp"
    }.get(ext, "image/jpeg")

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return b64, media_type


def step2_llm_report(image_path, cv_results):
    """Call LLM via OpenRouter with the image + CV results to generate the academic report."""
    print("\n" + "─" * 50)
    print("[Step 2] Calling LLM via OpenRouter")
    print(f"  Model: {MODEL}")
    print("─" * 50)

    cv_summary = build_cv_summary(cv_results)
    img_b64, media_type = encode_image(image_path)

    prompt = f"""You are GeoMap Lens, a geography map analysis assistant for Arts and Social (Geography) university students.

A map image has been pre-processed using a traditional computer vision pipeline with four steps:
- Step 1: Blur detection (Laplacian variance) and CLAHE contrast enhancement (OpenCV)
- Step 2: Layout detection using Canny edge detection and contour analysis (OpenCV)
- Step 3: OCR text extraction in sparse text mode PSM 11 (pytesseract)
- Step 4: Dominant colour identification using K-Means clustering with k=5 (scikit-learn)

The CV pipeline produced these results:

{cv_summary}

Using the CV results above AND your visual analysis of the attached map image, generate a complete GeoMap Lens academic report in the following format. Do not skip any section.

MAP ANALYSIS REPORT
═══════════════════════════════════════

MAP CLASSIFICATION
Map Type      : [Choropleth / Topographic / Physical / Political / Climate / Unknown]
Map Title     : [extracted from OCR or visual read, or "Not detected"]
Year / Source : [if visible, or "Not detected"]

DETECTED FEATURES
Title Area          : [Detected / Not detected]
Legend Box          : [Detected / Not detected] — Labels: [list categories if found]
Scale Bar           : [Detected / Not detected]
Compass Rose        : [Detected / Not detected]
Handwritten Notes   : [X detected / None]

EXTRACTED TEXT
Place Names         : [list from OCR + visual]
Legend Categories   : [list]
Additional Labels   : [any other text]

COLOUR ANALYSIS
Dominant Colours    : [list hex codes from CV step 4]
Choropleth Pattern  : [Yes / No, based on CV colour variance]
Most Prominent Zone : [what the top colour corresponds to in the legend]

ACADEMIC SUMMARY
[Write 2 to 3 paragraphs in academic tone, suitable for a geography student to include in an assignment or field report. Describe the map type, what data it encodes, spatial patterns visible, and what geographic insights can be drawn from it.]

UNCERTAINTY FLAGS
[List any features that could not be confidently detected, with a brief reason such as low image quality, missing legend, or dense overlapping text.]"""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openclaw.ai",
            "X-OpenRouter-Title": "GeoMap Lens"
        },
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": SKILL_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{img_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            "max_tokens": 2000
        },
        timeout=120
    )

    if response.status_code != 200:
        print(f"  ERROR: {response.status_code} — {response.text}")
        return None

    report = response.json()["choices"][0]["message"]["content"]
    print(f"  Report generated — {len(report)} characters")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — SEND TO TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────

def step3_send_telegram(image_path, report):
    """Send the map image and generated report to Telegram via Bot API."""
    print("\n" + "─" * 50)
    print("[Step 3] Sending to Telegram")
    print("─" * 50)

    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    # Send map image with caption
    with open(image_path, "rb") as img_file:
        r = requests.post(
            f"{base_url}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": "GeoMap Lens — Map Analysis Report"},
            files={"photo": img_file},
            timeout=30
        )
    if r.status_code == 200:
        print("  Map image sent ✓")
    else:
        print(f"  Failed to send image: {r.text}")

    # Send annotated CV detection image
    annotated_path = os.path.splitext(image_path)[0] + "_annotated.png"
    if os.path.exists(annotated_path):
        with open(annotated_path, "rb") as img_file:
            r = requests.post(
                f"{base_url}/sendPhoto",
                data={
                    "chat_id":  TELEGRAM_CHAT_ID,
                    "caption":  "GeoMap Lens — CV Detection (annotated regions + colour swatches)"
                },
                files={"photo": img_file},
                timeout=30
            )
        if r.status_code == 200:
            print("  Annotated image sent ✓")
        else:
            print(f"  Failed to send annotated image: {r.text}")
    else:
        print("  Annotated image not found — skipping")

    # Send report — split into 4000-char chunks (Telegram limit is 4096)
    chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
    for i, chunk in enumerate(chunks):
        r = requests.post(
            f"{base_url}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
            timeout=30
        )
        if r.status_code == 200:
            print(f"  Report part {i+1}/{len(chunks)} sent ✓")
        else:
            print(f"  Failed to send part {i+1}: {r.text}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py <image_path>")
        print("Example: python run_pipeline.py worldmap.png")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"Error: File not found — {image_path}")
        sys.exit(1)

    print("=" * 62)
    print("  GEOMAP LENS — Full Pipeline (Option C)")
    print(f"  Image : {image_path}")
    print(f"  Model : {MODEL}")
    print("=" * 62)

    check_config()

    # Step 1 — CV processing
    cv_results = step1_cv_processing(image_path)

    # Step 2 — LLM report generation
    report = step2_llm_report(image_path, cv_results)
    if not report:
        print("\nPipeline stopped — LLM call failed.")
        sys.exit(1)

    # Print report in terminal
    print("\n" + "=" * 62)
    print("  GENERATED REPORT")
    print("=" * 62)
    print(report)

    # Step 3 — Send to Telegram
    step3_send_telegram(image_path, report)

    print("\n" + "=" * 62)
    print("  Pipeline complete. Check your Telegram.")
    print("=" * 62)


if __name__ == "__main__":
    main()
