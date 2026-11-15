"""Extraction for the two user-supplied Etterna theme screenshots.

Returns OCR evidence and crops. Does NOT reconstruct exact replay events.
"""
import csv
import io
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 30_000_000


def load_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be between 1 byte and 20 MB.")
    # Read dimensions before allocating OpenCV's decoded image; honor phone EXIF.
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(io.BytesIO(data)) as im:
        if im.width * im.height > MAX_PIXELS:
            raise ValueError("Image is too large (maximum 30 megapixels).")
        rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def crop(image, box):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError(f"Invalid normalized crop: {box}")
    return image[round(y1*h):round(y2*h), round(x1*w):round(x2*w)].copy()


def ocr(image, psm=6, threshold=None, whitelist=None, invert=False, scale_factor=None, padding=12, engine_override=None):
    from native_ocr import engine, recognize
    selected_engine = engine_override or engine()
    # RapidOCR mode is hybrid: retain Tesseract for broad text panels and
    # accuracy/grade; use neural recognition for isolated numeric fields below.
    if selected_engine == "apple_vision":
        # Vision receives original crop pixels, not a binarized/super-resolved image.
        return recognize(image, whitelist)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Upscaling aids OCR but does not recover missing detail.
    scale = scale_factor or max(1.0, min(3.0, 950 / max(gray.shape[1], 1)))
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if threshold is not None:
        gray = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)[1]
    if invert:
        gray = 255-gray
    gray = cv2.copyMakeBorder(gray, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=0)
    config = f"--psm {psm}" + (f" -c tessedit_char_whitelist={whitelist}" if whitelist else "")
    data = pytesseract.image_to_data(gray, config=config,
                                     output_type=pytesseract.Output.DICT, timeout=20)
    grouped = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        item = grouped.setdefault(key, {"words": [], "conf": []})
        item["words"].append(word)
        item["conf"].append(float(data["conf"][i]))
    lines = [{"text": " ".join(v["words"]),
              "ocr_confidence": round(float(np.mean(v["conf"])), 1)}
             for v in grouped.values()]
    return {"text": "\n".join(v["text"] for v in lines), "lines": lines, "engine": "tesseract"}


def judgment_evidence(screen, layout=None, trusted_geometry=False):
    """Find the six colored horizontal bands in this theme, then OCR each row.

    Thresholded white text separates the pale blue/yellow backgrounds from digits.
    Still require a readable label; row order alone never assigns a count.
    """
    if (layout or {}).get("name") == "etterna_4k_results_v2":
        return numeric_judgment_evidence(screen, trusted_geometry)
    search = (layout or {}).get("judgment_search", [.028, .42, .35, .73])
    area = crop(screen, search)
    h, w = area.shape[:2]
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    med = np.median(hsv[:, round(.02*w):round(.98*w)], axis=1)
    ys = np.flatnonzero((med[:, 1] > 45) & (med[:, 2] > 60))
    groups = np.split(ys, np.where(np.diff(ys) > 1)[0] + 1)
    lines = []
    for group in groups:
        if len(group) < screen.shape[0]*.012:
            continue
        panel = area[group[0]:group[-1]+1, :]
        row = ocr(panel, psm=7, threshold=190, invert=True)
        lines.extend(row["lines"])
    return {"text": "\n".join(line["text"] for line in lines), "lines": lines}


def camera_number_panel(panel):
    """Remove band borders/empty margins while preserving the observed digits."""
    h, w = panel.shape[:2]
    mask = cv2.inRange(cv2.cvtColor(panel, cv2.COLOR_BGR2HSV),
                       (0, 0, 170), (180, 140, 255))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    chars = stats[1:]
    chars = chars[(chars[:, cv2.CC_STAT_HEIGHT] > h*.25)
                  & (chars[:, cv2.CC_STAT_AREA] > 4)]
    if not len(chars):
        return panel
    x = int(chars[:, 0].min()); right = int((chars[:, 0]+chars[:, 2]).max())
    y = int(chars[:, 1].min()); bottom = int((chars[:, 1]+chars[:, 3]).max())
    return panel[max(0, y-3):min(h, bottom+3), max(0, x-10):min(w, right+4)]


def valid_count(reading):
    text = reading["text"].replace(" ", "")
    return bool(re.fullmatch(r"0|[1-9]\d{0,6}", text) and reading["lines"]
                and reading["lines"][0]["ocr_confidence"] >= 40)


