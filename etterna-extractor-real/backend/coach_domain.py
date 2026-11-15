"""Compact summaries, grouped session reports, and grounded coaching requests.

Reports are persisted by the miniapp on the phone. These functions are pure;
they do not store a timeline, API key, session, or chat conversation on disk.
"""
import math
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WeakestSection(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start_s: int = Field(ge=0)
    end_s: int = Field(gt=0)
    accuracy_pct: float = Field(ge=0, le=100)


class SongSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=100)
    source: Literal["custom_game_csv", "screen_ocr"]
    scoring_system: str = Field(min_length=1, max_length=150)
    title: str = Field(max_length=300)
    played_at: int = Field(ge=0)
    game_id: int | None = Field(default=None, ge=0)
    song_id: int | None = Field(default=None, ge=0)
    chart_id: int | None = Field(default=None, ge=0)
    difficulty: int | None = None
    game_time_ms: int | None = Field(default=None, ge=0)
    bpm: int | None = Field(default=None, ge=0)
    total_notes: int | None = Field(default=None, ge=0)
    score: int | None = Field(default=None, ge=0)
    score_max: int | None = Field(default=None, gt=0)
    accuracy_is_approximate: bool = False
    accuracy_coverage_uncertain: bool = False
    peak_nps: float | None = Field(default=None, ge=0)
    server_sequence: int | None = Field(default=None, ge=1)
    remote_session_id: str | None = None
    native_grade: str | None = Field(default=None, max_length=30)
    accuracy_pct: float | None = Field(default=None, ge=0, le=100)
    mean_offset_ms: float | None = None
    offset_spread_ms: float | None = Field(default=None, ge=0)
    weakest_section: WeakestSection | None = None
    tips: list[str] = Field(default_factory=list, max_length=30)
    data_notes: list[str] = Field(default_factory=list, max_length=30)
    reviewed: bool = False
    usable_for_coaching: bool = True


