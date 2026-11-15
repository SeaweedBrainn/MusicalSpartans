"""Custom-game CSV import and analysis compatible with MusicalSpartans.

Independent Python implementation of the formats/algorithm inspected at
SeaweedBrainn/MusicalSpartans commit 92dfd9d74f1fc7efd3637280f89705ced8cb862f.
Etterna OCR results never pass through this million-point scoring model.
"""
import csv
import io
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "mentra-run:v1:"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
STORE = Path(os.getenv("GAME_RUN_DIR", str(Path(__file__).parent / "run-data")))
MAX_CSV_BYTES = 2 * 1024 * 1024


def rows(text):
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text.lstrip("\ufeff")))
            if any(c.strip() for c in row)]


def integer(value, label, minimum=0):
    if not re.fullmatch(r"[+\-]?\d+", value):
        raise ValueError(f"{label} must be an integer")
    number = int(value)
    if number < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return number


def number(value, label):
    try:
        result = float(value)
    except ValueError:
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def parse_summary(text, allow_zero_duration=False):
    records = rows(text)
    if len(records) != 1 or len(records[0]) != 8:
        raise ValueError("Summary must be one headerless row with exactly 8 values")
    row = records[0]
    keys = ("game_id", "song_id", "difficulty", "game_time_ms", "bpm", "total_notes", "score")
    result = {key: integer(row[i], key) for i, key in enumerate(keys)}
    result["average_latency_ms"] = number(row[7], "average latency")
    if not 1 <= result["difficulty"] <= 4:
        raise ValueError("Difficulty must be 1, 2, 3, or 4")
    if result["game_time_ms"] < 0 or result["game_time_ms"] == 0 and not allow_zero_duration:
        raise ValueError("Song length must be greater than zero")
    if result["score"] > 1_000_000:
        raise ValueError("Custom-game score must be between 0 and 1,000,000")
    return result


def parse_timeline(text):
    records = rows(text)
    if any(row[0] == 'format_version' for row in records):
        from csv_v2 import parse
        return parse(records)
    index = next((i for i, row in enumerate(records) if row[0].lower() == "game_time"), None)
    if index is None:
        raise ValueError("Timeline needs a game_time header after its metadata")
    metadata = {}
    for row in records[:index]:
        if len(row) != 2 or row[0].lower() in metadata:
            raise ValueError("Timeline metadata must be unique name,value pairs")
        metadata[row[0].lower()] = row[1]
    for key in ("game_id", "song_id", "chart_id"):
        if key not in metadata:
            raise ValueError(f"Timeline metadata is missing {key}")
    header = [c.lower() for c in records[index]]
    required = {"game_time", "percent_accuracy", "avg_latency", "bpm", "nps", "latency_spread"}
    if len(header) != len(set(header)) or not required.issubset(header):
        raise ValueError("Timeline header must include each of the six game columns once")
    interval = number(metadata.get("sample_interval_sec", "1"), "sample interval")
    if interval <= 0:
        raise ValueError("Sample interval must be positive")
    samples = []
    for line_index, row in enumerate(records[index+1:], start=index+2):
        if len(row) != len(header):
            raise ValueError(f"Timeline row {line_index} has the wrong number of columns")
        values = dict(zip(header, row))
        time = number(values["game_time"], "game_time")
        if time < 0 or (samples and time <= samples[-1]["time_sec"]):
            raise ValueError("Timeline times must be nonnegative and strictly increasing")
        percent = number(values["percent_accuracy"], "percent accuracy") if values["percent_accuracy"] else None
        if percent is not None and not 0 <= percent <= 100:
            raise ValueError("Timeline percent_accuracy must be between 0 and 100")
        spread = number(values["latency_spread"], "latency spread") if values["latency_spread"] else None
        if spread is not None and spread < 0:
            raise ValueError("Latency spread cannot be negative")
        samples.append({"time_sec": time, "accuracy": percent/100 if percent is not None else None,
                        "avg_latency_ms": number(values["avg_latency"], "average latency") if values["avg_latency"] else None,
                        "bpm": number(values["bpm"], "bpm") if values["bpm"] else None, "nps": integer(values["nps"], "nps"),
                        "latency_spread_ms": spread})
        if len(samples) > 20000:
            raise ValueError("Timeline exceeds 20,000 samples")
    return {"game_id": integer(metadata["game_id"], "game_id"),
            "song_id": integer(metadata["song_id"], "song_id"),
            "chart_id": integer(metadata["chart_id"], "chart_id"),
            "sample_interval_sec": interval, "samples": samples}


def import_run(summary_text, timeline_text=None):
    timeline = parse_timeline(timeline_text) if timeline_text is not None else None
    summary = parse_summary(summary_text, allow_zero_duration=bool(timeline and timeline.get("format_version")==2))
    if timeline and any(timeline[key] != summary[key] for key in ("game_id", "song_id")):
        raise ValueError("Summary and timeline must be from the same game and song")
    warnings = []
    if timeline and timeline.get("format_version",1) == 1 and sum(s["nps"] for s in timeline["samples"]) != summary["total_notes"]:
        warnings.append("Timeline note count differs from the game's summary; original values are retained.")
    if not timeline:
        warnings.append("Summary only: section coaching requires the optional timeline CSV.")
    return {"format_version": timeline.get("format_version",1) if timeline else 1,
            "notes": timeline.get("notes",[]) if timeline else [],
            "nominal_bpm": timeline.get("nominal_bpm") if timeline else None,
            "summary": summary, "chart_id": timeline["chart_id"] if timeline else None,
            "samples": timeline["samples"] if timeline else [], "timeline_available": timeline is not None,
            "sample_interval_sec": timeline["sample_interval_sec"] if timeline else None,
            "video_uri": None, "video_offset_ms": None, "warnings": warnings}


