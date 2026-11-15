"""Run after installing requirements + httpx: python -m unittest -v test_regression"""
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from extract import extract, load_image, rectify
from server import app, OUTPUTS

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class RegressionTests(unittest.TestCase):
    def test_default_uses_neural_mode_without_selecting_apple_binary(self):
        from native_ocr import engine
        with patch.dict(os.environ, {}, clear=True), patch("neural_ocr.reader", return_value=object()), patch("native_ocr.sys.platform", "darwin"):
            self.assertEqual(engine(), "rapidocr")

    def test_completeness_includes_small_statistics(self):
        from neural_ocr import completeness
        data = {"accuracy_percent": {"value": 87.57, "ocr_confidence": 90},
                "judgments": {key: {"value": 1, "ocr_confidence": 90}
                              for key in ("marvelous", "perfect", "great", "good", "bad", "miss")}}
        coverage = completeness(data)
        self.assertEqual(coverage["expected_fields"], 26)
        self.assertIn("timing.mean_ms", coverage["missing_fields"])
        self.assertIn("auxiliary_counts.holds", coverage["missing_fields"])
        self.assertIn("ratios_and_streaks.longest_pfc", coverage["missing_fields"])
        self.assertNotIn("timing.mean_absolute_ms", coverage["missing_fields"])

    @unittest.skipUnless(os.getenv("ETTERNA_CAMERA_TEST_DIR"), "Set ETTERNA_CAMERA_TEST_DIR for the latest crop-board fixture")
    def test_neural_reader_on_latest_actual_crops(self):
        from neural_ocr import fixed_fields
        paths = list(Path(os.environ["ETTERNA_CAMERA_TEST_DIR"]).glob("Screenshot*3.35.00*.png"))
        if not paths:
            self.skipTest("Latest crop-board fixture not present")
        image = cv2.imread(str(paths[0]))
        boxes = {"results": (14,108,667,375), "timing_stats": (689,513,1159,777),
                 "auxiliary_counts": (1364,513,1833,777), "ratios_and_streaks": (14,914,422,1178)}
        panels = {name: image[y1:y2, x1:x2].copy() for name, (x1,y1,x2,y2) in boxes.items()}
        data = fixed_fields(panels)
        self.assertEqual([v["value"] for v in data["judgments"].values()], [679,537,215,1,1,1])
        self.assertEqual([v["value"] for v in data["timing"].values()], [23.37,21.75,-164.57,3,0])
        self.assertEqual([v["value"] for v in data["auxiliary_counts"].values()],
                         [{"first": 2, "second": 2}] + [{"first": 0, "second": 0}]*4)
        self.assertEqual([data["ratios_and_streaks"][k]["value"] for k in ("ra","ma","pa")], ["1.1:1","1.3:1","2.5:1"])
        # Do not promote the blurred streak candidates as reliable values.
        self.assertIsNone(data["ratios_and_streaks"]["longest_pfc"]["value"])

    def test_neural_numeric_cells_do_not_fill_blank_images(self):
        from neural_ocr import fixed_fields
        image = np.zeros((240, 600, 3), np.uint8)
        data = fixed_fields({key: image for key in ("results", "timing_stats", "auxiliary_counts", "ratios_and_streaks")})
        for group in data.values():
            self.assertTrue(all(v["value"] is None for v in group.values()))

    def test_apple_selection_cannot_supply_truncated_numeric_counts(self):
        from extract import numeric_judgment_evidence
        image = load_image((SAMPLES / "etterna-4k-results.png").read_bytes())

        def fake_vision(panel, whitelist=None):
            # Actual failure mode in the submitted Apple output: a partial digit
            # observation with confidence 100. Such a call must never supply counts.
            if whitelist:
                return {"text": "6", "lines": [{"text": "6", "ocr_confidence": 100}], "engine": "apple_vision"}
            return {"text": "", "lines": [], "engine": "apple_vision"}

        with patch("native_ocr.engine", return_value="apple_vision"), patch("native_ocr.recognize", side_effect=fake_vision) as vision:
            result = numeric_judgment_evidence(image, trusted_geometry=True)
        self.assertEqual([line["text"] for line in result["lines"]],
                         ["Marvelous 679", "Perfect 537", "Great 215", "Good 1", "Bad 1", "Miss 1"])
        self.assertEqual(result["numeric_engine"], "tesseract")
        self.assertTrue(all(row["number_ocr"]["engine"] == "tesseract" for row in result["readings"]))
        self.assertTrue(all(call.args[1] is None for call in vision.call_args_list))

    def test_new_4k_results_and_historical_score_exclusion(self):
        image = load_image((SAMPLES / "etterna-4k-results.png").read_bytes())
        with tempfile.TemporaryDirectory() as out:
            result = extract(image, out, "auto")
            coverage = result["completeness"]
            self.assertEqual(coverage["expected_fields"], 26)
            if os.getenv("OCR_ENGINE", "rapidocr") == "rapidocr":
                self.assertEqual(result["status"], "extracted")
                self.assertEqual(coverage["read_fields"], 26)
            else:
                self.assertEqual(result["status"], "partial" if coverage["missing_fields"] or coverage["review_fields"] else "extracted")
            self.assertNotIn("mean_absolute_ms", result["data"]["timing"])
            self.assertNotIn("smallest_ms", result["data"]["timing"])
            self.assertEqual(result["layout"], "etterna_4k_results_v2")
            data = result["data"]
            # Historical scores show 98.37 and 98.34; current result is 87.57.
            self.assertEqual(data["accuracy_percent"]["value"], 87.57)
            self.assertEqual(data["grade"]["value"], "A")
            self.assertEqual(data["wife_version"]["value"], 3)
            self.assertEqual(data["judge_setting"]["value"], 4)
            expected = {"marvelous": 679, "perfect": 537, "great": 215,
                        "good": 1, "bad": 1, "miss": 1}
            self.assertEqual({k: v["value"] for k, v in data["judgments"].items()}, expected)
            self.assertEqual(data["timing"]["mean_ms"]["value"], 23.37)
            self.assertEqual(data["timing"]["standard_deviation_ms"]["value"], 21.75)
            self.assertEqual(data["timing"]["left_cbs"]["value"], 3)
            self.assertEqual(data["timing"]["right_cbs"]["value"], 0)
            self.assertEqual(data["ratios_and_streaks"]["ma"]["value"], "1.3:1")
            self.assertTrue((Path(out) / "offset_graph.png").is_file())

    def test_demo_preview_and_in_app_corner_reprocess(self):
        import shutil
        with TestClient(app) as client:
            response = client.post("/api/demo")
            self.assertEqual(response.status_code, 202)
            job = response.json()["job_id"]
            try:
                result = client.get(f"/api/jobs/{job}").json()
                self.assertEqual(result["data"]["judgments"]["perfect"]["value"], 537)
                image = client.get(f"/api/jobs/{job}/preview/original")
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.headers["content-type"], "image/jpeg")
                self.assertEqual(client.get(f"/api/jobs/{job}/preview/offset_graph").status_code, 200)
                self.assertEqual(client.get(f"/api/jobs/{job}/preview/unknown").status_code, 404)
                self.assertEqual(client.post(f"/api/jobs/{job}/corners", json={"corners": [[0, 0]]}).status_code, 400)
                response = client.post(f"/api/jobs/{job}/corners", json={
                    "corners": [[0, 0], [1, 0], [1, 1], [0, 1]]})
                self.assertEqual(response.status_code, 202)
                self.assertIn(client.get(f"/api/jobs/{job}").json()["status"], ("extracted", "partial"))
            finally:
                shutil.rmtree(OUTPUTS / job)

    def test_reference_screenshot_values(self):
        image = load_image((SAMPLES / "etterna-reference.png").read_bytes())
        with tempfile.TemporaryDirectory() as out:
            result = extract(image, out, "auto")
            self.assertEqual(result["status"], "extracted")
            data = result["data"]
            self.assertEqual(data["accuracy_percent"]["value"], 96.91)
            expected = {"marvelous": 1255, "perfect": 398, "great": 53,
                        "good": 4, "bad": 0, "miss": 4}
            self.assertEqual({k: v["value"] for k, v in data["judgments"].items()}, expected)
            self.assertEqual(data["timing"]["mean_ms"]["value"], -2.9)
            self.assertEqual(data["timing"]["mean_absolute_ms"]["value"], 13.71)
            self.assertEqual(data["timing"]["standard_deviation_ms"]["value"], 17.62)
            self.assertTrue((Path(out) / "offset_graph.png").is_file())
            self.assertIsNone(result["graph"]["events"])

    def test_api_upload_and_low_resolution_unknowns(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.post("/api/jobs", content=b"not an image").status_code, 400)
            response = client.post("/api/jobs?mode=screen", content=(
                SAMPLES / "etterna-low-resolution.png").read_bytes(),
                headers={"Content-Type": "image/png"})
            self.assertEqual(response.status_code, 202)
            job = response.json()["job_id"]
            result = client.get(f"/api/jobs/{job}").json()
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["data"]["accuracy_percent"]["value"], 99.98)
            self.assertEqual(result["data"]["judgments"]["marvelous"]["value"], 4938)
            self.assertTrue(result["warnings"])
            self.assertEqual(client.get(f"/outputs/{job}/offset_graph.png").status_code, 200)
            # Remove only the scan created by this test.
            import shutil
            shutil.rmtree(OUTPUTS / job)

    def test_blank_scene_requires_alignment(self):
        with tempfile.TemporaryDirectory() as out:
            result = extract(np.full((800, 1200, 3), 40, np.uint8), out)
            self.assertEqual(result["status"], "needs_corners")

    def test_missing_numbers_are_not_filled_from_reference(self):
        image = load_image((SAMPLES / "etterna-4k-results.png").read_bytes())
        h, w = image.shape[:2]
        image[round(.24*h):round(.29*h), round(.75*w):round(.95*w)] = 0
        image[round(.50*h):round(.79*h), round(.27*w):round(.39*w)] = 0
        # Put the edited screenshot into a synthetic skewed camera scene.
        source = np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
        dest = np.float32([[140, 140], [1500, 80], [1450, 950], [250, 1050]])
        scene = cv2.warpPerspective(image, cv2.getPerspectiveTransform(source, dest), (1700, 1250))
        with tempfile.TemporaryDirectory() as out:
            result = extract(scene, out, "auto")
            self.assertEqual(result["alignment"], "auto_game_content")
            self.assertEqual(result["status"], "partial")
            self.assertIsNone(result["data"]["accuracy_percent"]["value"])
            self.assertTrue(all(v["value"] is None for v in result["data"]["judgments"].values()))
            self.assertTrue((Path(out)/"offset_graph.png").is_file())

    @unittest.skipUnless(os.getenv("ETTERNA_CAMERA_TEST_DIR"), "Set ETTERNA_CAMERA_TEST_DIR for supplied camera examples")
    def test_supplied_camera_examples_automatically_align(self):
        paths = sorted(Path(os.environ["ETTERNA_CAMERA_TEST_DIR"]).glob("Screenshot*1.18.*.png"))
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            with self.subTest(image=path.name), tempfile.TemporaryDirectory() as out:
                result = extract(load_image(path.read_bytes()), out, "auto")
                self.assertEqual(result["alignment"], "auto_game_content")
                self.assertIn(result["status"], ("partial", "extracted"))
                self.assertEqual(result["data"]["accuracy_percent"]["value"], 87.57)
                self.assertGreaterEqual(result["alignment_details"]["inliers"], 18)
                self.assertTrue((Path(out)/"offset_graph.png").is_file())
                self.assertTrue((Path(out)/"detected_content.png").is_file())

    @unittest.skipUnless(os.getenv("ETTERNA_CAMERA_TEST_DIR"), "Set ETTERNA_CAMERA_TEST_DIR for brightness examples")
    def test_lower_brightness_photo_does_not_select_legacy_layout(self):
        folder = Path(os.environ["ETTERNA_CAMERA_TEST_DIR"])
        paths = list(folder.glob("Screenshot*1.57.12*.png"))
        if not paths:
            self.skipTest("Lower-brightness example is not present")
        image = load_image(paths[0].read_bytes())
        from extract import identify_layout, load_layouts
        direct = identify_layout(image, load_layouts())
        self.assertIsNone(direct, "A room photo must not pass as the legacy flat screenshot")
        with tempfile.TemporaryDirectory() as out:
            result = extract(image, out, "auto")
            self.assertEqual(result["alignment"], "auto_game_content")
            self.assertEqual(result["layout"], "etterna_4k_results_v2")
            self.assertEqual(result["data"]["accuracy_percent"]["value"], 87.57)
            expected = {"marvelous": 679, "perfect": 537, "great": 215,
                        "good": 1, "bad": 1, "miss": 1}
            self.assertEqual({k: v["value"] for k, v in result["data"]["judgments"].items()}, expected)
            screen = cv2.imread(str(Path(out)/"screen.png"))
            self.assertEqual(screen.shape[:2], (1152, 2048))
            graph = cv2.imread(str(Path(out)/"offset_graph.png"))
            hsv = cv2.cvtColor(graph, cv2.COLOR_BGR2HSV)
            self.assertGreater(float(np.mean((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 70))), .01)

    def test_qr_path_and_no_automatic_url_open(self):
        code = cv2.QRCodeEncoder_create().encode("https://example.com/results.csv")
        code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        code = cv2.resize(code, (600, 600), interpolation=cv2.INTER_NEAREST)
        image = cv2.cvtColor(code, cv2.COLOR_GRAY2BGR)
        with tempfile.TemporaryDirectory() as out:
            result = extract(image, out)
            self.assertEqual(result["status"], "qr_found")
            self.assertEqual(result["qr_payload"], "https://example.com/results.csv")
            self.assertIsNone(result["csv"])

    @unittest.skipUnless(os.getenv("ETTERNA_CAMERA_TEST_DIR"), "Set ETTERNA_CAMERA_TEST_DIR for latest camera example")
    def test_latest_blurred_counts_do_not_read_one_as_41_or_4(self):
        paths = list(Path(os.environ["ETTERNA_CAMERA_TEST_DIR"]).glob("Screenshot*2.21.02*.png"))
        if not paths:
            self.skipTest("Latest camera example is not present")
        with tempfile.TemporaryDirectory() as out:
            result = extract(load_image(paths[0].read_bytes()), out, "auto")
            self.assertEqual(result["alignment"], "auto_game_content")
            self.assertEqual({k: v["value"] for k, v in result["data"]["judgments"].items()},
                             {"marvelous": 679, "perfect": 537, "great": 215,
                              "good": 1, "bad": 1, "miss": 1})

    def test_incomplete_ratios_are_not_accepted_as_complete_values(self):
        from extract import parse_results
        empty = {"text": "", "lines": []}
        evidence = {name: empty for name in ("results", "song_and_rate", "timing_stats", "auxiliary_counts")}
        evidence["ratios_and_streaks"] = {"lines": [
            {"text": "RA: 1.1", "ocr_confidence": 80},
            {"text": "MA: 1.301", "ocr_confidence": 80},
            {"text": "PA: 2.5:1", "ocr_confidence": 80}]}
        data = parse_results(evidence)["ratios_and_streaks"]
        self.assertIsNone(data["ra"]["value"])
        self.assertIsNone(data["ma"]["value"])
        self.assertEqual(data["pa"]["value"], "2.5:1")

    def test_corner_correction_on_synthetic_monitor_photo(self):
        reference = cv2.imread(str(SAMPLES / "etterna-reference.png"))
        reference = cv2.resize(reference, (900, 660))
        source = np.float32([[0, 0], [899, 0], [899, 659], [0, 659]])
        corners = np.float32([[130, 110], [1060, 70], [1100, 780], [90, 740]])
        matrix = cv2.getPerspectiveTransform(source, corners)
        photo = cv2.warpPerspective(reference, matrix, (1200, 900))
        fixed = rectify(photo, corners / [1199, 899])
        fixed = cv2.resize(fixed, (900, 660))
        # Compare blurred images to tolerate resampling at letter edges.
        difference = np.abs(cv2.GaussianBlur(fixed, (5, 5), 0).astype(float)
                            - cv2.GaussianBlur(reference, (5, 5), 0).astype(float)).mean()
        self.assertLess(difference, 5)


if __name__ == "__main__":
    unittest.main()
