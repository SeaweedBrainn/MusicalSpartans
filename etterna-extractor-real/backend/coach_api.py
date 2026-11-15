import json
import asyncio
import os
import re
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from coach_domain import OcrReview, SongSummary, build_report, context_request, offline_reply, song_request, summarize

router = APIRouter()


class ReviewBody(BaseModel):
    review: OcrReview = Field(default_factory=OcrReview)


class SongsBody(BaseModel):
    songs: list[SongSummary] = Field(max_length=200)


class ChatTurn(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    text: str = Field(min_length=1, max_length=2000)


class ChatBody(SongsBody):
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    report_notes: list[Annotated[str, Field(max_length=12000)]] = Field(default_factory=list,max_length=10)
    report_count: int = Field(default=0, ge=0)
    current_count: int = Field(default=0, ge=0)


def load_job(job_id):
    from server import directory_for
    return json.loads((directory_for(job_id) / "result.json").read_text())


def validate_coach(output, payload):
    if not isinstance(output, dict):
        raise ValueError("Coach returned no structured reply")
    tiers=payload["tier"] if isinstance(payload["tier"],tuple) else (payload["tier"],)
    if output.get("mode") != payload["mode"] or output.get("tier") not in tiers:
        raise ValueError("Coach reply has the wrong mode or evidence tier")
    if not isinstance(output.get("speech"), str) or not output["speech"].strip():
        raise ValueError("Coach reply has no speech")
    if not isinstance(output.get("phone_text"), list) or any(not isinstance(t, str) for t in output["phone_text"]):
        raise ValueError("Coach reply has invalid phone text")
    if not isinstance(output.get("data_notes"), list) or any(not isinstance(t, str) for t in output["data_notes"]):
        raise ValueError("Coach reply has invalid data notes")
    if output.get("confidence") not in ("low", "medium", "high"):
        raise ValueError("Coach reply has invalid confidence")
    if len(output["speech"]) > 12000:
        raise ValueError("Coach speech exceeds supported size")
    if output.get("coaching_focus") not in {"judgement_quality","combo_continuity","recovery_after_miss","density_or_difficulty","consistency","lane_execution","timing_bias","timing_spread","calibration_check","progression","data_quality","none","density"}:
        raise ValueError("Coach focus is invalid")
    if output.get("evidence_basis") not in {"measured_run_data","cross_run_pattern","game_heuristic","practice_convention","mixed_evidence","none","meta_analysis","lab_consensus"}:
        raise ValueError("Coach evidence basis is invalid")
    for field in ("what_went_well","drill","next_target"):
        if output.get(field) is not None and not isinstance(output[field],str): raise ValueError("Invalid coach text field")
    observations=output.get("observations",[])
    if not isinstance(observations,list) or len(observations)>3 or any(not isinstance(o,dict) or set(o)!={"label","value","interpretation"} or any(not isinstance(v,str) for v in o.values()) for o in observations):
        raise ValueError("Invalid coaching observations")
    output={**output,"what_went_well":output.get("what_went_well"),"observations":observations}
    if output.get("focus_section") is not None:
        sections = payload["runs"][0]["facts"]["sections"] if len(payload["runs"]) == 1 else []
        focus = output["focus_section"]
        if not isinstance(focus, dict) or type(focus.get("start_s")) is not int or type(focus.get("end_s")) is not int or focus["start_s"] < 0 or focus["end_s"] <= focus["start_s"] or not isinstance(focus.get("reason"),str) or not focus["reason"].strip():
            raise ValueError("Coach reply has an invalid focus section")
        if payload["mode"] != "song_debrief" or payload["tier"] != "A" or not any(
            focus.get("start_s") == s["start_s"] and focus.get("end_s") == s["end_s"] for s in sections):
            raise ValueError("Coach reply references an unavailable section")
    return output


@router.get("/api/coach-status")
async def coach_status():
    base = os.getenv("RHYTHM_COACH_URL", "").strip().rstrip("/")
    if not base:
        return {"configured": False, "reachable": False, "gemini_configured": False}
    try:
        url = httpx.URL(base)
        if url.scheme not in ("http", "https") or not url.host or url.path not in ("", "/") or url.query or url.fragment or url.username or url.password:
            raise ValueError("Use a coach server origin without credentials, path, or query")
        async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
            response = await client.get(base+"/api/mentra/health")
            response.raise_for_status()
            info = response.json()
        return {"configured": True, "reachable": True, "gemini_configured": bool(info.get("gemini_configured"))}
    except (httpx.HTTPError, ValueError):
        return {"configured": True, "reachable": False, "gemini_configured": False}


async def get_coaching(payload):
    base = os.getenv("RHYTHM_COACH_URL", "").strip().rstrip("/")
    reason = "RhythmBackend is not configured."
    if base:
        try:
            url = httpx.URL(base)
            if url.scheme not in ("http", "https") or not url.host or url.path not in ("", "/") or url.query or url.fragment or url.username or url.password:
                raise ValueError("RHYTHM_COACH_URL must be a server origin without a path")
            async with httpx.AsyncClient(timeout=55, trust_env=False) as client:
                response = await client.post(base+"/api/mentra/coach", json=payload)
                response.raise_for_status()
                output = validate_coach(response.json().get("coach"), payload)
            return {"provider": "rhythm_backend", "coach": output, "fallback_reason": None}
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            reason = f"RhythmBackend returned HTTP {status}. " + (
                "Apply the integration patch to enable its Mentra endpoint." if status == 404 else
                "Configure its Gemini key before using AI coaching." if status == 503 else
                "Check the coach-service log; offline coaching is shown instead.")
            # Only surface a bounded diagnostic code, never provider bodies or credentials.
            try:
                code = error.response.json().get("errorCode")
                if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,64}", code):
                    reason += f" Diagnostic code: {code}."
            except (ValueError, AttributeError):
                pass
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # Never drop the player's data because the AI service is unavailable.
            reason = "RhythmBackend was unavailable or rejected the reply. The offline coach is shown instead."
    return {"provider": "offline", "coach": offline_reply(payload), "fallback_reason": reason}


