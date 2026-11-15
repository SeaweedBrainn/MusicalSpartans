"""Read RhythmBackend session API v1; never open a QR landing page or persist its key."""
import json
import math
import hashlib
import os
import re
import threading
import time
import uuid
from urllib.parse import urlsplit, parse_qsl

import httpx
import game_runs

DEFAULT_ORIGIN = 'https://rhythm-backend-emmanuel-hvfkdjhxfjc4d9a5.westus-01.azurewebsites.net'
ID = re.compile(r'^[a-f0-9]{32}$')
KEY = re.compile(r'^[A-Za-z0-9_-]{32}$')
_LINKS = {}
_LOCK = threading.Lock()
_COOLDOWNS = {}


def origins():
    return {v.strip().rstrip('/') for v in os.getenv('RHYTHM_SESSION_ORIGINS', DEFAULT_ORIGIN).split(',') if v.strip()}


def parse_link(payload):
    try:
        u = urlsplit(payload)
        # Exact origins, no credentials, fragments, alternate ports, encodings or duplicate keys.
        if u.scheme not in ('https', 'http') or u.username or u.password or u.fragment:
            return None
        origin = f'{u.scheme}://{u.netloc}'
        if origin not in origins():
            return None
        if u.scheme == 'http' and u.hostname not in ('localhost', '127.0.0.1', '::1'):
            return None
        match = re.fullmatch(r'/sessions/([a-f0-9]{32})/', u.path)
        query = parse_qsl(u.query, keep_blank_values=True)
        if not match or len(query) != 1 or query[0][0] != 'key' or not KEY.fullmatch(query[0][1]):
            return None
        return origin, match[1], query[0][1]
    except ValueError:
        return None


class SessionReadError(ValueError):
    def __init__(self, message, http_status=None, backend_error_code=None, stage=None, retry_after_seconds=None):
        super().__init__(message)
        self.http_status = http_status
        self.backend_error_code = backend_error_code
        self.stage = stage
        self.retry_after_seconds = retry_after_seconds

    def diagnostic(self):
        return {"http_status": self.http_status, "backend_error_code": self.backend_error_code,
                "stage": self.stage, "retry_after_seconds": self.retry_after_seconds}



def _read_once(client, path, key, limit, stage="csv_download", method="GET", timeout=50):
    # No redirect following or exception strings containing request URLs/headers.
    try:
        with client.stream(method, path, headers={'Authorization': f'Bearer {key}'}, timeout=timeout) as response:
            if response.status_code != 200:
                code = response.status_code
                message = {401: 'QR decoded, but the session API returned HTTP 401: this session ID/read-key pair was rejected. Start a fresh game session and verify registration succeeded on the same API origin.',
                           403: 'Session API returned HTTP 403: wrong key scope. The game QR must contain the session read key, never the upload key.',
                           410: 'Session expired or was revoked. Scan a new game QR.',
                           429: 'Session API rate limited this request. Wait before checking again.',
                           503: 'Session storage is unavailable. Check the RhythmBackend deployment.'}.get(code,
                           f'Session API returned HTTP {code}.')
                if stage == 'coach' and code == 404:
                    message = 'The deployed game backend does not expose the new CSV coaching endpoint yet.'
                elif stage in ('coach', 'session_coach') and code == 503:
                    message = 'Game coaching is unavailable or Gemini is not configured on that backend.'
                error_code = None
                try:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 4096: break
                    if len(body) <= 4096:
                        value = json.loads(body).get("error", {}).get("code")
                        if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,64}", value):
                            error_code = value
                except (ValueError, AttributeError, TypeError):
                    pass
                retry = None
                if code == 429:
                    try: retry = max(1,min(3600,int(response.headers.get('Retry-After','1'))))
                    except ValueError:
                        try:
                            from email.utils import parsedate_to_datetime
                            retry = max(1,math.ceil(parsedate_to_datetime(response.headers['Retry-After']).timestamp()-time.time()))
                        except (KeyError,TypeError,ValueError,OverflowError): retry = 60
                raise SessionReadError(message, code, error_code, stage, retry)
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > limit:
                    raise SessionReadError('Session response exceeds the supported size.',413,stage=stage)
            return bytes(content)
    except httpx.HTTPError:
        raise SessionReadError('Could not reach the session API. Check connectivity and its HTTPS address.', stage=stage) from None


