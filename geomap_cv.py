#!/usr/bin/env python3
"""
GeoMap Lens - CV Preprocessor (Hybrid CV + LVM Architectural Fallback)
WID3013 Practical CV Skill Assignment | Arts & Social (Geography)

Performs a hybrid pipeline of traditional computer vision analysis on a map image,
supervised by a zero-shot Large Vision Model via OpenRouter when geometry structures fail.

  Step 1 - Image preprocessing (blur detection, CLAHE enhancement)
  Step 2 - Layout detection (Contour morphology + OpenRouter API Fallback)
  Step 3 - OCR (text extraction from map labels, legend, title)
  Step 4 - Colour analysis (K-Means clustering, choropleth detection)

Usage:
    python geomap_cv.py <image_path>
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
import json
import os
import cv2
import base64
import http.client
import numpy as np
from PIL import Image

# ── CONFIGURATION PARAMETERS ──────────────────────────────────────────────────
OPENROUTER_API_KEY = "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"

# ── Tesseract path configuration ───────────────────────────────────────────
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if sys.platform != "win32":
    TESSERACT_PATH = "/opt/homebrew/bin/tesseract" if os.path.exists("/opt/homebrew/bin/tesseract") else "/usr/local/bin/tesseract"

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
# OPENROUTER LVM COORDINATE CALLOUT
# ────────────────────────────────────────────────────────────────────────────
def query_lvm_layout_fallback(image_path):
    """
    Queries Gemini via OpenRouter using zero-shot vision grounding.
    Cleanses output text cleanly to guarantee robust JSON dictionary transformation.
    """
    print("  [API] Querying OpenRouter Vision Model for spatial ground truth correction...")
    
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("sk-or-..."):
        print("  [API] WARNING: Missing valid OpenRouter API Key. Skipping LVM pass.")
        return None

    try:
        with open(image_path, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        
        ext = os.path.splitext(image_path)[1].lower().replace(".", "")
        mime_type = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "webp"] else "image/jpeg"

        system_instruction = (
            "You are a computer vision bounding box engine. Locate the 'title', 'legend', and 'scale_bar' "
            "components on the map image. Return coordinates normalized to a 1000x1000 grid where top-left "
            "is [0, 0] and bottom-right is [1000, 1000]. Format strictly as a JSON object containing keys "
            "'title', 'legend', 'scale_bar' mapped to [ymin, xmin, ymax, xmax]. "
            "If a component is missing, return null for its value. Output raw JSON text only."
        )
        
        user_prompt = (
            "Analyze this map. Identify and locate the bounding boxes for 'title', 'legend', and 'scale_bar'. "
            "Output JSON format example: "
            '{"title": [10, 20, 90, 800], "legend": [200, 700, 600, 950], "scale_bar": [850, 650, 920, 950]}'
        )

        payload = json.dumps({
            "model": "google/gemini-2.5-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{system_instruction}\n\n{user_prompt}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_base64}"}
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        })

        headers = {
            'Authorization': f'Bearer {OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://localhost',
            'X-Title': 'GeoMap Lens'
        }

        conn = http.client.HTTPSConnection("openrouter.ai")
        conn.request("POST", "/api/v1/chat/completions", payload, headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        conn.close()

        response_json = json.loads(data)
        raw_text = response_json['choices'][0]['message']['content'].strip()
        
        # --- ROBUST TEXT CLEANING REGEX-ALTERNATIVE ---
        # Strip away markdown block indicators if returned by the model
        if "```" in raw_text:
            raw_text = raw_text.split("```")
            # Pull the segment following the json indicator
            for segment in raw_text:
                cleaned = segment.replace("json", "").strip()
                if cleaned.startswith("{") and cleaned.endswith("}"):
                    raw_text = cleaned
                    break

        return json.loads(raw_text)

    except Exception as e:
        print(f"  [API] LVM Processing Exception Encountered: {e}")
        return None

# ────────────────────────────────────────────────────────────────────────────
# STEP 1 — IMAGE PREPROCESSING
# ────────────────────────────────────────────────────────────────────────────

def step1_preprocess(img):
    print("\n[Step 1] Image Preprocessing")
    print("  Technique: Laplacian variance (blur detection) + CLAHE (contrast enhancement)")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    quality = "Good" if blur_score > 100 else "Poor — image may be too blurry"
    print(f"  Blur score (Laplacian variance): {blur_score:.2f}")
    print(f"  Image quality assessment      : {quality}")

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_gray = clahe.apply(gray)
    print("  CLAHE contrast enhancement    : Applied (clipLimit=2.0, tileGridSize=8x8)")

    return {
        "blur_score": round(blur_score, 2),
        "image_quality": quality,
        "enhancement_applied": "CLAHE"
    }, enhanced_gray, gray


# ────────────────────────────────────────────────────────────────────────────
# STEP 2 — HYBRID LAYOUT DETECTION (CV + LVM CORRECTION LAYER)
# ────────────────────────────────────────────────────────────────────────────
def step2_layout_detection(img, enhanced_gray, image_path):
    print("\n[Step 2] Layout Detection")
    print("  Technique: Traditional CV Contours with Validated LVM Overrides")

    h, w = img.shape[:2]
    bboxes = {"title": None, "legend": None, "scale_bar": None}
    
    # 1. Run traditional CV code pathway (Required)
    v = np.median(enhanced_gray)
    edges = cv2.Canny(enhanced_gray, int(max(0, 0.66 * v)), int(min(255, 1.33 * v)))
    macro_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, macro_kernel)
    cv_contours, _ = cv2.findContours(dilated_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    large_contours = [c for c in cv_contours if 150 < cv2.contourArea(c) < (w * h * 0.90)]
    large_contours = sorted(large_contours, key=cv2.contourArea, reverse=True)

    # Base traditional geometry calculations 
    for c in large_contours:
        cx, cy, cw, ch = cv2.boundingRect(c)
        if cy < h * 0.12 and cw > w * 0.35 and ch < h * 0.15:
            bboxes["title"] = (cx, cy, cw, ch)
            break
            
    for c in large_contours:
        cx, cy, cw, ch = cv2.boundingRect(c)
        aspect = cw / max(ch, 1)
        if (cx > w * 0.50) and (cy < h * 0.70) and (cw > 60 and ch > 60) and (0.35 < aspect < 2.5):
            bboxes["legend"] = (cx, cy, cw, ch)
            break

    # 2. Query LVM corrections
    lvm_data = query_lvm_layout_fallback(image_path)
    
    used_api_override = False
    if lvm_data:
        print("  [API] LVM Bounding Box coordinates received. Running validation gates...")
        
        for target in ["title", "legend", "scale_bar"]:
            box = lvm_data.get(target)
            if box and isinstance(box, list) and len(box) == 4:
                ymin, xmin, ymax, xmax = box
                
                # Convert from the normalized 1000x1000 scale to raw pixels
                lx = int(xmin * w / 1000)
                ly = int(ymin * h / 1000)
                lw = int((xmax - xmin) * w / 1000)
                lh = int((ymax - ymin) * h / 1000)
                
                # Enforce safety boundaries
                lx, ly = max(0, lx), max(0, ly)
                lw, lh = min(w - lx, lw), min(h - ly, lh)
                
                if lw <= 0 or lh <= 0:
                    continue

                # ── GEOMETRIC VALIDATION GATES ──
                # Crop the edge map to see if the LVM picked up an empty white void
                roi_edges = edges[ly:ly+lh, lx:lx+lw]
                edge_density = np.sum(roi_edges > 0) / (lw * lh) if (lw * lh) > 0 else 0

                if target == "title":
                    # If edge density is incredibly low, it's just empty background space
                    if edge_density < 0.01:
                        print(f"  [Gate Reject] Title rejected. Edge density ({edge_density:.4f}) indicates empty space.")
                        continue
                    bboxes["title"] = (lx, ly, lw, lh)

                elif target == "scale_bar":
                    # A scale bar shouldn't occupy more than 20% of the entire map height
                    if lh > (h * 0.20):
                        print("[Gate Reject] Scale bar rejected. Too tall; likely caught on a continent border.")
                        continue
                    bboxes["scale_bar"] = (lx, ly, lw, lh)
                    used_api_override = True

                elif target == "legend":
                    if bboxes[target] is None:
                        bboxes[target] = (lx, ly, lw, lh)

    print(f"  Title area final state        : {'Yes' if bboxes['title'] else 'Not detected'}")
    print(f"  Legend box final state         : {'Yes' if bboxes['legend'] else 'Not detected'}")
    print(f"  Scale bar final state         : {'Yes (LVM Forced Override Applied)' if used_api_override else ('Yes (CV Native)' if bboxes['scale_bar'] else 'Not detected')}")

    return {
        "total_raw_cv_contours": len(cv_contours),
        "significant_cv_regions": len(large_contours),
        "title_region_detected": bboxes["title"] is not None,
        "legend_detected": bboxes["legend"] is not None,
        "scale_bar_detected": bboxes["scale_bar"] is not None,
        "lvm_api_override_applied": used_api_override
    }, bboxes
# ────────────────────────────────────────────────────────────────────────────
# STEP 3 — OCR TEXT EXTRACTION
# ────────────────────────────────────────────────────────────────────────────

def step3_ocr(enhanced_gray):
    print("\n[Step 3] OCR Text Extraction")
    print("  Technique: pytesseract OCR (PSM 11 - sparse text mode)")

    if not TESSERACT_AVAILABLE:
        print("  STATUS: SKIPPED — pytesseract not installed")
        return {"status": "skipped", "reason": "pytesseract not installed"}

    try:
        pil_img = Image.fromarray(enhanced_gray)
        raw = pytesseract.image_to_string(pil_img, config="--psm 11")
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip() and len(ln.strip()) > 1]

        print(f"  Text lines extracted          : {len(lines)}")
        for ln in lines[:5]:
            print(f"    → \"{ln}\"")

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
    print("\n[Step 4] Colour Analysis")
    print("  Technique: K-Means clustering (k=5) on RGB pixel values")

    if not SKLEARN_AVAILABLE:
        print("  STATUS: SKIPPED — scikit-learn missing")
        return {"status": "skipped"}

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    body = img_rgb[int(h * 0.1):int(h * 0.9), int(w * 0.1):int(w * 0.9)]
    pixels = body.reshape(-1, 3).astype(np.float32)

    if len(pixels) > 10000:
        idx = np.random.choice(len(pixels), 10000, replace=False)
        pixels = pixels[idx]

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
        print(f"    #{rank+1}: {hex_val}  →  {pct}% of map area")

    color_variance = float(np.std([c["rgb"] for c in dominant_colors], axis=0).mean())
    choropleth = bool(color_variance > 30)
    print(f"  Colour variance across clusters: {color_variance:.2f}")
    print(f"  Choropleth/gradient detected  : {'YES' if choropleth else 'NO'}")

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
    print("\n[Step 5] Generating Annotated Image")
    
    annotated = img.copy()
    h, w = annotated.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX

    region_style = {
        "title":     {"color": (255, 180,   0), "label": "TITLE AREA"},
        "legend":    {"color": (  0, 200,   0), "label": "LEGEND"},
        "scale_bar": {"color": (  0, 165, 255), "label": "SCALE BAR"},
    }

    for region, bbox in bboxes.items():
        if bbox is None:
            print(f"  {region:<10} : not detected — skipping visual overlay box")
            continue
        x, y, bw, bh = bbox
        color = region_style[region]["color"]
        label = region_style[region]["label"]

        cv2.rectangle(annotated, (x, y), (x + bw, y + bh), color, 2)
        (tw, th), _ = cv2.getTextSize(label, font, 0.5, 1)
        pill_y = max(y - th - 6, 0)
        cv2.rectangle(annotated, (x, pill_y), (x + tw + 8, pill_y + th + 6), color, -1)
        cv2.putText(annotated, label, (x + 4, pill_y + th + 2), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        print(f"  {region:<10} : box successfully plotted at x={x}, y={y}")

    if colour_results.get("status") == "success":
        swatch_h = 36
        colors = colour_results["dominant_colors"]
        strip = np.zeros((swatch_h, w, 3), dtype=np.uint8)
        sw = w // len(colors)

        for i, c in enumerate(colors):
            r, g, b = c["rgb"]
            x1 = i * sw
            x2 = x1 + sw if i < len(colors) - 1 else w
            strip[:, x1:x2] = [b, g, r]
            text_color = (255, 255, 255) if (r*0.299 + g*0.587 + b*0.114) < 128 else (0, 0, 0)
            cv2.putText(strip, f"{c['hex']} {c['coverage_percent']}%", (x1 + 6, 22), font, 0.38, text_color, 1, cv2.LINE_AA)

        annotated = np.vstack([annotated, strip])

    out_path = os.path.splitext(image_path)[0] + "_annotated.png"
    cv2.imwrite(out_path, annotated)
    print(f"  Saved → {out_path}")
    return out_path


def classify_map(ocr_results, color_results):
    text_lines = ocr_results.get("extracted_lines", [])
    all_text = " ".join(text_lines).lower()

    if any(kw in all_text for kw in ["population", "density", "/km", "inhabitants", "people"]):
        return "Population / Demographic Choropleth"
    if any(kw in all_text for kw in ["elevation", "contour", "metres", "feet", "altitude", "topograph"]):
        return "Topographic"
    if any(kw in all_text for kw in ["temperature", "rainfall", "precipitation", "climate", "weather", "vulnerability"]):
        return "Climate / Weather / Vulnerability"
    if any(kw in all_text for kw in ["gdp", "income", "economic", "trade", "export", "economy"]):
        return "Economic / Thematic"
    if color_results.get("choropleth_detected"):
        return "Thematic / Choropleth (type unspecified — no keyword match)"
    return "Physical / Political (or unknown)"


# ────────────────────────────────────────────────────────────────────────────
# MAIN LOOP CONTROL INTERACTION
# ────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python geomap_cv.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"Error: File not found — {image_path}")
        sys.exit(1)

    print("=" * 62)
    print("  GEOMAP LENS — Hybrid CV + LVM Preprocessor")
    print(f"  File : {image_path}")
    print("=" * 62)

    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: OpenCV could not read image — {image_path}")
        sys.exit(1)

    h, w = img.shape[:2]
    print(f"\nImage loaded: {w} x {h} pixels")

    # Pipeline Chain execution paths
    preprocess, enhanced_gray, gray = step1_preprocess(img)
    layout, bboxes = step2_layout_detection(img, enhanced_gray, image_path)
    ocr = step3_ocr(enhanced_gray)
    colours = step4_colour_analysis(img)
    annotated_path = step5_annotate(img, bboxes, colours, image_path)
    map_type = classify_map(ocr, colours)

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

    print("\n" + "=" * 62)
    print("  CV ANALYSIS SUMMARY — paste this into Telegram")
    print("=" * 62)
    print(f"  [CV Results from geomap_cv.py]")
    print(f"  Map type estimate  : {map_type}")
    print(f"  Image quality      : {preprocess['image_quality']} (blur={preprocess['blur_score']})")
    print(f"  Enhancement        : {preprocess['enhancement_applied']}")
    print(f"  Regions detected   : {layout['significant_cv_regions']}")
    print(f"  Legend detected    : {layout['legend_detected']}")
    print(f"  Scale bar detected : {layout['scale_bar_detected']}")
    print(f"  LVM Guard Corrected: {layout['lvm_api_override_applied']}")
    
    if ocr.get("status") == "success":
        print(f"  OCR lines found    : {ocr['line_count']}")
        if ocr["extracted_lines"]:
            print(f"  Sample text        : {', '.join(ocr['extracted_lines'][:4])}")
    if colours.get("status") == "success":
        top = colours["dominant_colors"][0]
        print(f"  Top colour         : {top['hex']} ({top['coverage_percent']}% coverage)")
        print(f"  Choropleth pattern : {colours['choropleth_detected']}")
    print("=" * 62)

    out_path = os.path.splitext(image_path)[0] + "_cv_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull JSON results saved to: {out_path}")


if __name__ == "__main__":
    main()