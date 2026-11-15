"""Disposable loopback-only integration test against a built updated RhythmBackend DLL."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import httpx
import session_qr
from coach_domain import OcrReview, song_request, summarize

parser = argparse.ArgumentParser()
parser.add_argument('--dotnet', default='dotnet')
parser.add_argument('--dll', required=True)
parser.add_argument('--v2', action='store_true', help='Exercise the new per-note contract')
args = parser.parse_args()
dll = Path(args.dll).resolve()
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
origin = f'http://127.0.0.1:{port}'
with tempfile.TemporaryDirectory() as temp:
    env = dict(os.environ, ASPNETCORE_ENVIRONMENT='Development', SessionApi__StorageProvider='Local',
               SessionApi__LocalDirectory=temp, ASPNETCORE_URLS=origin, GEMINI_API_KEY='')
    with open(Path(temp)/'server.log', 'w') as log:
        proc = subprocess.Popen([args.dotnet, str(dll)], cwd=dll.parents[3], env=env, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=origin, trust_env=False, timeout=10) as client:
                for _ in range(100):
                    try:
                        if client.get('/health').status_code == 200: break
                    except httpx.HTTPError: pass
                    if proc.poll() is not None: raise RuntimeError('C# service exited before health check')
                    time.sleep(.1)
                else: raise RuntimeError('C# storage health did not become ready')
                sid, rid = secrets.token_hex(16), secrets.token_hex(16)
                read_key, upload_key = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
                reg = client.post('/v1/sessions', json={'contract_version':1, 'session_id':sid, 'session_key':read_key, 'upload_key':upload_key})
                assert reg.status_code == 201, reg.status_code
                os.environ['RHYTHM_SESSION_ORIGINS'] = origin
                link = f'{origin}/sessions/{sid}/?key={read_key}'
                empty = session_qr.resolve(link)
                assert empty['status'] == 'session_waiting', empty['status']
                body = {'contract_version':1,'finished_at_utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'game_id':2,'song_id':103,'chart_id':1,'sample_interval_sec':1,'autoplay':False,
                        'latency_basis':'successful_hits_only_v1','successful_hit_count':1,'summary_exceeds_format_range':False,
                        'series_csv':'game_id,2\nsong_id,103\nchart_id,1\nbpm,120\nsample_interval_sec,1\ngame_time,percent_accuracy,avg_latency,bpm,nps,latency_spread\n0,,,120,0,\n1,100,-12,120,1,\n',
                        'summary_csv':'02,103,3,2000,120,1,1000000,-12'}
                if args.v2:
                    body.update(successful_hit_count=2,
                        series_csv='game_id,2\nsong_id,103\nchart_id,1\nbpm,120\nformat_version,2\nnote_index,time_ms,lane,judgement,accuracy_delta,latency_ms,nps,bpm,combo,std_ms\n0,0,0,P,100,0,2,120,1,\n1,1000,1,M,-50,180,2,120,0,\n4,1500,2,G,16.7,20,2,120,1,10\n',
                        summary_csv='02,103,3,2000,120,3,123456,10')
                upload = client.put(f'/v1/sessions/{sid}/runs/{rid}', headers={'Authorization':'Bearer '+upload_key}, json=body)
                assert upload.status_code == 201, upload.status_code
                result = session_qr.refresh(empty['remote_session']['handle'])
                assert result['status'] == 'run_analyzed', result['status']
                assert summarize(result).mean_offset_ms == (10 if args.v2 else -12)
                if args.v2:
                    assert result['game_run']['run']['format_version'] == 2
                    assert len(result['game_run']['run']['notes']) == 3
                    assert summarize(result).accuracy_pct == 66.7
                    assert summarize(result).accuracy_is_approximate
                assert read_key not in json.dumps(result)
                coach = client.post('/api/mentra/coach',json=song_request(result,OcrReview()))
                assert coach.status_code == 503, coach.status_code  # explicit no-key test, no model charge
                session_coach_path=f'/v1/sessions/{sid}/coach'
                assert client.post(session_coach_path).status_code==401
                assert client.post(session_coach_path,headers={'Authorization':'Bearer '+upload_key}).status_code==403
                session_reply=client.post(session_coach_path,headers={'Authorization':'Bearer '+read_key})
                assert session_reply.status_code==503,session_reply.status_code
                native_path = f'/v1/sessions/{sid}/runs/{rid}/coach' 
                assert client.post(native_path).status_code == 401
                assert client.post(native_path, headers={'Authorization':'Bearer '+upload_key}).status_code == 403
                native = client.post(native_path, headers={'Authorization':'Bearer '+read_key})
                assert native.status_code == 503, native.status_code
                assert native.json()['error']['code'] == 'coach_not_configured'
                try:
                    session_qr.coach_run(empty['remote_session']['handle'], rid)
                    raise AssertionError('Missing-key service unexpectedly produced coaching')
                except session_qr.SessionReadError as error:
                    assert error.http_status == 503 and error.backend_error_code == 'coach_not_configured'
                autoplay_id = secrets.token_hex(16)
                body['autoplay'] = True
                assert client.put(f'/v1/sessions/{sid}/runs/{autoplay_id}', headers={'Authorization':'Bearer '+upload_key},json=body).status_code == 201
                assert client.post(f'/v1/sessions/{sid}/runs/{autoplay_id}/coach', headers={'Authorization':'Bearer '+read_key}).status_code == 422

                revoke = client.delete(f'/v1/sessions/{sid}', headers={'Authorization':'Bearer '+upload_key})
                assert revoke.status_code == 204
                assert session_qr.refresh(empty['remote_session']['handle'])['status'] == 'session_error'
            print('PASS: real updated .NET register/empty session/upload -> Python read-bearer CSV retrieval -> grounded facts -> native coach auth/scope/no-key/autoplay gates -> revocation; no credentials printed.')
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