def read(client, path, key, limit, stage="csv_download", method="GET"):
    # Bounded unchanged retries per the new handoff, sharing one time budget.
    deadline=time.monotonic()+50
    attempts=3 if method=='GET' else 2
    for attempt in range(attempts):
        try:
            return _read_once(client,path,key,limit,stage,method, max(.1,deadline-time.monotonic()))
        except SessionReadError as error:
            transient = error.http_status is None or error.http_status in (500,502,503,504)
            if not transient or attempt == attempts-1 or deadline-time.monotonic()<5: raise
            time.sleep(.25*(attempt+1))


def cooldown(handle):
    remaining = int(math.ceil(_COOLDOWNS.get(handle,0)-time.monotonic()))
    if remaining > 0:
        raise SessionReadError(f'Wait {remaining} seconds before retrying this session.',429,'rate_limited','retry_wait',remaining)


def remember_error(handle,error):
    if error.http_status in (401,410):
        with _LOCK:
            _LINKS.pop(handle,None)
            _COOLDOWNS.pop(handle,None)
    elif error.http_status == 429:
        _COOLDOWNS[handle] = time.monotonic() + (error.retry_after_seconds or 60)


def listing(client, session_id, key, after=0):
    entries = []
    for _ in range(3):
        raw = read(client, f'/v1/sessions/{session_id}/runs?after_sequence={after}&limit=100', key, 512*1024, stage="list_runs")
        try:
            page = json.loads(raw)
            if page['session_id'] != session_id or type(page['has_more']) is not bool:
                raise ValueError()
            runs = page['runs']
            if not isinstance(runs, list) or len(runs) > 100:
                raise ValueError()
            for entry in runs:
                if not ID.fullmatch(entry['run_id']) or entry['status'] != 'completed' or type(entry['sequence']) is not int or entry['sequence'] <= after:
                    raise ValueError()
                after = entry['sequence']
                entries.append(entry)
            if len(entries) > 200 or page['next_after_sequence'] != after:
                raise ValueError()
            if not page['has_more']:
                return entries
            if not runs:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise SessionReadError('Session API returned an invalid run listing.') from None
    raise SessionReadError('Session listing exceeded the supported run count.')


def retain(link):
    with _LOCK:
        now = time.monotonic()
        for handle in list(_LINKS):
            if _LINKS[handle][1] < now:
                del _LINKS[handle]
        # Process memory only, bounded lifetime. Restart requires rescanning.
        for handle, (saved, _) in _LINKS.items():
            if saved == link:
                return handle
        if len(_LINKS) >= 100:
            raise SessionReadError('Too many active sessions. Restart the extraction server.')
        handle = uuid.uuid4().hex
        _LINKS[handle] = (link, now + 24*3600)
        return handle