def numeric_judgment_evidence(screen, trusted_geometry=False):
    # Vision's recognizer can return only part of a short digit string with
    # confidence 100 (observed: 679 -> 6, 215 -> "2 5"). Its confidence is not
    # proof that all digits were detected. Keep numeric crops on the tested
    # Tesseract path even when Vision is explicitly selected for text panels.
    def read_number(panel, **options):
        return ocr(panel, engine_override="tesseract", **options)

    lines, readings = [], []
    for index, label in enumerate(("Marvelous", "Perfect", "Great", "Good", "Bad", "Miss")):
        y1, y2 = .501 + index*.0473, .544 + index*.0473
        label_reading = ocr(crop(screen, [.05, y1, .235, y2]), psm=7)
        label_verified = bool(re.search(rf"\b{label}\b", label_reading["text"], re.I))
        # A verified homography also establishes which row belongs to which label;
        # requiring OCR of the label again discards readable counts on blurry photos.
        if not label_verified and not trusted_geometry:
            readings.append({"label": label, "label_ocr": label_reading, "number_ocr": None})
            continue
        panel = crop(screen, [.28, y1, .386, y2])
        camera_reading = None
        if trusted_geometry:
            camera_panel = camera_number_panel(panel)
            camera_reading = read_number(camera_panel, psm=7, whitelist="0123456789", scale_factor=2, padding=15)
            if not valid_count(camera_reading):
                camera_reading = read_number(camera_panel, psm=7, threshold=150, whitelist="0123456789", scale_factor=2, padding=15)
        # Locate bright, low-saturation digit strokes inside the numeric column.
        # Adaptive left edge preserves 4+ digit counts without excessive whitespace.
        ph, pw = panel.shape[:2]
        mask = cv2.inRange(cv2.cvtColor(panel, cv2.COLOR_BGR2HSV),
                           (0, 0, 200), (180, 100, 255))
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        chars = stats[1:]
        chars = chars[(chars[:, cv2.CC_STAT_HEIGHT] > ph*.25)
                      & (chars[:, cv2.CC_STAT_AREA] > 4)]
        if len(chars):
            left = max(0, int(chars[:, 0].min()) - round(.0075*screen.shape[1]))
            right = min(pw, int((chars[:, 0]+chars[:, 2]).max()) + round(.002*screen.shape[1]))
            panel = panel[:, left:right]
        number = read_number(panel, psm=7, whitelist="0123456789", scale_factor=4, padding=15)
        if (not re.fullmatch(r"\d+", number["text"].replace(" ", ""))
                or not number["lines"] or number["lines"][0]["ocr_confidence"] < 40):
            number = read_number(panel, psm=7, threshold=150, whitelist="0123456789", scale_factor=4, padding=15)
        if camera_reading is not None and valid_count(camera_reading):
            number = camera_reading
        if trusted_geometry:
            # The full row includes dark horizontal band edges. On a blurred
            # capture Tesseract can treat these as a leading 4 ("1" -> "41").
            # Read the interior independently, separating white digits from
            # the colored background. Keep this observation in the evidence.
            interior = crop(screen, [.28, y1+.006, .386, y2-.007])
            interior_reading = read_number(interior, psm=7, threshold=200,
                                   whitelist="0123456789", scale_factor=3, padding=15)
            if (valid_count(interior_reading)
                    and interior_reading["lines"][0]["ocr_confidence"] >=
                    (85 if valid_count(number) else 70)):
                number = interior_reading
        else:
            interior_reading = None
        digits = number["text"].replace(" ", "")
        readings.append({"label": label, "label_ocr": label_reading, "number_ocr": number,
                         "interior_ocr": interior_reading,
                         "label_source": "registered_layout" if trusted_geometry else "label_ocr"})
        if (re.fullmatch(r"0|[1-9]\d{0,6}", digits) and number["lines"]
                and number["lines"][0]["ocr_confidence"] >= 40):
            confidence = number["lines"][0]["ocr_confidence"]
            if not trusted_geometry:
                confidence = min(confidence, label_reading["lines"][0]["ocr_confidence"])
            lines.append({"text": f"{label} {digits}", "ocr_confidence": confidence})
    return {"text": "\n".join(line["text"] for line in lines), "lines": lines,
            "method": "separate_label_and_numeric_column", "numeric_engine": "tesseract", "readings": readings}


def anchors(text):
    return sum(bool(re.search(rf"\b{word}\b", text, re.I))
               for word in ("Marvelous", "Perfect", "Great", "Good", "Bad", "Miss"))


