"""Optional macOS Vision OCR. No network or model API is used."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

BINARY = Path(__file__).resolve().parent / "apple-ocr"


def engine():
    requested = os.getenv("OCR_ENGINE", "rapidocr").lower()
    if requested not in ("auto", "apple", "tesseract", "rapidocr"):
        raise ValueError("OCR_ENGINE must be rapidocr, auto, apple, or tesseract")
    if requested == "rapidocr":
        from neural_ocr import reader
        reader()
        return "rapidocr"
    if requested == "apple":
        if sys.platform != "darwin" or not BINARY.is_file():
            raise RuntimeError("Build AppleOCR.swift on your Mac with: swiftc AppleOCR.swift -O -o apple-ocr")
        return "apple_vision"
    return "apple_vision" if requested == "auto" and sys.platform == "darwin" and BINARY.is_file() else "tesseract"


def recognize(image, whitelist=None):
    with tempfile.TemporaryDirectory(prefix="etterna-ocr-") as tmp:
        path = Path(tmp) / "panel.png"
        cv2.imwrite(str(path), image)
        output = subprocess.run([str(BINARY), str(path)], capture_output=True,
                                text=True, timeout=25, check=True)
        items = json.loads(output.stdout)
    # Vision can return label and numeric value as separate observations.
    # Merge horizontally adjacent observations with the same text baseline.
    rows = []
    for item in sorted(items, key=lambda x: x["top"]+x["height"]/2):
        center = item["top"]+item["height"]/2
        row = next((r for r in rows if abs(r["center"]-center) < .45*max(r["height"], item["height"])), None)
        if row is None:
            row = {"center": center, "height": item["height"], "items": []}
            rows.append(row)
        row["items"].append(item)
    lines = []
    for row in rows:
        cells = sorted(row["items"], key=lambda x: x["left"])
        text = " ".join(cell["text"] for cell in cells)
        if whitelist and any(char not in whitelist and not char.isspace() for char in text):
            continue
        lines.append({"text": text, "ocr_confidence": round(
            sum(cell["confidence"] for cell in cells)/len(cells), 1)})
    return {"text": "\n".join(line["text"] for line in lines),
            "lines": lines, "engine": "apple_vision"}