class OcrReview(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    reviewed: bool = False
    accuracy_pct: float | None = Field(default=None, ge=0, le=100)
    mean_offset_ms: float | None = None
    native_grade: str | None = Field(default=None, max_length=30)


def observed(data, group, key=None):
    item = data.get(group, {}) if key is None else data.get(group, {}).get(key, {})
    return item.get("value") if isinstance(item, dict) else None


def summarize(result, review=None):
    now = int(time.time()*1000)
    if result.get("game_run"):
        game = result["game_run"]
        run, analysis = game["run"], game["analysis"]
        summary = run["summary"]
        weakest = min([s for s in analysis["sections"] if s["accuracy"] is not None], key=lambda s: s["accuracy"], default=None)
        envelope = run.get("envelope", {})
        excluded = envelope.get("autoplay", False) or envelope.get("summary_exceeds_format_range", False)
        mismatch = run.get("format_version",1) == 1 and run["timeline_available"] and sum(s["nps"] for s in run["samples"]) != summary["total_notes"]
        return SongSummary(
            id="run-"+game["run_id"], source="custom_game_csv",
            scoring_system=f"custom_csv_game_{summary['game_id']}" if envelope or run.get("format_version")==2 else f"custom_million_point_game_{summary['game_id']}",
            title=f"Song {summary['song_id']}", played_at=int(datetime.fromisoformat(game['created_at'].replace('Z','+00:00')).timestamp()*1000) if game.get('created_at') else now,
            accuracy_is_approximate=analysis.get('accuracy_is_approximate',False),
            accuracy_coverage_uncertain=analysis.get('accuracy_coverage_uncertain',False),
            peak_nps=max((n['nps'] for n in run.get('notes',[])),default=None),
            server_sequence=game.get('sequence'),remote_session_id=game.get('session_id'),
            game_id=summary["game_id"], song_id=summary["song_id"], chart_id=run["chart_id"],
            difficulty=summary["difficulty"], game_time_ms=summary["game_time_ms"], bpm=summary["bpm"],
            total_notes=summary["total_notes"], score=analysis["score"], score_max=None if envelope or run.get("format_version")==2 else 1_000_000,
            native_grade=analysis["grade"], accuracy_pct=analysis["accuracy"]*100 if analysis["accuracy"] is not None else None,
            mean_offset_ms=analysis["mean_offset_ms"], tips=[] if mismatch or excluded else [t["text"] for t in analysis["tips"]],
            weakest_section={"start_s": weakest["start_ms"]//1000,
                             "end_s": math.ceil(min(weakest["end_ms"], summary["game_time_ms"])/1000),
                             "accuracy_pct": weakest["accuracy"]*100} if weakest else None,
            offset_spread_ms=analysis.get("spread_ms"), data_notes=run["warnings"], reviewed=True, usable_for_coaching=not mismatch and not excluded)
    if result.get("source") != "screen" or not result.get("data"):
        raise ValueError("This result has no game or screen statistics to save")
    review = review or OcrReview()
    if not review.reviewed:
        raise ValueError("Review the OCR values before saving or coaching this screen result")
    data = result["data"]
    accuracy = observed(data, "accuracy_percent")
    mean = observed(data, "timing", "mean_ms")
    native_grade = observed(data, "grade")
    # Explicitly supplied null means the reviewer could not verify the value.
    for key, value in review.model_dump(exclude_unset=True).items():
        if key == "accuracy_pct": accuracy = value
        if key == "mean_offset_ms": mean = value
        if key == "native_grade": native_grade = value
    wife, judge = observed(data, "wife_version"), observed(data, "judge_setting")
    identifier = "scan-"+result["job_id"]
    label_confidence = data.get("accuracy_label", {}).get("ocr_confidence") or 0
    metric = f"etterna_wife_{wife}_judge_{judge}" if wife is not None and judge is not None and label_confidence >= 65 else "unverified_metric_"+identifier
    title = str(data.get("song_text") or "Scanned results").splitlines()[0][:300]
    return SongSummary(id=identifier, source="screen_ocr", scoring_system=metric, title=title,
                      played_at=now, native_grade=native_grade, accuracy_pct=accuracy, mean_offset_ms=mean,
                      offset_spread_ms=None, reviewed=True,
                      usable_for_coaching=accuracy is not None or mean is not None,
                      data_notes=["User reviewed the screen summary. Missing fields remain unknown.",
                                  "Screen OCR provides no exact per-second timeline, BPM, song length, or custom-game score.",
                                  "Only the reviewed accuracy, mean timing and native grade are used for coaching."])


def average(values):
    values = [v for v in values if v is not None]
    return sum(values)/len(values) if values else None


def build_report(songs):
    if not songs:
        raise ValueError("Add at least one result to the current session first")
    ids = [s.id for s in songs]
    if len(set(ids)) != len(ids):
        raise ValueError("A result appears more than once in this session")
    songs = sorted(songs, key=lambda s: s.played_at)
    if songs and all(s.remote_session_id and s.remote_session_id==songs[0].remote_session_id and s.server_sequence for s in songs):
        songs=sorted(songs,key=lambda s:s.server_sequence)
    grouped = defaultdict(list)
    for song in songs:
        grouped[song.scoring_system].append(song)
    groups, highlights = [], []
    for system, entries in grouped.items():
        if entries and all(s.remote_session_id and s.remote_session_id==entries[0].remote_session_id and s.server_sequence for s in entries):
            entries=sorted(entries,key=lambda s:s.server_sequence)
        valid = [s for s in entries if s.usable_for_coaching]
        accuracies = [s for s in valid if s.accuracy_pct is not None]
        mean_accuracy = average([s.accuracy_pct for s in valid])
        mean_timing = average([s.mean_offset_ms for s in valid])
        best = max(accuracies, key=lambda s: s.accuracy_pct, default=None)
        change = accuracies[-1].accuracy_pct-accuracies[0].accuracy_pct if len(accuracies) >= 2 else None
        group = {"scoring_system": system, "song_count": len(entries), "verified_song_count": len(valid),
                 "accuracy_measurement_count":len(accuracies),"timing_measurement_count":sum(s.mean_offset_ms is not None for s in valid),"average_accuracy_pct": mean_accuracy, "average_offset_ms": mean_timing,
                 "first_to_last_change_pct": change,
                 "first_accuracy_pct": accuracies[0].accuracy_pct if accuracies else None,
                 "last_accuracy_pct": accuracies[-1].accuracy_pct if accuracies else None, "best_song": best.title if best else None}
        timing=[s for s in valid if s.mean_offset_ms is not None]
        spreads=[s for s in valid if s.offset_spread_ms is not None]
        bpms=[s for s in valid if s.bpm is not None]
        densities=[s for s in valid if s.peak_nps is not None]
        worst=min(accuracies,key=lambda s:s.accuracy_pct,default=None)
        group.update(accuracy_is_approximate=any(s.accuracy_is_approximate for s in accuracies),
            weakest_song=worst.title if worst else None,
            timing_bias_first_ms=timing[0].mean_offset_ms if timing else None,timing_bias_last_ms=timing[-1].mean_offset_ms if timing else None,
            timing_distance_change_ms=abs(timing[-1].mean_offset_ms)-abs(timing[0].mean_offset_ms) if len(timing)>1 else None,
            spread_first_ms=spreads[0].offset_spread_ms if spreads else None,spread_last_ms=spreads[-1].offset_spread_ms if spreads else None,
            bpm_first=bpms[0].bpm if bpms else None,bpm_last=bpms[-1].bpm if bpms else None,
            peak_density_first=densities[0].peak_nps if densities else None,peak_density_last=densities[-1].peak_nps if densities else None,
            repeated_early=sum(s.mean_offset_ms < -20 for s in timing),repeated_late=sum(s.mean_offset_ms > 20 for s in timing),
            repeated_spread=sum(s.offset_spread_ms > 15 for s in spreads))
        groups.append(group)
        if best:
            highlights.append(f"{system}: highest {"approximate" if group["accuracy_is_approximate"] else "displayed"} accuracy was {best.accuracy_pct:.1f}% on {best.title}.")
        if change is not None:
            highlights.append(f"{system}: first-to-last accuracy changed by {change:+.2f} percentage points; charts may differ.")
        if mean_timing is not None:
            highlights.append(f"{system}: mean timing was {abs(mean_timing):.2f} ms {'early' if mean_timing < 0 else 'late' if mean_timing > 0 else 'from zero'}.")
    next_steps=[]
    for group in groups:
        if group['weakest_song']:
            highlights.append(f"Lowest available {'approximate ' if group['accuracy_is_approximate'] else ''}accuracy: {group['weakest_song']}. Different charts limit comparisons.")
        change=group['timing_distance_change_ms']
        if change is not None:
            highlights.append(f"Mean timing moved {abs(change):.2f} ms {'closer to' if change<0 else 'farther from' if change>0 else 'relative to'} zero from first to last; this is a bias comparison, not proof of skill improvement.")
        if group['spread_first_ms'] is not None and group['spread_last_ms'] is not None:
            highlights.append(f"Successful-hit timing spread: {group['spread_first_ms']:.2f} to {group['spread_last_ms']:.2f} ms.")
        if group['bpm_first'] is not None and group['bpm_last'] is not None:
            highlights.append(f"Nominal BPM: {group['bpm_first']} to {group['bpm_last']}.")
        if group['peak_density_first'] is not None and group['peak_density_last'] is not None:
            highlights.append(f"Peak sampled density: {group['peak_density_first']:g} to {group['peak_density_last']:g} notes per second.")
        for label,key in [('early bias','repeated_early'),('late bias','repeated_late'),('timing spread','repeated_spread')]:
            if group[key]>=2: highlights.append(f"Repeated {label} in {group[key]} saved attempts (rule-based thresholds).")
        if group['repeated_early']>=2 or group['repeated_late']>=2:
            next_steps.append('Practice centering your successful inputs closer to zero milliseconds, then compare another attempt on the same chart.')
        if group['repeated_spread']>=2:
            next_steps.append('Retry a chart already represented in this report and compare whether successful-hit timing spread becomes smaller.')
    next_steps=list(dict.fromkeys(next_steps))[:2] or ['Replay a chart represented here and compare the available accuracy estimate and timing, keeping game settings consistent.']
    created_at = int(time.time()*1000)
    report = {"id": "report-"+uuid.uuid4().hex, "created_at": created_at,
              "songs": [s.model_dump() for s in songs], "groups": groups, "highlights": highlights}
    lines = [f"Session report: {len(songs)} plays. Scoring systems are compared separately."]+highlights
    for song in songs:
        accuracy = f"{song.accuracy_pct:.2f}%" if song.accuracy_pct is not None else "unknown accuracy"
        timing = f"{song.mean_offset_ms:+.2f} ms" if song.mean_offset_ms is not None else "unknown timing"
        lines.append(f"{song.title} [{song.scoring_system}]: {accuracy}, {timing}, native grade {song.native_grade or 'unknown'}.")
        lines.extend("Tip: "+tip for tip in song.tips)
    report["text"] = "\n".join(lines)
    report['next_steps']=next_steps
    observations=[]
    for group in groups[:2]:
        parts=[]
        label='approximate captured accuracy' if group['accuracy_is_approximate'] else 'displayed accuracy'
        if group['first_accuracy_pct'] is not None:
            parts.append(f"{label} went from {group['first_accuracy_pct']:.1f} to {group['last_accuracy_pct']:.1f} percent" if group['accuracy_measurement_count']>1 else f"available {label} was {group['first_accuracy_pct']:.1f} percent")
        if group['best_song']:
            parts.append(f"highest available accuracy was on {group['best_song']}, and lowest on {group['weakest_song']}")
        if group['timing_bias_first_ms'] is not None:
            parts.append(f"mean timing changed from {group['timing_bias_first_ms']:+.2f} to {group['timing_bias_last_ms']:+.2f} milliseconds, where negative is early and positive is late" if group['timing_measurement_count']>1 else f"available mean timing was {group['timing_bias_first_ms']:+.2f} milliseconds, where negative is early and positive is late")
        if group['bpm_first'] is not None:
            parts.append(f"nominal BPM changed from {group['bpm_first']} to {group['bpm_last']}")
        if group['peak_density_first'] is not None:
            parts.append(f"peak sampled density changed from {group['peak_density_first']:g} to {group['peak_density_last']:g} notes per second")
        if group['repeated_early']>=2: parts.append('early bias recurred')
        if group['repeated_late']>=2: parts.append('late bias recurred')
        if group['repeated_spread']>=2: parts.append('wide timing spread recurred')
        observations.append('; '.join(parts)+'.' if parts else 'Comparable measurements were unavailable for this scoring group.')
    report["spoken_summary"] = f"Across {len(songs)} saved attempts, "+' '.join(observations)+' Different charts limit comparisons.'+(' Additional scoring groups are detailed in the full report.' if len(groups)>2 else '')+"\n\nFor your next session, "+' '.join(next_steps)
    report['text'] += "\n\nNext steps: " + " ".join(next_steps)
    return report


def summary_facts(song):
    return {"source": "screen_ocr" if song.source == "screen_ocr" else "custom_game_summary", "tier": "B",
            "song": {"title": song.title, "game_id": song.game_id, "song_id": song.song_id,
                     "difficulty": song.difficulty, "game_time_ms": song.game_time_ms, "bpm": song.bpm,
                     "note_count": song.total_notes, "score": song.score,
                     "accuracy_is_approximate": song.accuracy_is_approximate, "peak_nps": song.peak_nps, "score_max": song.score_max,
                     "native_grade": song.native_grade, "scoring_system": song.scoring_system},
            "facts": {"overall": {"accuracy_pct": song.accuracy_pct, "offset_mean_ms": song.mean_offset_ms,
                                   "offset_spread_ms": song.offset_spread_ms, "notes": song.total_notes},
                      "sections": [], "weakest_section": song.weakest_section.model_dump() if song.weakest_section else None,
                      "usable_for_coaching": song.usable_for_coaching, "data_notes": song.data_notes + (["Accuracy is approximate, from rounded V2 deltas; never describe it as exact."] if song.accuracy_is_approximate else [])}}


def song_request(result, review):
    summary = summarize(result, review)
    facts = summary_facts(summary)
    if result.get("game_run") and result["game_run"]["run"].get("format_version") != 2 and result["game_run"]["analysis"]["sections"]:
        game = result["game_run"]
        facts["source"], facts["tier"] = "custom_game_csv", "A"
        facts["facts"]["sections"] = [{"start_s": s["start_ms"]//1000,
            "end_s": math.ceil(min(s["end_ms"], summary.game_time_ms)/1000),
            "accuracy_pct": s["accuracy"]*100 if s["accuracy"] is not None else None, "offset_mean_ms": s["mean_offset_ms"],
            "offset_spread_ms": s["spread_ms"]} for s in game["analysis"]["sections"]]
    return {"mode": "song_debrief", "tier": facts["tier"], "question": None, "runs": [facts],
            "session": None, "history": []}


def context_request(mode, songs, question=None, history=None):
    # Saved reports retain summaries, not the original per-second timeline.
    unique = {s.id: s for s in songs}
    recent = sorted(unique.values(), key=lambda s: s.played_at)[-20:]
    report = build_report(recent) if recent else None
    return {"mode": mode, "tier": "B" if recent else None, "question": question,
            "runs": [summary_facts(s) for s in recent],
            "session": {"song_count": len(recent), "groups": report["groups"], "calibration_suspect": None, "two_paragraph_report": report["spoken_summary"], "next_steps": report["next_steps"]} if report else None,
            "history": history or []}


def offline_reply(payload):
    runs = payload["runs"]
    usable = [r for r in runs if r["facts"]["usable_for_coaching"]]
    question = (payload.get("question") or "").lower()
    offsets = [r["facts"]["overall"]["offset_mean_ms"] for r in usable]
    mean = average(offsets)
    focus = "none"
    if not usable:
        speech = "I do not have verified performance data yet. Add a game result or review a screen scan first. I can then discuss the numbers you have saved."
    elif payload["mode"] == "session_debrief":
        speech = f"This report contains {len(runs)} plays. Compare accuracy within the same scoring group; different games and scoring systems are kept separate."
        if mean is not None and len({r['song']['scoring_system'] for r in usable}) == 1:
            speech += f" Mean timing was {abs(mean):.2f} ms {'early' if mean < 0 else 'late' if mean > 0 else 'from zero'}."
    elif payload["mode"] == "song_debrief" or any(w in question for w in ("timing", "late", "early", "offset", "latency")):
        if mean is None:
            speech = "Timing is not available in the saved data. I cannot infer it from the score or accuracy."
        elif len({r['song']['scoring_system'] for r in usable}) > 1:
            speech = "These plays use different scoring systems. Open a session report to see timing separately for each scoring group."
        else:
            focus = "timing_bias"
            speech = f"The available mean timing is {abs(mean):.2f} ms {'early' if mean < 0 else 'late' if mean > 0 else 'from zero'}. Practice keeping taps aligned with the beat and compare your next result in the same game."
    elif any(w in question for w in ("best", "highest", "worst", "hardest", "lowest")):
        groups = defaultdict(list)
        for run in usable:
            if run["facts"]["overall"]["accuracy_pct"] is not None:
                groups[run["song"]["scoring_system"]].append(run)
        lines = []
        for group, entries in groups.items():
            choose = min if any(w in question for w in ("worst", "hardest", "lowest")) else max
            chosen = choose(entries, key=lambda r: r["facts"]["overall"]["accuracy_pct"])
            lines.append(f"{group}: {chosen['song']['title']} at {"approximately " if chosen["song"].get("accuracy_is_approximate") else ""}{chosen['facts']['overall']['accuracy_pct']:.1f}%.")
        speech = " ".join(lines) or "No verified accuracy is available yet."
    elif any(w in question for w in ("improv", "trend", "progress")):
        groups = payload.get("session", {}).get("groups", []) if payload.get("session") else []
        lines = [f"{g['scoring_system']}: first-to-last displayed accuracy changed by {g['first_to_last_change_pct']:+.2f} percentage points."
                 for g in groups if g["first_to_last_change_pct"] is not None]
        speech = " ".join(lines) or "Save at least two comparable plays to inspect a first-to-last accuracy change."
    elif any(w in question for w in ("count", "many", "session", "report")):
        session = payload.get("session") or {}
        speech = (f"You have {session['report_count']} saved reports and {session.get('current_count', 0)} plays in the current session. "
                  if "report_count" in session else "")
        speech += f"The current coaching context contains {len(runs)} distinct recent plays. Open Reports to inspect each saved session."
    else:
        speech = "The offline coach can discuss saved timing, highest or lowest accuracy within each scoring group, first-to-last accuracy changes, and play counts. Ask about one of those, or configure RhythmBackend for open conversation."
    if payload["mode"] == "session_debrief" and payload.get("session",{}).get("two_paragraph_report"):
        speech=payload['session']['two_paragraph_report']
    return {"mode": payload["mode"], "tier": payload["tier"], "coaching_focus": focus,
            "speech": speech, "phone_text": [speech], "what_went_well": None, "observations": [], "drill": None, "next_target": None,
            "focus_section": None, "data_notes": ["Offline rule-based reply; no Gemini request was made successfully."],
            "confidence": "low", "evidence_basis": "game_heuristic" if focus != "none" else "none"}