def validate_session_coach(output, payload, result):
    # The native endpoint sees raw CSV windows, rather than just our five-second
    # aggregates. Accept focus windows only when present in those actual data.
    import copy
    import math
    grounding = copy.deepcopy(payload)
    # Native CSV coaching declares Tier A even when all CSV windows are empty.
    grounding["tier"] = "A"
    grounding["runs"][0]["tier"] = "A"
    run = result['game_run']['run']
    sections = grounding['runs'][0]['facts']['sections']
    interval = run['sample_interval_sec']
    duration = run['summary']['game_time_ms']/1000
    if run.get('format_version') == 2:
        for note in run['notes']:
            start=note['time_ms']//1000
            sections.append({'start_s':start, 'end_s':start+1})
        for section in result['game_run']['analysis']['sections']:
            sections.append({'start_s':section['start_ms']//1000,'end_s':section['end_ms']//1000})
    else:
        for sample in run['samples']:
            if sample['nps'] > 0 and sample['time_sec'] < duration and any(sample[k] is not None for k in ('accuracy', 'avg_latency_ms', 'latency_spread_ms')):
                sections.append({'start_s': int(sample['time_sec']),
                                 'end_s': math.ceil(min(sample['time_sec']+interval, duration))})
    if run.get('format_version') == 2 and isinstance(output,dict) and isinstance(output.get('focus_section'),dict):
        focus=output['focus_section']
        start,end=focus.get('start_s'),focus.get('end_s')
        bound=max(math.ceil(duration),max((n['time_ms']//1000+1 for n in run['notes']),default=0))
        if type(start) is int and type(end) is int and 0 <= start < end <= bound and any(
                start*1000 <= n['time_ms'] < end*1000 for n in run['notes']):
            sections.append({'start_s':start,'end_s':end})
    output = validate_coach(output, grounding)
    speech = output['speech']
    if not 30 <= len(speech.split()) <= 120 or len(speech) > 4000 or re.search(r'https?://|\[[^\]]*\]', speech, re.I):
        raise ValueError('Session coach speech violated the current 30–120 word contract')
    focus = output.get('coaching_focus')
    if focus in ('calibration_check',):
        raise ValueError('Session coach used an unsupported focus')
    observations = run.get('notes',[]) if run.get('format_version')==2 else run['samples']
    if focus == 'density' and not any(s['nps'] > 0 for s in observations):
        raise ValueError('Session coach inferred density without playable notes')
    if focus == 'timing_bias' and run['envelope']['successful_hit_count'] == 0:
        raise ValueError('Session coach inferred timing without successful hits')
    if focus == 'timing_spread' and not any(s.get('std_ms' if run.get('format_version')==2 else 'latency_spread_ms') is not None for s in observations):
        raise ValueError('Session coach inferred unavailable spread')
    if focus in ('judgement_quality','combo_continuity','lane_execution') and not run.get('notes'):
        raise ValueError('Coach inferred note judgments without note-level data')
    if focus == 'recovery_after_miss' and not any(n['judgement']=='M' for n in run.get('notes',[])[:-1]):
        raise ValueError('Coach inferred recovery without a recorded miss and later notes')
    if output.get('evidence_basis') == 'cross_run_pattern':
        raise ValueError('Single-run coaching cannot establish a cross-run pattern')
    for field in ('drill','next_target'):
        if output.get(field) is not None and not isinstance(output[field], str):
            raise ValueError('Session coach advice field is invalid')
    return output


async def get_job_coaching(result, payload):
    remote = result.get('remote_session')
    if not remote or not result.get('game_run'):
        return await get_coaching(payload)
    # Never send autoplay, clamped or mismatched data for player advice.
    if not payload['runs'][0]['facts']['usable_for_coaching']:
        return {'provider':'offline', 'coach':offline_reply(payload), 'coaching_route':'session_api',
                'fallback_reason':'Player coaching is disabled for autoplay, format-limited or mismatched data.'}
    from session_qr import SessionReadError, coach_run
    try:
        output = await asyncio.to_thread(coach_run, remote['handle'], remote['selected_run_id'])
        output = validate_session_coach(output, payload, result)
        return {'provider':'rhythm_backend', 'coach':output, 'fallback_reason':None, 'coaching_route':'session_api'}
    except SessionReadError as error:
        code = f" ({error.backend_error_code})" if error.backend_error_code else ''
        reason = f"Game-session coaching failed{code}: {error} Offline coaching is shown instead."
        if error.http_status in (401,410):
            return {'provider':'offline','coach':offline_reply(payload),'fallback_reason':reason,'coaching_route':'session_api','session_access_revoked':True}
    except (ValueError, KeyError, TypeError):
        reason = 'Game-session coaching returned an invalid or ungrounded reply. Offline coaching is shown instead.'
    return {'provider':'offline', 'coach':offline_reply(payload), 'fallback_reason':reason, 'coaching_route':'session_api'}


@router.post("/api/jobs/{job_id}/session-summary")
def session_summary(job_id: str, body: ReviewBody):
    try:
        return summarize(load_job(job_id), body.review).model_dump()
    except ValueError as error:
        raise HTTPException(400, str(error))


@router.post("/api/jobs/{job_id}/coaching")
async def job_coaching(job_id: str, body: ReviewBody):
    try:
        result = load_job(job_id)
        payload = song_request(result, body.review)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return await get_job_coaching(result, payload)


@router.post("/api/session-report")
def session_report(body: SongsBody):
    try:
        return build_report(body.songs)
    except ValueError as error:
        raise HTTPException(400, str(error))


@router.post("/api/report-coaching")
async def report_coaching(body: SongsBody):
    if not body.songs:
        raise HTTPException(400, "This report contains no plays")
    return await get_coaching(context_request("session_debrief", body.songs))


@router.post("/api/coach-chat")
async def coach_chat(body: ChatBody):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Enter a message")
    payload = context_request("chat", body.songs, question, [turn.model_dump() for turn in body.history])
    if body.report_notes and not payload["session"]: payload["session"]={}
    if payload["session"] is not None:
        payload["session"].update(report_count=body.report_count, current_count=body.current_count,
            saved_report_notes=[text[:12000] for text in body.report_notes],
            report_notes_basis="Previously generated AI text, not independent measurements. Do not turn its claims into new measured facts.")
    return await get_coaching(payload)


class SessionDebriefBody(BaseModel):
    handle: str


@router.post('/api/game-session-debrief')
async def server_session_debrief(body: SessionDebriefBody):
    from session_qr import SessionReadError,coach_session
    try:
        response=await asyncio.to_thread(coach_session,body.handle)
        output=validate_coach(response['coaching'],{'mode':'session_debrief','tier':('mixed','A'),'runs':[]})
        if not 60<=len(output['speech'].split())<=180 or len(re.split(r'\n\s*\n',output['speech'].strip()))!=2:
            raise ValueError('Invalid session speech format')
        from datetime import datetime
        import hashlib
        facts=response.get('session_facts') or {}
        records=facts.get('runs',[])
        report=None
        if records:
            songs=[]
            for r in records:
                songs.append(SongSummary(id='run-'+response['session_id']+'-'+r['run_id'],source='custom_game_csv',
                    scoring_system=f"custom_csv_game_{r['game_id']}",title=f"Song {r['song_id']}",
                    played_at=int(datetime.fromisoformat(r['completed_at'].replace('Z','+00:00')).timestamp()*1000),
                    remote_session_id=response['session_id'],server_sequence=r['sequence'],game_id=r['game_id'],song_id=r['song_id'],chart_id=r['chart_id'],
                    difficulty=int(r['difficulty']),game_time_ms=int(r['game_time_ms']),total_notes=int(r['total_notes']),
                    bpm=int(r['bpm']),score=int(r['score']),accuracy_pct=r['accuracy_pct'],accuracy_is_approximate=r['accuracy_is_approximate'],
                    mean_offset_ms=r['offset_mean_ms'],offset_spread_ms=r['offset_spread_ms'],peak_nps=r['peak_nps'],
                    usable_for_coaching=r['usable_for_coaching'],reviewed=True,
                    data_notes=['Backend session snapshot. Accuracy is approximate and captured note rows may be partial.']))
            report=build_report(songs)
            report['id']='server-report-'+hashlib.sha256((response['session_id']+'|'+','.join(r['run_id'] for r in records)).encode()).hexdigest()[:24]
            report['ai_debrief']=output['speech'];report['spoken_summary']=output['speech']
            report['text']=output['speech']+'\n\n'+report['text']
        if report is None:
            # Current upstream returns coaching only, not our earlier facts extension.
            # Persist it without inventing song counts, metrics or local summaries.
            import time,uuid
            report={'id':'server-debrief-'+uuid.uuid4().hex,'created_at':int(time.time()*1000),
                    'scope':'server_session','songs':[],'groups':[],'highlights':[],
                    'ai_debrief':output['speech'],'text':output['speech'],'spoken_summary':output['speech']}
        report['coaching']={'provider':'rhythm_backend','coach':output,'coaching_route':'session_api','fallback_reason':None}
        return {'provider':'rhythm_backend','coach':output,'coaching_route':'session_api','fallback_reason':None,
                'session_facts':facts,'report':report}
    except SessionReadError as error:
        if error.http_status==404:
            raise HTTPException(404,'The Azure session-debrief endpoint is not deployed yet. Use the local saved-results report, or have the backend owner deploy the supplied session-debrief patch.')
        raise HTTPException(error.http_status or 503,str(error))
    except (ValueError,KeyError,TypeError):
        raise HTTPException(502,'Server session debrief failed response validation; saved results remain available.')
