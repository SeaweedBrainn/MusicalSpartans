"""Bounded multi-engine QR reading. No payloads are logged or written to disk."""
from dataclasses import dataclass
from urllib.parse import urlsplit

import cv2
import numpy as np

try:
    import zxingcpp
except ImportError:
    zxingcpp = None


@dataclass
class QRScan:
    payload: str | None = None
    detected: bool = False
    engine: str = 'none'
    ambiguous: bool = False


def decoder_name():
    return 'zxing-cpp+opencv' if zxingcpp is not None else 'opencv-only (install requirements.txt)'


def choose(payloads, engine):
    unique = list(dict.fromkeys(p for p in payloads if p))
    if not unique:
        return None
    def game_link(value):
        try:
            return value.startswith('mentra-run:v1:') or urlsplit(value).path.startswith('/sessions/')
        except ValueError:
            return False
    preferred = [p for p in unique if game_link(p)] or unique
    if len(preferred) > 1:
        return QRScan(detected=True, engine=engine, ambiguous=True)
    return QRScan(preferred[0], True, engine)


def zxing(image):
    if zxingcpp is None:
        return None
    try:
        codes = zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode,
                                      try_rotate=True, try_downscale=True)
        return choose([code.text for code in codes if code.valid], 'zxing-cpp')
    except (ValueError, RuntimeError):
        return None


def scan_qr(image):
    # ZXing handles the tilted camera-on-monitor case that OpenCV detects but
    # fails to decode. Fast path avoids preprocessing most photos.
    result = zxing(image)
    if result:
        return result
    detector = cv2.QRCodeDetector()
    points = None
    try:
        payload, points, _ = detector.detectAndDecode(image)
        result = choose([payload], 'opencv')
        if result:
            return result
    except cv2.error:
        pass
    if points is None:
        # Do not threshold/scan arbitrary room photographs repeatedly.
        return QRScan()
    try:
        quad = np.asarray(points, dtype=np.float32).reshape(-1, 2)[:4]
        if quad.shape != (4, 2) or abs(cv2.contourArea(quad)) < 100:
            return QRScan()
        # Local perspective retry, with a quiet margin; bounded independent of
        # full photo dimensions. No generated pixels are treated as measurements.
        target = np.array([[32,32],[735,32],[735,735],[32,735]], np.float32)
        crop = cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad,target),
                                   (768,768), borderValue=(255,255,255))
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        for variant in (crop, cv2.createCLAHE(clipLimit=2, tileGridSize=(8,8)).apply(gray)):
            result = zxing(variant)
            if result:
                return result
            try:
                payload, _, _ = detector.detectAndDecode(variant)
                result = choose([payload], 'opencv-perspective')
                if result:
                    return result
            except cv2.error:
                pass
    except (cv2.error, ValueError):
        pass
    return QRScan(detected=True, engine='outline-only')