def rectify(image, points):
    h, w = image.shape[:2]
    p = np.asarray(points, dtype=np.float32)
    if p.shape != (4, 2) or not np.isfinite(p).all():
        raise ValueError("Provide four normalized corners in TL, TR, BR, BL order.")
    if np.any(p < 0) or np.any(p > 1):
        raise ValueError("Corner coordinates must be between zero and one.")
    p = p * [w-1, h-1]
    if not cv2.isContourConvex(p.astype(np.int32)):
        raise ValueError("Corners must form a convex quadrilateral in TL, TR, BR, BL order.")
    width = max(np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[3]))
    height = max(np.linalg.norm(p[3]-p[0]), np.linalg.norm(p[2]-p[1]))
    if width < 200 or height < 150:
        raise ValueError("Screen is too small; take a closer photo.")
    # Preserve the measured screen aspect ratio; normalized layout handles resolution.
    factor = min(1.0, 2000 / width)
    ow, oh = max(1, round(width*factor)), max(1, round(height*factor))
    dst = np.array([[0, 0], [ow-1, 0], [ow-1, oh-1], [0, oh-1]], np.float32)
    matrix = cv2.getPerspectiveTransform(p.astype(np.float32), dst)
    return cv2.warpPerspective(image, matrix, (ow, oh))


