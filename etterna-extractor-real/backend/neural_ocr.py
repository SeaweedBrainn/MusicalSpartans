"""Local PP-OCRv4 inference plus geometry-specific numeric cells. No network API.

No game result values are stored here. Row/column positions describe the theme.
"""
import re
import threading
from functools import lru_cache

import cv2
import numpy as np

_LOCK = threading.RLock()


@lru_cache(maxsize=1)
def reader():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)


def line(image):
    with _LOCK:
        rows, _ = reader()(image, use_det=False, use_cls=False)
    if not rows:
        return {"text": "", "ocr_confidence": 0}
    text, score = rows[0][:2]
    return {"text": text, "ocr_confidence": round(float(score)*100, 1)}


def recognize(image, whitelist=None):
    with _LOCK:
        result, _ = reader()(image, use_cls=False)
    rows = []
    # Merge label and value observations on the same baseline.
    for box, text, score in result or []:
        p = np.asarray(box)
        cy = float(p[:, 1].mean()); h = float(np.ptp(p[:, 1]))
        row = next((r for r in rows if abs(r["y"]-cy) < .45*max(h, r["h"])), None)
        if row is None:
            row = {"y": cy, "h": h, "cells": []}; rows.append(row)
        row["cells"].append((float(p[:, 0].min()), text, float(score)*100))
    lines = []
    for row in sorted(rows, key=lambda r: r["y"]):
        cells = sorted(row["cells"])
        text = " ".join(c[1] for c in cells)
        if whitelist and any(c not in whitelist and not c.isspace() for c in text):
            continue
        lines.append({"text": text, "ocr_confidence": round(sum(c[2] for c in cells)/len(cells), 1)})
    return {"text": "\n".join(r["text"] for r in lines), "lines": lines, "engine": "rapidocr"}


def row(panel, i, n, left=0, right=1):
    h, w = panel.shape[:2]
    return panel[round(i*h/n):round((i+1)*h/n), round(left*w):round(right*w)].copy()


def trim_white(panel):
    mask = cv2.inRange(cv2.cvtColor(panel, cv2.COLOR_BGR2HSV), (0, 0, 150), (180, 150, 255))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    chars = stats[1:]
    chars = chars[(chars[:, 4] > 5) & (chars[:, 3] > panel.shape[0]*.2)]
    if not len(chars):
        return None
    x, y = chars[:, 0].min(), chars[:, 1].min()
    r, b = (chars[:, 0]+chars[:, 2]).max(), (chars[:, 1]+chars[:, 3]).max()
    return panel[max(0, y-3):min(panel.shape[0], b+3), max(0, x-3):min(panel.shape[1], r+3)]


def missing(candidates=None):
    return {"value": None, "raw": None, "ocr_confidence": None,
            "engine": "rapidocr", "candidates": candidates or []}


