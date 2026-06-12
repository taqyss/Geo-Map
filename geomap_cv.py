#!/usr/bin/env python3
"""
GeoMap Lens - CV Preprocessor
WID3013 Practical CV Skill Assignment | Arts & Social (Geography)

Performs traditional computer vision analysis on a map image:
  Step 1 - Image preprocessing (blur detection, CLAHE enhancement)
  Step 2 - Layout detection (contour detection, legend/component localisation)
  Step 3 - OCR (text extraction from map labels, legend, title)
  Step 4 - Colour analysis (K-Means clustering, choropleth detection)

Usage:
    python geomap_cv.py <image_path>
    python geomap_cv.py worldmap.png
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
import json
import os
import cv2
import numpy as np
from PIL import Image

# ── Tesseract path for Windows ──────────────────────────────────────────────
# If pytesseract cannot find Tesseract, set the path manually here.
# Download Tesseract for Windows: https://github.com/UB-Mannheim/tesseract/wiki
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    import pytesseract
    if os.path.exists(TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ────────────────────────────────────────────────────────────────────────────
# STEP 1 — IMAGE PREPROCESSING
# ────────────────────────────────────────────────────────────────────────────

def step1_preprocess(img):
    """
    Blur detection using Laplacian variance.
    Contrast enhancement using CLAHE (Contrast Limited Adaptive Histogram Equalisation).
    """
    print("\n[Step 1] Image Preprocessing")
    print("  Technique: Laplacian variance (blur detection) + CLAHE (contrast enhancement)")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur detection — Laplacian variance
    # Higher value = sharper image. Below 100 = likely blurry.
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    quality = "Good" if blur_score > 100 else "Poor — image may be too blurry to process accurately"
    print(f"  Blur score (Laplacian variance): {blur_score:.2f}")
    print(f"  Image quality assessment      : {quality}")

    # CLAHE contrast enhancement
    # clipLimit controls contrast amplification; tileGridSize divides image into tiles
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(gray)
    print("  CLAHE contrast enhancement    : Applied (clipLimit=2.0, tileGridSize=8x8)")

    return {
        "blur_score": round(blur_score, 2),
        "image_quality": quality,
        "enhancement_applied": "CLAHE"
    }, enhanced_gray, gray


# ────────────────────────────────────────────────────────────────────────────
# STEP 2 — LAYOUT DETECTION
# ────────────────────────────────────────────────────────────────────────────

def step2_layout_detection(img, gray):
    """
    Canny edge detection + contour analysis to locate map components:
    title area, legend box, scale bar, compass rose.
    """
    print("\n[Step 2] Layout Detection")
    print("  Technique: Canny edge detection + contour analysis (cv2.findContours)")

    h, w = img.shape[:2]

    # Canny edge detection
    edges = cv2.Canny(gray, threshold1=50, threshold2=150)

    # Find contours from edges
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large_contours = [c for c in contours if cv2.contourArea(c) > 500]
    print(f"  Total contours detected       : {len(contours)}")
    print(f"  Significant regions (>500px²) : {len(large_contours)}")

    # Legend box detection — look for rectangular regions in bottom corners
    legend_detected = False
    legend_location = "Not detected"
    for c in large_contours:
        x, y, cw, ch = cv2.boundingRect(c)
        aspect = cw / max(ch, 1)
        in_bottom_corner = (x < w * 0.35 or x > w * 0.65) and (y > h * 0.55)
        reasonable_size = cw * ch > 1000
        reasonable_shape = 0.15 < aspect < 6
        if in_bottom_corner and reasonable_size and reasonable_shape:
            legend_detected = True
            legend_location = f"Region at x={x}, y={y}, size={cw}x{ch}px"
            break

    # Title area — assume top 15% of image
    title_region = f"Top 15% of image (0 to {int(h*0.15)}px)"

    # Scale bar — look for thin horizontal rectangle near bottom
    scale_detected = False
    for c in large_contours:
        x, y, cw, ch = cv2.boundingRect(c)
        is_horizontal = cw > ch * 3
        near_bottom = y > h * 0.75
        reasonable_width = w * 0.05 < cw < w * 0.3
        if is_horizontal and near_bottom and reasonable_width:
            scale_detected = True
            break

    print(f"  Title area                    : {title_region}")
    print(f"  Legend box                    : {legend_location}")
    print(f"  Scale bar detected            : {'Yes' if scale_detected else 'Not detected'}")

    # ── Build bboxes dict for annotation step ──
    bboxes = {
        "title":     (0, 0, w, int(h * 0.15)),   # always top 15%
        "legend":    None,
        "scale_bar": None,
    }

    # Re-run loops to capture coordinates (store during detection)
    for c in large_contours:
        x, y, cw, ch = cv2.boundingRect(c)
        aspect = cw / max(ch, 1)
        in_bottom_corner = (x < w * 0.35 or x > w * 0.65) and (y > h * 0.55)
        if in_bottom_corner and cw * ch > 1000 and 0.15 < aspect < 6:
            bboxes["legend"] = (x, y, cw, ch)
            break

    for c in large_contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw > ch * 3 and y > h * 0.75 and w * 0.05 < cw < w * 0.3:
            bboxes["scale_bar"] = (x, y, cw, ch)
            break

    return {
        "total_contours": len(contours),
        "significant_regions": len(large_contours),
        "title_region": title_region,
        "legend_detected": legend_detected,
        "legend_location": legend_location,
        "scale_bar_detected": scale_detected
    }, bboxes


# ────────────────────────────────────────────────────────────────────────────
# STEP 3 — OCR TEXT EXTRACTION
# ────────────────────────────────────────────────────────────────────────────

def step3_ocr(enhanced_gray):
    """
    Optical Character Recognition using pytesseract.
    PSM 11 (sparse text) is used because map text is scattered, not in columns.
    """
    print("\n[Step 3] OCR Text Extraction")
    print("  Technique: pytesseract OCR (PSM 11 - sparse text mode)")

    if not TESSERACT_AVAILABLE:
        print("  STATUS: SKIPPED — pytesseract not installed")
        print("  Install: pip install pytesseract")
        print("  Also install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki")
        return {"status": "skipped", "reason": "pytesseract not installed"}

    try:
        pil_img = Image.fromarray(enhanced_gray)
        # PSM 11 = sparse text, finds text anywhere in the image
        raw = pytesseract.image_to_string(pil_img, config="--psm 11")
        lines = [ln.strip() for ln in raw.split("\n")
                 if ln.strip() and len(ln.strip()) > 1]

        print(f"  Text lines extracted          : {len(lines)}")
        print("  Sample extracted text:")
        for ln in lines[:8]:
            print(f"    → \"{ln}\"")
        if len(lines) > 8:
            print(f"    ... and {len(lines) - 8} more lines")

        return {
            "status": "success",
            "line_count": len(lines),
            "extracted_lines": lines[:30]
        }

    except Exception as e:
        print(f"  STATUS: ERROR — {e}")
        return {"status": "error", "reason": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# STEP 4 — COLOUR ANALYSIS
# ────────────────────────────────────────────────────────────────────────────

def step4_colour_analysis(img):
    """
    K-Means clustering to identify dominant colours in the map body.
    Gradient/choropleth detection based on colour variance across clusters.
    """
    print("\n[Step 4] Colour Analysis")
    print("  Technique: K-Means clustering (k=5) on RGB pixel values")

    if not SKLEARN_AVAILABLE:
        print("  STATUS: SKIPPED — scikit-learn not installed")
        print("  Install: pip install scikit-learn")
        return {"status": "skipped", "reason": "scikit-learn not installed"}

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    # Focus on inner 80% of image to avoid border/whitespace
    body = img_rgb[int(h * 0.1):int(h * 0.9), int(w * 0.1):int(w * 0.9)]
    pixels = body.reshape(-1, 3).astype(np.float32)

    # Sample 10,000 pixels for performance
    if len(pixels) > 10000:
        idx = np.random.choice(len(pixels), 10000, replace=False)
        pixels = pixels[idx]

    print(f"  Pixels sampled for clustering : {len(pixels)}")

    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    kmeans.fit(pixels)

    centers = kmeans.cluster_centers_.astype(int)
    counts = np.bincount(kmeans.labels_)
    sorted_idx = np.argsort(-counts)

    dominant_colors = []
    print("  Dominant colours (by coverage):")
    for rank, i in enumerate(sorted_idx):
        r, g, b = centers[i]
        pct = round(counts[i] / len(pixels) * 100, 1)
        hex_val = f"#{r:02x}{g:02x}{b:02x}"
        dominant_colors.append({
            "rank": rank + 1,
            "hex": hex_val,
            "rgb": [int(r), int(g), int(b)],
            "coverage_percent": pct
        })
        print(f"    #{rank+1}: {hex_val}  RGB({r},{g},{b})  →  {pct}% of map area")

    # Choropleth/gradient detection
    # High variance across cluster centres = multiple distinct hues = likely choropleth
    color_variance = float(np.std([c["rgb"] for c in dominant_colors], axis=0).mean())
    choropleth = color_variance > 30
    print(f"  Colour variance across clusters: {color_variance:.2f}")
    print(f"  Choropleth/gradient detected  : {'YES — map likely uses colour to encode data' if choropleth else 'NO — single dominant hue or physical map'}")

    return {
        "status": "success",
        "dominant_colors": dominant_colors,
        "color_variance": round(color_variance, 2),
        "choropleth_detected": choropleth
    }

# ────────────────────────────────────────────────────────────────────────────
# STEP 5 — ANNOTATED IMAGE GENERATION
# ────────────────────────────────────────────────────────────────────────────

def step5_annotate(img, bboxes, colour_results, image_path):
    """
    Draw labelled bounding boxes on the original map image for each detected
    component (title, legend, scale bar). Append a colour swatch strip at the
    bottom showing K-Means dominant colours. Saves as <name>_annotated.png.
    """
    print("\n[Step 5] Generating Annotated Image")
    print("  Technique: cv2.rectangle + colour swatches from K-Means output")

    annotated = img.copy()
    h, w = annotated.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX

    # BGR colour per region type
    region_style = {
        "title":     {"color": (255, 180,   0), "label": "TITLE AREA"},
        "legend":    {"color": (  0, 200,   0), "label": "LEGEND"},
        "scale_bar": {"color": (  0, 165, 255), "label": "SCALE BAR"},
    }

    for region, bbox in bboxes.items():
        if bbox is None:
            print(f"  {region:<10} : not detected — skipping")
            continue
        x, y, bw, bh = bbox
        color = region_style[region]["color"]
        label = region_style[region]["label"]

        # Bounding box
        cv2.rectangle(annotated, (x, y), (x + bw, y + bh), color, 2)

        # Label pill above the box
        (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)
        pill_y = max(y - th - 6, 0)
        cv2.rectangle(annotated, (x, pill_y), (x + tw + 8, pill_y + th + 6), color, -1)
        cv2.putText(annotated, label, (x + 4, pill_y + th + 2),
                    font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        print(f"  {region:<10} : box drawn at x={x}, y={y}, {bw}x{bh}px")

    # ── Colour swatch strip ──────────────────────────────────────────────────
    if colour_results.get("status") == "success":
        swatch_h  = 36
        colors    = colour_results["dominant_colors"]
        strip     = np.zeros((swatch_h, w, 3), dtype=np.uint8)
        sw        = w // len(colors)

        for i, c in enumerate(colors):
            r, g, b = c["rgb"]
            x1 = i * sw
            x2 = x1 + sw if i < len(colors) - 1 else w
            strip[:, x1:x2] = [b, g, r]   # OpenCV is BGR
            cv2.putText(strip, f"{c['hex']}  {c['coverage_percent']}%",
                        (x1 + 4, 24), font, 0.38, (255, 255, 255), 1, cv2.LINE_AA)

        annotated = np.vstack([annotated, strip])
        print(f"  Colour swatch strip appended ({len(colors)} clusters)")

    # ── Mini legend (top-right corner) ──────────────────────────────────────
    lx, ly = w - 170, 10
    for i, (region, style) in enumerate(region_style.items()):
        yp = ly + i * 22
        cv2.rectangle(annotated, (lx, yp), (lx + 16, yp + 14), style["color"], -1)
        cv2.putText(annotated, style["label"], (lx + 22, yp + 11),
                    font, 0.4, style["color"], 1, cv2.LINE_AA)

    out_path = os.path.splitext(image_path)[0] + "_annotated.png"
    cv2.imwrite(out_path, annotated)
    print(f"  Saved → {out_path}")
    return out_path


# ────────────────────────────────────────────────────────────────────────────
# MAP TYPE CLASSIFICATION
# ────────────────────────────────────────────────────────────────────────────

def classify_map(ocr_results, color_results):
    """Rule-based map type classification from OCR keywords and colour analysis."""
    text_lines = ocr_results.get("extracted_lines", [])
    all_text = " ".join(text_lines).lower()

    if any(kw in all_text for kw in ["population", "density", "/km", "inhabitants", "people"]):
        return "Population / Demographic Choropleth"
    if any(kw in all_text for kw in ["elevation", "contour", "metres", "feet", "altitude", "topograph"]):
        return "Topographic"
    if any(kw in all_text for kw in ["temperature", "rainfall", "precipitation", "climate", "weather"]):
        return "Climate / Weather"
    if any(kw in all_text for kw in ["gdp", "income", "economic", "trade", "export"]):
        return "Economic / Thematic"
    if any(kw in all_text for kw in ["vegetation", "forest", "land use", "land cover"]):
        return "Vegetation / Land Use"
    if color_results.get("choropleth_detected"):
        return "Thematic / Choropleth (type unspecified — no keyword match)"
    return "Physical / Political (or unknown)"


# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python geomap_cv.py <image_path>")
        print("Example: python geomap_cv.py worldmap.png")
        sys.exit(1)

    image_path = sys.argv[1]

    if not os.path.exists(image_path):
        print(f"Error: File not found — {image_path}")
        sys.exit(1)

    print("=" * 62)
    print("  GEOMAP LENS — CV Preprocessor")
    print(f"  File : {image_path}")
    print("=" * 62)

    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: OpenCV could not read image — {image_path}")
        sys.exit(1)

    h, w = img.shape[:2]
    print(f"\nImage loaded: {w} x {h} pixels")

    # Run all CV steps
    preprocess, enhanced_gray, gray = step1_preprocess(img)
    layout, bboxes = step2_layout_detection(img, gray)
    ocr = step3_ocr(enhanced_gray)
    colours = step4_colour_analysis(img)
    annotated_path = step5_annotate(img, bboxes, colours, image_path)
    # Classify map type
    map_type = classify_map(ocr, colours)

    # Build final results
    results = {
        "source_image": image_path,
        "annotated_image": annotated_path,
        "dimensions": f"{w}x{h}",
        "map_type_estimate": map_type,
        "step1_preprocessing": preprocess,
        "step2_layout": layout,
        "step3_ocr": ocr,
        "step4_colour_analysis": colours
    }

    # ── Print summary for pasting into Telegram ──────────────────────────
    print("\n" + "=" * 62)
    print("  CV ANALYSIS SUMMARY — paste this into Telegram")
    print("=" * 62)
    summary_lines = [
        f"[CV Results from geomap_cv.py]",
        f"Map type estimate  : {map_type}",
        f"Image quality      : {preprocess['image_quality']} (blur={preprocess['blur_score']})",
        f"Enhancement        : {preprocess['enhancement_applied']}",
        f"Regions detected   : {layout['significant_regions']}",
        f"Legend detected    : {layout['legend_detected']}",
        f"Scale bar detected : {layout['scale_bar_detected']}",
    ]
    if ocr.get("status") == "success":
        summary_lines.append(f"OCR lines found    : {ocr['line_count']}")
        if ocr["extracted_lines"]:
            summary_lines.append(f"Sample text        : {', '.join(ocr['extracted_lines'][:5])}")
    if colours.get("status") == "success":
        top = colours["dominant_colors"][0]
        summary_lines.append(f"Top colour         : {top['hex']} ({top['coverage_percent']}% coverage)")
        summary_lines.append(f"Choropleth pattern : {colours['choropleth_detected']}")
        summary_lines.append(f"Colour variance    : {colours['color_variance']}")

    for line in summary_lines:
        print(f"  {line}")
    print("=" * 62)

    # Save full JSON
    out_path = os.path.splitext(image_path)[0] + "_cv_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull JSON results saved to: {out_path}")
    print("\nNext step: send the map image to your Telegram bot and")
    print("paste the [CV Results] block above into the same message.")


if __name__ == "__main__":
    main()
