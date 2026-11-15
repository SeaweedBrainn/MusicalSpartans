"""Locate known game CONTENT inside a camera photo, not the monitor bezel.

Reference pixels are used ONLY to estimate geometry. All returned crops and OCR
come from the submitted photo. Dynamic result numbers are masked from matching.
"""
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
STATIC_BOXES = [[.049, .501, .24, .783], [.315, .799, .373, .919],
                [.458, .125, .65, .173], [.459, .367, .51, .47],
                [.458, .641, .54, .675], [.458, .885, .54, .916],
                [.049, .799, .1, .919], [.193, .8, .246, .919]]


def fill_boxes(mask, boxes, value):
    h, w = mask.shape
    for x1, y1, x2, y2 in boxes:
        mask[round(y1*h):round(y2*h), round(x1*w):round(x2*w)] = value


@lru_cache(maxsize=4)
def reference_features(path_string, modified):
    reference = cv2.imread(path_string)
    if reference is None:
        return None
    h, w = reference.shape[:2]
    width = 1024
    resized = cv2.resize(reference, (width, round(h*width/w)), interpolation=cv2.INTER_AREA)
    gray = cv2.createCLAHE(2, (8, 8)).apply(cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY))
    sift = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.015)
    models = []
    for mode in ("static_ui", "appearance_assisted"):
        mask = np.zeros(gray.shape, np.uint8) if mode == "static_ui" else np.full(gray.shape, 255, np.uint8)
        if mode == "static_ui":
            fill_boxes(mask, STATIC_BOXES, 255)
        else:
            # Exclude repetitive graph points, leaderboard, account details,
            # numeric count/stat columns, ratings and accuracy from matching.
            fill_boxes(mask, [[.45, .35, 1, .95], [0, 0, .46, .12],
                              [.27, .50, .44, .94], [.72, .18, .96, .35]], 0)
        keys, descriptors = sift.detectAndCompute(gray, mask)
        if descriptors is not None:
            models.append((mode, keys, descriptors))
    return {"width": w, "height": h, "scale": width/w, "models": models}


def register_content(image, directory, layouts):
    layout = next((x for x in layouts if x["name"] == "etterna_4k_results_v2"), None)
    path = ROOT.parent / "samples" / "etterna-4k-results.png"
    if layout is None or not path.is_file():
        return None
    reference = reference_features(str(path), path.stat().st_mtime_ns)
    if reference is None:
        return None
    ih, iw = image.shape[:2]
    photo_scale = min(1, 1600/iw)
    small = cv2.resize(image, None, fx=photo_scale, fy=photo_scale, interpolation=cv2.INTER_AREA)
    gray = cv2.createCLAHE(2, (8, 8)).apply(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
    keys, descriptors = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.015).detectAndCompute(gray, None)
    if descriptors is None or len(keys) < 20:
        return None
    rw, rh = reference["width"], reference["height"]
    rs = reference["scale"]
    ref_w, ref_h = round(rw*rs), round(rh*rs)
    best = None
    for mode, ref_keys, ref_desc in reference["models"]:
        pairs = cv2.BFMatcher().knnMatch(ref_desc, descriptors, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .8*pair[1].distance]
        if len(good) < 18:
            continue
        src = np.float32([ref_keys[m.queryIdx].pt for m in good])
        dst = np.float32([keys[m.trainIdx].pt for m in good])
        matrix, used = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 4)
        if matrix is None or used is None or not np.isfinite(matrix).all():
            continue
        used = used.ravel().astype(bool)
        inliers = int(used.sum())
        if inliers < 18 or inliers/len(good) < .20:
            continue
        coverage = cv2.contourArea(cv2.convexHull(src[used]))/(ref_w*ref_h)
        if coverage < .10:
            continue
        rectangle = np.float32([[0, 0], [ref_w-1, 0], [ref_w-1, ref_h-1], [0, ref_h-1]])
        polygon = cv2.perspectiveTransform(rectangle.reshape(-1, 1, 2), matrix).reshape(4, 2)
        if not np.isfinite(polygon).all() or not cv2.isContourConvex(polygon.astype(np.int32)):
            continue
        area = cv2.contourArea(polygon)/(small.shape[0]*small.shape[1])
        if not .12 < area < 1.6 or polygon[1, 0] <= polygon[0, 0] or polygon[3, 1] <= polygon[0, 1]:
            continue
        if np.any(polygon < [-.5*small.shape[1], -.5*small.shape[0]]) or np.any(
                polygon > [1.5*small.shape[1], 1.5*small.shape[0]]):
            continue
        projected = cv2.perspectiveTransform(src[used].reshape(-1, 1, 2), matrix).reshape(-1, 2)
        residual = float(np.median(np.linalg.norm(projected-dst[used], axis=1)))
        full_matrix = np.diag([1/photo_scale, 1/photo_scale, 1]) @ matrix @ np.diag([rs, rs, 1])
        try:
            inverse = np.linalg.inv(full_matrix)
        except np.linalg.LinAlgError:
            continue
        score = inliers * min(coverage/.3, 1)
        if best is None or score > best[0]:
            best = (score, inverse, polygon/photo_scale, {
                "algorithm": "SIFT_RANSAC_content_registration", "matching_mode": mode,
                "inliers": inliers, "candidate_matches": len(good),
                "reference_spatial_coverage": round(coverage, 3),
                "median_reprojection_error_scaled_px": round(residual, 2),
                "reference_used_for": "geometry_only_not_result_values",
            })
    if best is None:
        return None
    _, inverse, corners, details = best
    frame_corners = np.float32([[0, 0], [iw-1, 0], [iw-1, ih-1], [0, ih-1]])
    if image.shape[:2] == (rh, rw) and float(np.max(np.linalg.norm(corners-frame_corners, axis=1))) < 3:
        # Avoid damaging small text with a needless near-identity resampling.
        screen = image.copy()
        details["resampling"] = "skipped_identity_transform"
    else:
        screen = cv2.warpPerspective(image, inverse, (rw, rh))
        details["resampling"] = "perspective_corrected"
    visible = cv2.warpPerspective(np.ones((ih, iw), np.uint8)*255, inverse, (rw, rh))
    details["visible_game_fraction"] = round(float(np.mean(visible > 200)), 3)
    if details["visible_game_fraction"] < .65:
        return None
    overlay = image.copy()
    cv2.polylines(overlay, [corners.astype(np.int32)], True, (0, 255, 100), max(2, iw//500))
    cv2.imwrite(str(Path(directory)/"detected_content.png"), overlay)
    details["game_corners_in_photo_normalized"] = (corners/[iw, ih]).round(5).tolist()
    return screen, layout, details