def cell(panel, decimal=False, minimum=65):
    panel = trim_white(panel)
    if panel is None:
        return missing()
    gray = cv2.cvtColor(cv2.cvtColor(panel, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    candidates = []
    for name, image in (("color", panel), ("gray", gray)):
        candidate = line(image); candidate["variant"] = name
        candidates.append(candidate)
    if not decimal and any(re.fullmatch(r"[0-9Oo]", c["text"].strip()) for c in candidates):
        # Short glyphs have little context for a sequence recognizer. Repeating
        # the SAME observed pixels is a recognition augmentation, not a source
        # of new digits. Only three identical decoded groups are accepted.
        for name, image in (("repeat_color", panel), ("repeat_gray", gray)):
            gap = np.zeros((image.shape[0], 8, 3), np.uint8)
            repeated = np.concatenate((image, gap, image, gap, image), axis=1)
            candidate = line(repeated); candidate["variant"] = name
            candidates.append(candidate)
    valid = []
    for candidate in candidates:
        text = re.sub(r"\s", "", candidate["text"])
        if not decimal:
            # In an isolated numeric cell, O/o can only denote a zero.
            text = text.translate(str.maketrans({"O": "0", "o": "0"}))
        if candidate["variant"].startswith("repeat"):
            n = len(text)//3
            if not n or len(text) != n*3 or text != text[:n]*3:
                continue
            text = text[:n]
        pattern = r"\d+\.\d+" if decimal else r"\d{1,7}"
        if re.fullmatch(pattern, text) and candidate["ocr_confidence"] >= minimum:
            valid.append((candidate, float(text) if decimal else int(text)))
    if not valid:
        return missing(candidates)
    best, value = max(valid, key=lambda v: v[0]["ocr_confidence"])
    # Do not resolve two strong contradictory readings using confidence alone.
    if any(v != value and c["ocr_confidence"] >= 90 for c, v in valid):
        return missing(candidates)
    return {"value": value, "raw": best["text"], "ocr_confidence": best["ocr_confidence"],
            "engine": "rapidocr", "method": best["variant"], "candidates": candidates}


def fixed_fields(panels):
    out = {"judgments": {}, "timing": {}, "auxiliary_counts": {}, "ratios_and_streaks": {}}
    for i, key in enumerate(("marvelous", "perfect", "great", "good", "bad", "miss")):
        out["judgments"][key] = cell(row(panels["results"], i, 6, .58, .86))
    for i, key in enumerate(("mean_ms", "standard_deviation_ms", "largest_ms")):
        # Keep the full line here: trimming short components can lose a minus.
        reading = line(row(panels["timing_stats"], i, 5))
        text = re.sub(r"\s", "", reading["text"]).replace("−", "-")
        match = re.search(r"[+\-]?\d+\.\d{2}(?!\d)", text)
        out["timing"][key] = missing([reading])
        if match and reading["ocr_confidence"] >= 65:
            out["timing"][key] = {"value": float(match[0]), "raw": reading["text"],
                                  "ocr_confidence": reading["ocr_confidence"], "engine": "rapidocr"}
    for i, key in ((3, "left_cbs"), (4, "right_cbs")):
        out["timing"][key] = cell(row(panels["timing_stats"], i, 5, .92, 1), minimum=60)
    for i, key in enumerate(("holds", "mines", "rolls", "lifts", "fakes")):
        a = cell(row(panels["auxiliary_counts"], i, 5, .48, .72), minimum=50)
        if a["value"] is None:
            a = cell(row(panels["auxiliary_counts"], i, 5, .48, .70), minimum=50)
        b = cell(row(panels["auxiliary_counts"], i, 5, .79, 1), minimum=50)
        out["auxiliary_counts"][key] = missing([a, b])
        if a["value"] is not None and b["value"] is not None:
            out["auxiliary_counts"][key] = {"value": {"first": a["value"], "second": b["value"]},
                "raw": f'{a["raw"]} / {b["raw"]}', "ocr_confidence": min(a["ocr_confidence"], b["ocr_confidence"]),
                "engine": "rapidocr", "method": "separate_pair_cells", "candidates": [a, b]}
    for i, key in enumerate(("ra", "ma", "pa")):
        a = cell(row(panels["ratios_and_streaks"], i, 5, .425, .59), decimal=True, minimum=85)
        b = cell(row(panels["ratios_and_streaks"], i, 5, .63, .73), minimum=85)
        out["ratios_and_streaks"][key] = missing([a, b])
        if a["value"] is not None and b["value"] is not None:
            out["ratios_and_streaks"][key] = {"value": f'{a["value"]:g}:{b["value"]}',
                "raw": f'{a["raw"]} : {b["raw"]}', "ocr_confidence": min(a["ocr_confidence"], b["ocr_confidence"]),
                "engine": "rapidocr", "method": "separate_ratio_cells", "candidates": [a, b]}
    for i, key in ((3, "longest_mfc"), (4, "longest_pfc")):
        out["ratios_and_streaks"][key] = cell(row(panels["ratios_and_streaks"], i, 5, .77, .99), minimum=90)
    return out


def completeness(data):
    paths = [(key,) for key in ("accuracy_percent", "grade", "wife_version", "judge_setting", "playback_rate")]
    for group, keys in {
        "judgments": ("marvelous", "perfect", "great", "good", "bad", "miss"),
        "timing": ("mean_ms", "standard_deviation_ms", "largest_ms", "left_cbs", "right_cbs"),
        "auxiliary_counts": ("holds", "mines", "rolls", "lifts", "fakes"),
        "ratios_and_streaks": ("ra", "ma", "pa", "longest_mfc", "longest_pfc"),
    }.items():
        paths.extend((group, key) for key in keys)
    absent, review = [], []
    for path in paths:
        item = data
        for key in path:
            item = item.get(key, {})
        name = ".".join(path)
        if item.get("value") is None:
            absent.append(name)
        elif (item.get("ocr_confidence") or 0) < 65:
            review.append(name)
    return {"expected_fields": len(paths), "read_fields": len(paths)-len(absent),
            "missing_fields": absent, "review_fields": review,
            "not_displayed": ["timing.mean_absolute_ms", "timing.smallest_ms"]}
