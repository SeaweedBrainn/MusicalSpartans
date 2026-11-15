import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

import game_runs
from server import app, OUTPUTS

SAMPLES = Path(__file__).parent.parent / "samples" / "custom-game"
SUMMARY = (SAMPLES / "song10-chart1-summary.csv").read_text()
TIMELINE = (SAMPLES / "song10-chart1.csv").read_text()


class GameRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = patch.object(game_runs, "STORE", Path(self.tmp.name))
        self.store.start()
        self.jobs = []

    def tearDown(self):
        for job in self.jobs:
            shutil.rmtree(OUTPUTS / job, ignore_errors=True)
        self.store.stop()
        self.tmp.cleanup()

    def test_sample_matches_kotlin_reference_results(self):
        run = game_runs.import_run(SUMMARY, TIMELINE)
        analysis = game_runs.analyze(run)
        self.assertEqual(run["summary"]["song_id"], 10)
        self.assertEqual(run["chart_id"], 1)
        self.assertEqual(len(run["samples"]), 14)
        self.assertEqual(sum(s["nps"] for s in run["samples"]), 25)
        self.assertIsNone(run["samples"][0]["accuracy"])
        self.assertEqual(run["samples"][2]["accuracy"], 1)
        self.assertEqual(analysis["score"], 1_000_000)
        self.assertEqual(analysis["grade"], "Perfect")
        self.assertEqual(analysis["accuracy"], 1)
        self.assertAlmostEqual(analysis["mean_offset_ms"], 26.16)
        self.assertEqual([s["start_ms"] for s in analysis["sections"]], [0,5000,10000])
        self.assertIn("late", analysis["tips"][0]["text"])
        self.assertIsNone(run["video_uri"])
        self.assertIsNone(run["video_offset_ms"])

    def test_summary_only_keeps_timeline_unknown(self):
        run = game_runs.import_run(SUMMARY)
        analysis = game_runs.analyze(run)
        self.assertFalse(run["timeline_available"])
        self.assertIsNone(run["chart_id"])
        self.assertEqual(analysis["mean_offset_ms"], 26)
        self.assertEqual(analysis["sections"], [])

    def test_note_weighting_and_section_tips(self):
        text = "game_id,1\nsong_id,10\nchart_id,1\ngame_time,percent_accuracy,avg_latency,bpm,nps,latency_spread\n0,100,-40,120,1,20\n5,50,0,120,3,20"
        result = game_runs.analyze(game_runs.import_run(SUMMARY, text))
        self.assertEqual(result["mean_offset_ms"], -10)
        self.assertEqual(result["sections"][1]["accuracy"], .5)
        self.assertTrue(any("earlier" in t["text"] for t in result["tips"]))
        self.assertTrue(any("Accuracy dropped" in t["text"] for t in result["tips"]))

    def test_invalid_or_mismatched_csvs_are_rejected(self):
        bad_pairs = [(SUMMARY, TIMELINE.replace("song_id,10", "song_id,11")),
                     (SUMMARY, TIMELINE.replace("game_id,1", "game_id,2")),
                     (SUMMARY.replace("1000000", "1000001"), TIMELINE),
                     (SUMMARY.replace(",26", ",NaN"), TIMELINE),
                     (SUMMARY, TIMELINE.replace("2,100,40", "2,101,40")),
                     (SUMMARY, TIMELINE.replace("3,100,25", "2,100,25")),
                     (SUMMARY, TIMELINE.replace("2,100,40,120,2,3", "2,100,40,120,2"))]
        for summary, timeline in bad_pairs:
            with self.subTest(summary=summary, timeline=timeline), self.assertRaises(ValueError):
                game_runs.import_run(summary, timeline)

    def test_upload_qr_photo_analysis_end_to_end(self):
        with TestClient(app) as client:
            response = client.post("/runs", files={"summary": ("summary.csv", SUMMARY), "timeline": ("timeline.csv", TIMELINE)})
            self.assertEqual(response.status_code, 201, response.text)
            receipt = response.json()
            self.assertEqual(client.get(receipt["run_path"]).json()["analysis"]["grade"], "Perfect")
            self.assertEqual(client.get(f'/runs/{receipt["runId"]}/summary.csv').text, SUMMARY)
            self.assertEqual(client.get(f'/runs/{receipt["runId"]}/timeline.csv').text, TIMELINE)
            qr = client.get(receipt["qr_path"])
            self.assertEqual(qr.status_code, 200)
            image = cv2.imdecode(np.frombuffer(qr.content, np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(cv2.QRCodeDetector().detectAndDecode(image)[0], receipt["qr_payload"])
            uploaded = client.post("/api/jobs?mode=auto", content=qr.content, headers={"Content-Type":"image/png"})
            self.assertEqual(uploaded.status_code, 202)
            job = uploaded.json()["job_id"]; self.jobs.append(job)
            result = client.get(f"/api/jobs/{job}").json()
            self.assertEqual(result["status"], "run_analyzed")
            self.assertEqual(result["source"], "game_csv")
            self.assertEqual(result["game_run"]["analysis"]["mean_offset_ms"], 26.16)
            self.assertNotIn("data", result, "CSV scoring must not be represented as Etterna OCR data")

    def test_game_demo_and_paste_path(self):
        with TestClient(app) as client:
            response = client.post("/api/game-demo")
            self.assertEqual(response.status_code, 202)
            job = response.json()["job_id"]; self.jobs.append(job)
            result = client.get(f"/api/jobs/{job}").json()
            pasted = client.post("/api/game-run", json={"payload": result["qr_payload"]})
            self.assertEqual(pasted.status_code, 202)
            self.jobs.append(pasted.json()["job_id"])
            self.assertEqual(client.post(f"/api/jobs/{job}/auto-align").status_code, 400)
            self.assertEqual(client.post("/api/game-run", json={"payload":"https://example.com/run"}).status_code, 400)

    def test_unknown_runs_and_path_traversal_do_not_fetch_urls(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/runs/missing").status_code, 404)
            self.assertEqual(client.post("/api/game-run", json={"payload":game_runs.PREFIX+"missing"}).status_code, 404)
        self.assertIsNone(game_runs.resolve_qr("https://example.com/run"))
        self.assertEqual(game_runs.resolve_qr(game_runs.PREFIX+"../../secret")["status"], "qr_found")


if __name__ == "__main__":
    unittest.main()