def validated_game(entry, summary_bytes, series_bytes, session_id):
    summary = summary_bytes.decode('utf-8-sig')
    series = series_bytes.decode('utf-8-sig')
    run = game_runs.import_run(summary, series)
    for name in ('game_id', 'song_id', 'chart_id', 'sample_interval_sec', 'successful_hit_count'):
        if type(entry[name]) is not int or entry[name] < 0:
            raise SessionReadError('Invalid run envelope metadata.')
    for name in ('autoplay', 'summary_exceeds_format_range'):
        if type(entry[name]) is not bool:
            raise SessionReadError('Invalid run flags.')
    interval = entry['sample_interval_sec']
    v2 = run.get('format_version') == 2
    if interval not in (1, 2) or (not v2 and interval != run['sample_interval_sec']) or entry['chart_id'] != run['chart_id']:
        raise SessionReadError('Run envelope and CSV timeline do not match.')
    if entry['latency_basis'] != 'successful_hits_only_v1':
        raise SessionReadError('Unsupported latency basis; no timing assumptions were made.')
    hits = entry['successful_hit_count']
    clamped = entry['summary_exceeds_format_range']
    if v2:
        count = sum(n['judgement'] in ('P','G') and n['latency_ms'] is not None for n in run['notes'])
        if count != hits or hits == 0 and run['summary']['average_latency_ms'] != 0:
            raise SessionReadError('Successful-hit metadata or no-hit sentinel differs from V2 notes.')
    else:
        if any(s['time_sec'] != i*interval for i, s in enumerate(run['samples'])):
            raise SessionReadError('CSV window sequence is invalid.')
        count = sum(s['nps'] for s in run['samples'])
        if hits > count or (not clamped and count != run['summary']['total_notes']):
            raise SessionReadError('Run envelope and summary measurements do not match.')
        if hits == 0 and any(s['avg_latency_ms'] is not None or s['latency_spread_ms'] is not None for s in run['samples']):
            raise SessionReadError('No-hit run contains timing measurements.')
        if hits < 2 and any(s['latency_spread_ms'] is not None for s in run['samples']):
            raise SessionReadError('Spread requires at least two successful hits.')
    if not clamped and any(entry[k] != run['summary'][k] for k in ('game_id','song_id')):
        raise SessionReadError('Run envelope and summary identities do not match.')
    run['envelope'] = {k: entry[k] for k in ('game_id', 'song_id', 'chart_id', 'autoplay', 'successful_hit_count',
                                            'latency_basis', 'summary_exceeds_format_range', 'sample_interval_sec')}
    run['warnings'].append('Score is separate from accuracy. V2 accuracy is only an approximate sum of rounded deltas from a zero baseline; partial captures may omit changes. No grade is inferred.')
    run['warnings'].append('V2 notes remain note-level; NPS is density and is never summed as a note count.' if v2 else
                           'Timing uses successful hits only. Window note counts cannot weight successful-hit latency means.')
    if entry['autoplay']:
        run['warnings'].append('Autoplay run: retained for display, excluded from player coaching.')
    if clamped:
        run['warnings'].append('Summary exceeds format range: exact coaching is disabled.')
    analysis = game_runs.analyze(run)
    return {'session_id':session_id,'sequence':entry['sequence'],'run_id':session_id+'-'+entry['run_id'],'created_at':entry['completed_at'],'run':run,'analysis':analysis}


def load(link, handle, chosen=None):
    origin, session_id, key = link
    try:
        cooldown(handle)
        from session_cache import committed_entries, read_pair, save_pair
        cached=committed_entries(origin,session_id)
        after=cached[-1]['sequence'] if cached else 0
        with httpx.Client(base_url=origin, timeout=12, follow_redirects=False, trust_env=False) as client:
            # Listing always authenticates, even when every CSV is already cached.
            incoming=listing(client,session_id,key,after)
            for entry in incoming:
                base=f"/v1/sessions/{session_id}/runs/{entry['run_id']}"
                summary_bytes=read(client,base+'/summary.csv',key,256*1024)
                series_bytes=read(client,base+'/series.csv',key,256*1024)
                validated_game(entry,summary_bytes,series_bytes,session_id)
                # metadata.json is the commit marker and therefore the cursor.
                save_pair(origin,session_id,entry['run_id'],summary_bytes,series_bytes,entry)
            entries=cached+incoming
            if len(entries)>200: raise SessionReadError('Session exceeds 200 completed attempts.')
            info={'handle':handle,'runs':[{k:e[k] for k in ('run_id','sequence','game_id','song_id','autoplay')} for e in entries],
                  'run_count':len(entries),'downloaded_count':len(entries),'next_after_sequence':entries[-1]['sequence'] if entries else 0}
            if not entries:
                return {'status':'session_waiting','source':'game_session','remote_session':info,
                        'warnings':['Game session connected. Finish a song, then tap Check for new runs.'],'crops':{}}
            entry=next((e for e in entries if e['run_id']==chosen),None) if chosen else entries[-1]
            if entry is None: raise SessionReadError('The selected run is not in this session.')
            summary_bytes,series_bytes=read_pair(origin,session_id,entry['run_id'])
            game=validated_game(entry,summary_bytes,series_bytes,session_id)
            info['selected_run_id']=entry['run_id']
            return {'status':'run_analyzed','source':'game_csv','game_run':game,'remote_session':info,
                    'warnings':game['run']['warnings'],'crops':{}}
    except SessionReadError as error:
        revoked = error.http_status in (401,410)
        remember_error(handle,error)
        return {'status': 'session_error', 'source': 'game_session',
                'session_access_revoked': revoked,
                'remote_session': None if revoked else {'handle': handle, 'runs': [], 'run_count': 0},
                'session_diagnostic': {'api_origin': origin, 'session_fingerprint': hashlib.sha256(session_id.encode()).hexdigest()[:12], **error.diagnostic()},
                'warnings': [str(error)], 'crops': {}}
    except (ValueError, KeyError, TypeError, UnicodeError, OSError):
        return {'status': 'session_error', 'source': 'game_session',
                'remote_session': {'handle': handle, 'runs': [], 'run_count': 0},
                'warnings': ['Session CSV or metadata is invalid. No coaching was generated.'], 'crops': {}}