def weighted(samples, key):
    values = [(s[key], s["nps"]) for s in samples if s[key] is not None and s["nps"] > 0]
    count = sum(n for _, n in values)
    return sum(value*n for value, n in values)/count if count else None


def grade(accuracy):
    return next(label for floor, label in ((1, "Perfect"), (.95, "S"), (.9, "A"), (.8, "B"), (.7, "C"), (0, "Fail"))
                if accuracy >= floor)


def analyze(run):
    if run.get('format_version') == 2:
        from csv_v2 import analyze as analyze_notes
        return analyze_notes(run)
    summary = run["summary"]
    played = [s for s in run["samples"] if s["nps"] > 0 and s["accuracy"] is not None]
    envelope = run.get("envelope")
    bucket_seconds = math.lcm(5, int(run["sample_interval_sec"])) if envelope else 5
    groups = {}
    for sample in played:
        groups.setdefault(int(sample["time_sec"]//bucket_seconds), []).append(sample)
    offset = weighted(played, "avg_latency_ms")
    if offset is None:
        offset = summary["average_latency_ms"]
    if envelope:
        offset = summary["average_latency_ms"] if envelope["successful_hit_count"] > 0 else None
    sections, tips = [], []
    if offset is not None and abs(offset) > 20:
        direction = "late" if offset > 0 else "early"
        tips.append({"time_ms": 0, "spans_song": True,
                     "text": f"Your hits averaged {math.floor(abs(offset)+.5)} ms {direction} across the song. If this repeats across songs, review the game's audio offset."})
    for bucket, samples in sorted(groups.items()):
        spreads = [s["latency_spread_ms"] for s in samples if s["latency_spread_ms"] is not None]
        section = {"start_ms": bucket*bucket_seconds*1000, "end_ms": min((bucket+1)*bucket_seconds*1000, summary["game_time_ms"]),
                   "accuracy": weighted(samples, "accuracy"), "mean_offset_ms": weighted(samples, "avg_latency_ms"),
                   "spread_ms": sum(spreads)/len(spreads) if spreads else None}
        if envelope:
            section["mean_offset_ms"] = None
            section["spread_ms"] = None
        sections.append(section)
        drift = section["mean_offset_ms"]-offset if section["mean_offset_ms"] is not None and offset is not None else None
        text = None
        if section["accuracy"] < .9:
            text = f"Accuracy dropped to {math.floor(section['accuracy']*100+.5)}% in this section."
        elif drift is not None and drift < -20:
            text = f"Hits were {math.floor(-drift+.5)} ms earlier than your song average in this section."
        elif drift is not None and drift > 20:
            text = f"Hits were {math.floor(drift+.5)} ms later than your song average in this section."
        elif section["spread_ms"] is not None and section["spread_ms"] > 15:
            text = f"Timing was inconsistent in this section (spread {math.floor(section['spread_ms']+.5)} ms)."
        if text:
            tips.append({"time_ms": bucket*bucket_seconds*1000, "spans_song": False, "text": text})
    if envelope and (envelope["autoplay"] or envelope["summary_exceeds_format_range"]):
        tips = []
    accuracy = summary["score"]/1_000_000
    letter = grade(accuracy)
    if envelope:
        accuracy = None
        letter = None
    spoken = f"You scored {summary['score']}, grade {letter}. " + (tips[0]["text"] if tips else "No timing issue was flagged by these rules.")
    if envelope:
        spoken = f"Game score {summary['score']}. Overall accuracy was not supplied. " + (tips[0]["text"] if tips else "Review the available CSV measurements.")
    if envelope and offset is None:
        spoken += " Timing is unavailable: no successful hits were recorded."
    if envelope and (envelope["autoplay"] or envelope["summary_exceeds_format_range"]):
        spoken = "Game run loaded. Player coaching is disabled for autoplay or format-limited data."
    return {"score": summary["score"], "accuracy": accuracy, "grade": letter, "mean_offset_ms": offset,
            "sections": sections, "tips": tips, "spoken_summary": spoken, "method": "rule_based_custom_game_v1"}


def run_directory(run_id):
    if not ID_PATTERN.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    directory = STORE / run_id
    if not directory.is_dir():
        raise FileNotFoundError("Game run not found on this backend. Upload the game's CSV files here first.")
    return directory


def create_run(summary_text, timeline_text=None):
    run = import_run(summary_text, timeline_text)
    analysis = analyze(run)
    run_id = uuid.uuid4().hex
    directory = STORE / run_id
    directory.mkdir(parents=True)
    (directory / "summary.csv").write_text(summary_text, encoding="utf-8")
    if timeline_text is not None:
        (directory / "timeline.csv").write_text(timeline_text, encoding="utf-8")
    result = {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
              "run": run, "analysis": analysis}
    (directory / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result


def load_run(run_id):
    return json.loads((run_directory(run_id) / "result.json").read_text(encoding="utf-8"))


def resolve_qr(payload):
    if not payload.startswith(PREFIX):
        return None
    try:
        result = load_run(payload[len(PREFIX):])
    except (ValueError, FileNotFoundError) as error:
        return {"status": "qr_found", "source": "qr", "qr_payload": payload, "csv": None, "warnings": [str(error)]}
    return {"status": "run_analyzed", "source": "game_csv", "qr_payload": payload,
            "game_run": result, "warnings": result["run"]["warnings"], "crops": {}}