def screen_candidates(image):
    """Heuristic proposals only; each is checked against Etterna text anchors."""
    h, w = image.shape[:2]
    scale = min(1.0, 1200 / w)
    small = cv2.resize(image, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < small.shape[0]*small.shape[1]*0.15:
            continue
        poly = cv2.approxPolyDP(contour, 0.025*cv2.arcLength(contour, True), True)
        if len(poly) != 4 or not cv2.isContourConvex(poly):
            continue
        p = poly.reshape(4, 2).astype(np.float32)
        # Sort around centroid, start at top-left, ensure image-coordinate clockwise.
        center = p.mean(axis=0)
        p = p[np.argsort(np.arctan2(p[:, 1]-center[1], p[:, 0]-center[0]))]
        p = np.roll(p, -int(np.argmin(p.sum(axis=1))), axis=0)
        p = p / [small.shape[1]-1, small.shape[0]-1]
        if any(np.max(np.abs(p-q)) < 0.035 for q in candidates):
            continue
        candidates.append(p)
        if len(candidates) == 3:
            break
    return candidates


def field(value=None, line=None):
    return {"value": value, "raw": line["text"] if line else None,
            "ocr_confidence": line["ocr_confidence"] if line else None}


def parse_results(evidence):
    result = {"accuracy_percent": field(), "accuracy_label": field(),
              "judgments": {}, "timing": {}, "playback_rate": field(),
              "judge_setting": field(), "auxiliary_counts": {},
              "song_text": evidence["song_and_rate"]["text"],
              "unlabeled_ratings_text": [], "grade": field(),
              "wife_version": field(), "ratios_and_streaks": {}}
    for line in evidence.get("accuracy", evidence["results"])["lines"]:
        text = line["text"]
        if "accuracy" in evidence or re.search(r"wife|\bW\d\b", text, re.I):
            match = re.search(r"(\d{1,3}[.,]\d+)\s*%", text)
            if match:
                value = float(match[1].replace(",", "."))
                if 0 <= value <= 100:
                    result["accuracy_percent"] = field(value, line)
            result["accuracy_label"] = field(text, line)
            judge = re.search(r"\bJ\s*(\d+)\b", text, re.I)
            if judge:
                result["judge_setting"] = field(int(judge[1]), line)
            wife = re.search(r"\bW\s*(\d+)\b", text, re.I)
            if wife:
                result["wife_version"] = field(int(wife[1]), line)
        elif re.search(r"\d+[.,]\d+", text) and not re.search(
                r"marvelous|perfect|great|good|bad|miss|mini", text, re.I):
            result["unlabeled_ratings_text"].append(text)
    for label in ("marvelous", "perfect", "great", "good", "bad", "miss"):
        result["judgments"][label] = field()
        rows = evidence.get("judgment_rows", {"lines": []})
        # On the new layout, full-row OCR can merge counts with percentages.
        source_lines = rows["lines"] if rows.get("method") else rows["lines"] + evidence["results"]["lines"]
        for line in source_lines:
            match = re.search(rf"\b{label}\b\s*[:\-]?\s*(\d+)(?=\s|\[|\(|$)", line["text"], re.I)
            if match:
                result["judgments"][label] = field(int(match[1]), line)
                break
    names = {"mean_absolute_ms": r"mean\s*\(?\s*abs\s*\)?",
             "mean_ms": r"mean(?!\s*\(?\s*abs)",
             "standard_deviation_ms": r"sd",
             "smallest_ms": r"smallest", "largest_ms": r"largest",
             "left_cbs": r"left\s*cbs", "right_cbs": r"right\s*cbs"}
    for key, label in names.items():
        result["timing"][key] = field()
        for line in evidence["timing_stats"]["lines"]:
            match = re.search(rf"\b{label}\s*[:=]?\s*([+\-−]?\d+(?:[.,]\d+)?)\s*(?:ms)?\s*$",
                              line["text"], re.I)
            if match:
                value = float(match[1].replace(",", ".").replace("−", "-"))
                result["timing"][key] = field(int(value) if key.endswith("cbs") else value, line)
                break
    for label in ("holds", "mines", "rolls", "lifts", "fakes"):
        result["auxiliary_counts"][label] = field()
        for line in evidence["auxiliary_counts"]["lines"]:
            match = re.search(rf"\b{label}\b\s*(\d+)\s*/\s*(\d+)", line["text"], re.I)
            if match:
                result["auxiliary_counts"][label] = field(
                    {"first": int(match[1]), "second": int(match[2])}, line)
                break
    for line in evidence["song_and_rate"]["lines"]:
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*[xX×]\s*", line["text"])
        if match:
            result["playback_rate"] = field(float(match[1].replace(",", ".")), line)
    for line in evidence.get("footer", {"lines": []})["lines"]:
        match = re.search(r"judge\s*[:=]?\s*(\d+)", line["text"], re.I)
        if match:
            result["judge_setting"] = field(int(match[1]), line)
    for line in evidence.get("grade", {"lines": []})["lines"]:
        if re.fullmatch(r"[A-FS]{1,4}[+\-]?", line["text"].strip()):
            result["grade"] = field(line["text"].strip(), line)
    if "ratings" in evidence:
        result["unlabeled_ratings_text"] = [line["text"] for line in evidence["ratings"]["lines"]]
    for key, pattern in {"ra": r"RA", "ma": r"MA", "pa": r"PA",
                         "longest_mfc": r"Longest\s+MFC", "longest_pfc": r"Longest\s+PFC"}.items():
        result["ratios_and_streaks"][key] = field()
        for line in evidence.get("ratios_and_streaks", {"lines": []})["lines"]:
            # Ratios must contain both sides of a colon. "1.301" is not
            # evidence of "1.3:1" and must not silently become a valid ratio.
            numeric = r"(\d+)\s*$" if key.startswith("longest") else r"(\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?)\s*$"
            match = re.search(rf"\b{pattern}\s*:\s*{numeric}", line["text"], re.I)
            if match:
                value = int(match[1]) if key.startswith("longest") and match[1].isdigit() else re.sub(r"\s", "", match[1])
                result["ratios_and_streaks"][key] = field(value, line)
    for group, fields in evidence.get("fixed_fields", {}).items():
        result[group].update(fields)
    return result


def load_layouts():
    return [json.loads((ROOT / name).read_text())
            for name in ("layout.json", "layout-legacy.json")]


def identify_layout(screen, layouts):
    # The right-side historical leaderboard never supplies current judgments.
    best, score = None, 0
    for layout in layouts:
        evidence = ocr(crop(screen, layout["regions"]["results"]))
        count = anchors(evidence["text"])
        if count < 4:
            count = anchors(evidence["text"] + "\n" + judgment_evidence(screen, layout)["text"])
        if layout["name"] == "etterna_4k_results_v2" and count < 6:
            # The legacy table overlaps this crop and can expose 4–5 labels.
            # Use the new scoring header to distinguish that partial overlap.
            header = ocr(crop(screen, layout["regions"]["accuracy"]))["text"]
            if not re.search(r"\bW\s*\d", header, re.I):
                continue
        if layout["name"] == "etterna_supplied_theme_v1":
            # A camera photo of the NEW table can expose four labels in this
            # old crop. Labels alone must not select an unrelated flat layout.
            if not re.search(r"\bWife\b", evidence["text"], re.I):
                continue
        if count > score:
            best, score = layout, count
        if count == 6:
            break
    return best if score >= 4 else None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def qr_result(payload):
    """Never open URLs automatically. Fetch CSV only from explicitly allowed hosts."""
    from session_qr import resolve
    remote = resolve(payload)
    if remote is not None:
        return remote
    from game_runs import resolve_qr
    game = resolve_qr(payload)
    if game is not None:
        return game
    parsed = urllib.parse.urlsplit(payload)
    if "/sessions/" in parsed.path or "key=" in parsed.query:
        return {"status": "session_error", "source": "game_session", "crops": {},
                "warnings": ["Session QR origin or format is not allowed. Configure RHYTHM_SESSION_ORIGINS for the exact game backend."]}
    result = {"status": "qr_found", "source": "qr", "qr_payload": payload,
              "csv": None, "warnings": []}
    url = urllib.parse.urlsplit(payload)
    allowed = {s.strip().lower() for s in os.getenv("CSV_ALLOWED_HOSTS", "").split(",") if s.strip()}
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        result["warnings"].append("QR decoded. Automatic CSV fetching requires an HTTPS URL.")
        return result
    if url.hostname.lower() not in allowed:
        result["warnings"].append("CSV not fetched: configure CSV_ALLOWED_HOSTS for your data host.")
        return result
    try:
        request = urllib.request.Request(payload, headers={"User-Agent": "EtternaExtractor/1"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            content = response.read(2*1024*1024 + 1)
        if len(content) > 2*1024*1024:
            raise ValueError("CSV exceeds 2 MB.")
        text = content.decode("utf-8-sig")
        if text.lstrip().startswith("<"):
            raise ValueError("URL returned HTML. Use a direct CSV download URL.")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV requires a header with unique column names.")
        rows = list(reader)
        if len(rows) > 20000:
            raise ValueError("CSV exceeds 20,000 rows.")
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise ValueError("CSV rows must match the header column count.")
        result["csv"] = {"columns": reader.fieldnames, "rows": rows}
    except Exception as error:
        result["warnings"].append(f"CSV fetch failed: {error}")
    return result


def extract(image, directory, mode="auto", corners=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    layouts = load_layouts()
    layout = None
    alignment_details = None
    if corners is None:
        # QR detection comes before results-screen detection.
        from qr_reader import scan_qr
        qr = scan_qr(image)
        if qr.payload:
            result = qr_result(qr.payload)
            result["qr_decoder"] = qr.engine
            return result
        if qr.detected:
            return {"status": "qr_ambiguous" if qr.ambiguous else "qr_unreadable", "source": "qr",
                    "qr_decoder": qr.engine, "crops": {}, "warnings": [
                        "Multiple game QR codes are visible. Frame just one and scan again." if qr.ambiguous else
                        "QR outline found, but its data could not be decoded. Move closer, keep the complete white border visible, and scan again."]}
    method = "manual_corners" if corners is not None else mode
    if corners is not None:
        screen = rectify(image, corners)
        layout = identify_layout(screen, layouts)
    elif mode == "screen":
        screen = image
        layout = identify_layout(screen, layouts)
    else:
        # Establish geometry BEFORE classifying a camera image as a flat layout.
        # Readable labels scattered through a room photo are not canvas evidence.
        from registration import register_content
        registered = register_content(image, directory, layouts)
        if registered is not None:
            screen, layout, alignment_details = registered
            method = "auto_game_content"
        else:
            screen = image
            layout = identify_layout(screen, layouts)
            if layout is None:
                screen = None
        if screen is None:
            for points in screen_candidates(image):
                candidate = rectify(image, points)
                candidate_layout = identify_layout(candidate, layouts)
                if candidate_layout is not None:
                    screen = candidate
                    layout = candidate_layout
                    method = "auto_corners"
                    break
        elif method == "auto":
            method = "screen_filling_layout"
        if screen is None:
            return {"status": "needs_corners", "source": "screen", "warnings": [
                "Could not align a supported Etterna screen. Select its four screen corners inside the miniapp."]}
    if layout is None:
        return {"status": "unsupported_or_unreadable", "source": "screen", "warnings": [
            "Expected judgment labels were not found. Check screen corners, focus, and theme."]}
    regions = layout["regions"]
    if screen.shape[1] < 600:
        return {"status": "needs_better_photo", "source": "screen", "warnings": [
            "Screen is under 600 pixels wide. Move closer or capture at higher resolution."]}
    cv2.imwrite(str(directory / "screen.png"), screen)
    evidence, paths, panels = {}, {}, {}
    overlay = screen.copy()
    for name, box in regions.items():
        panel = crop(screen, box)
        panels[name] = panel
        cv2.imwrite(str(directory / f"{name}.png"), panel)
        paths[name] = f"{name}.png"
        if name != "offset_graph":
            evidence[name] = ocr(panel)
        h, w = screen.shape[:2]
        x1, y1, x2, y2 = [round(v*d) for v, d in zip(box, [w, h, w, h])]
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(overlay, name, (x1, max(15, y1-4)), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 0), 1)
    cv2.imwrite(str(directory / "overlay.png"), overlay)
    from native_ocr import engine
    if engine() == "rapidocr" and layout["name"] == "etterna_4k_results_v2":
        from neural_ocr import fixed_fields
        evidence["fixed_fields"] = fixed_fields(panels)
        lines = [{"text": f'{key.title()} {v["value"]}', "ocr_confidence": v["ocr_confidence"]}
                 for key, v in evidence["fixed_fields"]["judgments"].items() if v["value"] is not None]
        evidence["judgment_rows"] = {"text": "\n".join(x["text"] for x in lines), "lines": lines,
                                      "method": "fixed_numeric_cells", "numeric_engine": "rapidocr"}
    else:
        evidence["judgment_rows"] = judgment_evidence(screen, layout, trusted_geometry=alignment_details is not None)
    if alignment_details is None and anchors(evidence["results"]["text"] + "\n" + evidence["judgment_rows"]["text"]) < 4:
        return {"status": "unsupported_or_unreadable", "source": "screen",
                "warnings": ["Expected judgment labels were not found. Check corners, crop layout, focus, and theme."],
                "ocr": evidence, "crops": paths}
    parsed = parse_results(evidence)
    if layout["name"] == "etterna_4k_results_v2":
        # This theme does not display these legacy statistics. Their absence
        # should not appear in the miniapp as an OCR failure.
        parsed["timing"].pop("mean_absolute_ms", None)
        parsed["timing"].pop("smallest_ms", None)
    if alignment_details is not None:
        paths["detected_content"] = "detected_content.png"
    warnings = ["OCR output requires review; confidence scores are not calibrated probabilities.",
                "Graph is an image crop, not reconstructed replay data. No exact event timestamps extracted."]
    if parsed["accuracy_percent"]["value"] is None:
        warnings.append("Accuracy could not be read.")
    for key, value in parsed["judgments"].items():
        if value["value"] is None:
            warnings.append(f"Unreadable judgment count: {key}.")
        elif (value["ocr_confidence"] or 0) < 50:
            warnings.append(f"Review low-confidence judgment OCR: {key}.")
    if layout["name"] == "etterna_4k_results_v2":
        missing_timing = [key for key in ("mean_ms", "standard_deviation_ms", "largest_ms", "left_cbs", "right_cbs")
                          if parsed["timing"][key]["value"] is None]
        if missing_timing:
            warnings.append("Unreadable displayed timing fields: " + ", ".join(missing_timing) + ".")
    complete = parsed["accuracy_percent"]["value"] is not None and all(
        value["value"] is not None for value in parsed["judgments"].values())
    coverage = None
    if layout["name"] == "etterna_4k_results_v2":
        from neural_ocr import completeness
        coverage = completeness(parsed)
        complete = not coverage["missing_fields"] and not coverage["review_fields"]
        if coverage["missing_fields"]:
            warnings.append("Missing displayed fields: " + ", ".join(coverage["missing_fields"]) + ".")
        if coverage["review_fields"]:
            warnings.append("Review these uncertain readings: " + ", ".join(coverage["review_fields"]) + ".")
    if not complete:
        warnings.append("Partial extraction: readable fields and graph are retained; unreadable numbers are not filled from the reference.")
    if alignment_details and alignment_details["matching_mode"] == "appearance_assisted":
        warnings.append("Alignment used shared visual content with the reference, including artwork; a different chart or theme may need alignment correction.")
    return {"status": "extracted" if complete else "partial", "source": "screen", "layout": layout["name"],
            "alignment": method, "alignment_details": alignment_details,
            "data": parsed, "ocr": evidence, "crops": paths, "completeness": coverage,
            "graph": {"image": "offset_graph.png", "events": None,
                      "time_axis": "uncalibrated", "offset_scale": "not_digitized"},
            "warnings": warnings}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--out", default="outputs/cli")
    parser.add_argument("--mode", choices=["screen", "auto"], default="screen")
    args = parser.parse_args()
    result = extract(load_image(Path(args.image).read_bytes()), args.out, args.mode)
    Path(args.out, "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