def resolve(payload):
    link = parse_link(payload)
    if link is None:
        return None
    try:
        return load(link, retain(link))
    except SessionReadError as error:
        return {'status': 'session_error', 'source': 'game_session', 'warnings': [str(error)], 'crops': {}}


def refresh(handle, run_id=None):
    with _LOCK:
        saved = _LINKS.get(handle)
    if saved is None or saved[1] < time.monotonic():
        return {'status': 'session_error', 'source': 'game_session',
                'warnings': ['Session connection was lost or expired. Scan the game QR again.'], 'crops': {}}
    return load(saved[0], handle, run_id)


def coach_run(handle, run_id):
    """Call the updated authenticated CSV-coaching endpoint, without persisting the key."""
    if not isinstance(run_id, str) or not ID.fullmatch(run_id):
        raise SessionReadError('Select a valid completed run before requesting coaching.', stage='coach')
    with _LOCK:
        saved = _LINKS.get(handle)
    if saved is None or saved[1] < time.monotonic():
        raise SessionReadError('Session connection was lost or expired. Scan the game QR again.', stage='coach')
    origin, session_id, key = saved[0]
    try:
        cooldown(handle)
        with httpx.Client(base_url=origin, timeout=55, trust_env=False, follow_redirects=False) as client:
            data = read(client, f'/v1/sessions/{session_id}/runs/{run_id}/coach', key, 128*1024, stage='coach', method='POST')
    except SessionReadError as error:
        remember_error(handle,error)
        raise
    try:
        body = json.loads(data)
        if body['session_id'] != session_id or body['run_id'] != run_id or not isinstance(body['coaching'], dict):
            raise ValueError()
        return body['coaching']
    except (ValueError, KeyError, TypeError):
        raise SessionReadError('Session API returned an invalid coaching response.', stage='coach') from None


def coach_session(handle):
    with _LOCK: saved=_LINKS.get(handle)
    if saved is None or saved[1]<time.monotonic(): raise SessionReadError('Scan a current game QR before requesting a server session debrief.',stage='session_coach')
    origin,session_id,key=saved[0]
    try:
        cooldown(handle)
        with httpx.Client(base_url=origin,timeout=55,trust_env=False,follow_redirects=False) as client:
            raw=read(client,f'/v1/sessions/{session_id}/coach',key,512*1024,stage='session_coach',method='POST')
        body=json.loads(raw)
        if body['session_id']!=session_id or not isinstance(body['coaching'],dict): raise ValueError()
        return body
    except SessionReadError as error:
        remember_error(handle,error)
        raise
    except (KeyError,ValueError,TypeError):
        raise SessionReadError('Server session debrief had an invalid response shape.',stage='session_coach') from None
