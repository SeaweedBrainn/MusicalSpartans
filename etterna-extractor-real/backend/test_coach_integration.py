import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

import game_runs
from coach_api import get_coaching
from coach_domain import OcrReview, SongSummary, build_report, context_request, offline_reply, song_request, summarize
from server import OUTPUTS, app, write_json

SAMPLES = Path(__file__).parent.parent / "samples" / "custom-game"


def screen_result():
    f = lambda v: {"value": v, "ocr_confidence": 90, "raw": str(v)}
    return {"job_id": "screen-test", "source": "screen", "status": "partial", "data": {
        "accuracy_percent": f(87.57), "accuracy_label": f("87.57% [W3 J4]"),
        "wife_version": f(3), "judge_setting": f(4), "grade": f("A"),
        "song_text": "Etterna song", "timing": {"mean_ms": f(23.37), "standard_deviation_ms": f(21.75)}}}


class CoachIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = patch.object(game_runs, "STORE", Path(self.tmp.name))
        self.store.start()
        self.game = game_runs.create_run((SAMPLES/"song10-chart1-summary.csv").read_text(), (SAMPLES/"song10-chart1.csv").read_text())
        self.result = game_runs.resolve_qr(game_runs.PREFIX+self.game["run_id"])
        self.result["job_id"] = "csv-test"
        self.song = summarize(self.result)
        self.jobs = []

    def tearDown(self):
        for job in self.jobs:
            shutil.rmtree(OUTPUTS/job, ignore_errors=True)
        self.store.stop(); self.tmp.cleanup()

    def test_csv_adapter_percent_and_sections_are_grounded(self):
        request = song_request(self.result, OcrReview())
        self.assertEqual(request["tier"], "A")
        self.assertEqual(request["runs"][0]["facts"]["overall"]["accuracy_pct"], 100)
        self.assertEqual(request["runs"][0]["facts"]["overall"]["offset_mean_ms"], 26.16)
        self.assertEqual(len(request["runs"][0]["facts"]["sections"]), 3)
        self.assertEqual(request["runs"][0]["facts"]["sections"][-1]["end_s"], 14)

    def test_ocr_requires_review_and_does_not_invent_custom_metadata(self):
        with self.assertRaises(ValueError): summarize(screen_result())
        review = OcrReview(reviewed=True, accuracy_pct=86.5, mean_offset_ms=None, native_grade="A")
        summary = summarize(screen_result(), review)
        self.assertEqual(summary.accuracy_pct, 86.5)
        self.assertIsNone(summary.mean_offset_ms)
        for key in ("score", "score_max", "bpm", "game_time_ms", "song_id", "total_notes", "offset_spread_ms"):
            self.assertIsNone(getattr(summary, key), key)
        request = song_request(screen_result(), review)
        self.assertEqual(request["tier"], "B")
        self.assertEqual(request["runs"][0]["facts"]["sections"], [])
        self.assertEqual(summary.native_grade, "A")

    def test_ambiguous_scoring_labels_do_not_pool_screens(self):
        result = screen_result(); result["data"]["accuracy_label"]["ocr_confidence"] = 20
        summary = summarize(result, OcrReview(reviewed=True))
        self.assertTrue(summary.scoring_system.startswith("unverified_metric_"))

    def test_report_keeps_games_and_grades_separate_without_timelines(self):
        ocr = summarize(screen_result(), OcrReview(reviewed=True))
        report = build_report([self.song, ocr])
        self.assertEqual(len(report["groups"]), 2)
        self.assertEqual(sorted(g["average_accuracy_pct"] for g in report["groups"]), [87.57,100])
        self.assertNotIn("average_accuracy_pct", report)
        self.assertNotIn("samples", report["songs"][0])
        self.assertEqual(report["songs"][1]["native_grade"], "A")
        self.assertIn("Scoring systems are compared separately", report["text"])
        with self.assertRaises(ValueError): build_report([self.song,self.song])
        with self.assertRaises(ValueError): build_report([])

    def test_saved_summary_context_does_not_claim_series(self):
        request = context_request("chat", [self.song,self.song], "How is my timing?", [{"role":"user","text":"Hello"}])
        self.assertEqual(len(request["runs"]), 1)
        self.assertEqual(request["tier"], "B")
        self.assertEqual(request["runs"][0]["facts"]["sections"], [])
        self.assertIsNone(request["session"]["calibration_suspect"])
        self.assertEqual(request["history"][0]["text"], "Hello")

    def test_mismatched_game_files_are_excluded_from_comparisons(self):
        self.result["game_run"]["run"]["summary"]["total_notes"] = 500
        bad = summarize(self.result)
        self.assertFalse(bad.usable_for_coaching)
        report = build_report([bad])
        self.assertIsNone(report["groups"][0]["average_accuracy_pct"])

    def test_offline_fallback_needs_no_key_and_is_labelled(self):
        payload = song_request(self.result, OcrReview())
        with patch.dict(os.environ, {"RHYTHM_COACH_URL":""}):
            response = asyncio.run(get_coaching(payload))
        self.assertEqual(response["provider"], "offline")
        self.assertIn("26.16 ms late", response["coach"]["speech"])

    def test_gateway_sends_computed_facts_and_accepts_valid_coach(self):
        payload = song_request(self.result, OcrReview())
        coach = offline_reply(payload)
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            self.assertEqual(request.url.path, "/api/mentra/coach")
            return httpx.Response(200, json={"coach":coach})
        original = httpx.AsyncClient
        with patch.dict(os.environ, {"RHYTHM_COACH_URL":"http://coach.local"}), patch("coach_api.httpx.AsyncClient", side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw)):
            response = asyncio.run(get_coaching(payload))
        self.assertEqual(response["provider"], "rhythm_backend")
        self.assertEqual(seen[0]["runs"][0]["facts"]["overall"]["accuracy_pct"], 100)
        self.assertNotIn("samples", json.dumps(seen))

    def test_gateway_rejects_an_invented_section_and_falls_back(self):
        payload = song_request(screen_result(), OcrReview(reviewed=True))
        coach = offline_reply(payload); coach["focus_section"] = {"start_s":5,"end_s":10,"reason":"invented"}
        original = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"coach":coach}))
        with patch.dict(os.environ, {"RHYTHM_COACH_URL":"http://coach.local"}), patch("coach_api.httpx.AsyncClient", side_effect=lambda **kw: original(transport=transport, **kw)):
            response = asyncio.run(get_coaching(payload))
        self.assertEqual(response["provider"], "offline")
        self.assertIsNone(response["coach"]["focus_section"])

    def test_report_and_chat_endpoints_receive_phone_context(self):
        with TestClient(app) as client, patch.dict(os.environ, {"RHYTHM_COACH_URL":""}):
            response = client.post("/api/game-demo")
            job = response.json()["job_id"]; self.jobs.append(job)
            summary = client.post(f"/api/jobs/{job}/session-summary", json={"review":{}})
            self.assertEqual(summary.status_code, 200)
            report = client.post("/api/session-report", json={"songs":[summary.json()]})
            self.assertEqual(report.status_code, 200)
            chat = client.post("/api/coach-chat", json={"songs":report.json()["songs"], "question":"How is my timing?"})
            self.assertEqual(chat.status_code, 200)
            self.assertIn("26.16", chat.json()["coach"]["speech"])
            self.assertEqual(client.post("/api/report-coaching", json={"songs":report.json()["songs"]}).status_code, 200)
            self.assertEqual(client.post(f"/api/jobs/{job}/coaching", json={"review":{}}).json()["provider"], "offline")
            self.assertEqual(client.post("/api/coach-chat", json={"songs":[], "question":" "}).status_code, 400)
            invalid = summary.json(); invalid["accuracy_pct"] = 1000
            self.assertEqual(client.post("/api/session-report", json={"songs":[invalid]}).status_code, 422)
            self.assertEqual(client.get("/api/coach-status").json()["configured"], False)

    def test_malformed_coach_response_does_not_break_the_miniapp(self):
        payload = song_request(self.result, OcrReview())
        coach = offline_reply(payload); coach["focus_section"] = "invalid"
        original = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"coach":coach}))
        with patch.dict(os.environ, {"RHYTHM_COACH_URL":"http://coach.local"}), patch("coach_api.httpx.AsyncClient", side_effect=lambda **kw: original(transport=transport, **kw)):
            response = asyncio.run(get_coaching(payload))
        self.assertEqual(response["provider"], "offline")


if __name__ == "__main__": unittest.main()
