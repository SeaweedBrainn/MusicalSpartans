import asyncio
import copy
import json
import os
import time
import unittest
from unittest.mock import patch
import httpx

import game_runs
import session_qr as sq
from coach_api import get_job_coaching, validate_session_coach
from coach_domain import OcrReview, song_request
from test_session_qr import ORIGIN,SID,RID,KEY,SUMMARY,SERIES


def result():
    run=game_runs.import_run(SUMMARY,SERIES)
    run['envelope']={'successful_hit_count':1,'autoplay':False,'summary_exceeds_format_range':False}
    return {'status':'run_analyzed','source':'game_csv','game_run':{'run_id':SID+'-'+RID,'run':run,'analysis':game_runs.analyze(run)},
            'remote_session':{'handle':'handle','selected_run_id':RID}}


def reply():
    return {'mode':'song_debrief','tier':'A','coaching_focus':'timing_bias',
            'speech':'Your recorded timing was early. '+ ' '.join(['Practice a steady rhythm and listen carefully to the music.']*6),
            'phone_text':['Focus on steady timing'],'data_notes':[], 'confidence':'medium','evidence_basis':'game_heuristic',
            'drill':'Practice steady timing.','next_target':'Bring the reported mean closer to zero.','focus_section':None}


class NativeCoachingTests(unittest.TestCase):
    def setUp(self):
        sq._LINKS['handle']=((ORIGIN,SID,KEY),time.monotonic()+100)
        self.calls=[]
        real=httpx.Client
        self.body={'session_id':SID,'run_id':RID,'coaching':reply()}
        self.status=200
        def serve(req):
            self.calls.append(req)
            self.assertEqual(req.method,'POST')
            self.assertEqual(req.url.path,f'/v1/sessions/{SID}/runs/{RID}/coach')
            self.assertEqual(req.headers['Authorization'],'Bearer '+KEY)
            self.assertNotIn('key=',str(req.url))
            return httpx.Response(self.status,json=self.body)
        self.client=patch.object(sq.httpx,'Client',side_effect=lambda **kwargs:real(**kwargs,transport=httpx.MockTransport(serve)));self.client.start()
    def tearDown(self):
        self.client.stop();sq._LINKS.clear()
    def test_native_endpoint_and_coaching_response(self):
        r=result();out=asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))
        self.assertEqual(out['provider'],'rhythm_backend');self.assertEqual(out['coaching_route'],'session_api');self.assertEqual(len(self.calls),1)
        self.assertNotIn(KEY,json.dumps(out))
    def test_no_local_adapter_needed(self):
        with patch.dict(os.environ,{'RHYTHM_COACH_URL':''}),patch('coach_api.get_coaching',side_effect=AssertionError('Local adapter must not be used')):
            r=result();self.assertEqual(asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))['provider'],'rhythm_backend')
    def test_http_failure_and_error_body_are_safe(self):
        self.status=401;self.body={'error':{'code':'unauthorized','message':KEY}}
        r=result();out=asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))
        self.assertEqual(out['provider'],'offline');self.assertNotIn(KEY,json.dumps(out));self.assertIn('unauthorized',out['fallback_reason'])
    def test_missing_handle_and_wrong_response_identity(self):
        sq._LINKS.clear();r=result();self.assertEqual(asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))['provider'],'offline')
        self.assertFalse(self.calls)
        sq._LINKS['handle']=((ORIGIN,SID,KEY),time.monotonic()+100);self.body['run_id']='c'*32
        self.assertEqual(asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))['provider'],'offline')
    def test_csv_window_allowed_but_invented_window_rejected(self):
        r=result();p=song_request(r,OcrReview());c=reply();c['focus_section']={'start_s':1,'end_s':2,'reason':'Reported timing window'}
        validate_session_coach(c,p,r)
        self.body['coaching']['focus_section']={'start_s':50,'end_s':60,'reason':'Invented'}
        self.assertEqual(asyncio.run(get_job_coaching(r,p))['provider'],'offline')
    def test_bad_word_count_and_missing_spread_are_rejected(self):
        r=result();p=song_request(r,OcrReview())
        self.body['coaching']['speech']='Too short.';self.assertEqual(asyncio.run(get_job_coaching(r,p))['provider'],'offline')
        self.body['coaching']=reply();self.body['coaching']['coaching_focus']='timing_spread';self.assertEqual(asyncio.run(get_job_coaching(r,p))['provider'],'offline')
    def test_autoplay_and_clamped_never_call_native_ai(self):
        for flag in ('autoplay','summary_exceeds_format_range'):
            r=result();r['game_run']['run']['envelope'][flag]=True
            self.assertEqual(asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))['provider'],'offline')
        self.assertFalse(self.calls)
    def test_empty_csv_windows_keep_native_tier_a_without_timing(self):
        r=result()
        for sample in r['game_run']['run']['samples']:
            sample.update(nps=0,accuracy=None,avg_latency_ms=None,latency_spread_ms=None)
        r['game_run']['run']['summary'].update(total_notes=0,score=0,average_latency_ms=0)
        r['game_run']['run']['envelope']['successful_hit_count']=0
        r['game_run']['analysis']=game_runs.analyze(r['game_run']['run'])
        self.body['coaching']['coaching_focus']='none'
        out=asyncio.run(get_job_coaching(r,song_request(r,OcrReview())))
        self.assertEqual(out['provider'],'rhythm_backend')
    def test_local_source_still_uses_adapter(self):
        r=result();r.pop('remote_session');p=song_request(r,OcrReview())
        async def adapter(payload):return {'provider':'offline','coach':{},'fallback_reason':'test'}
        with patch('coach_api.get_coaching',side_effect=adapter) as call:asyncio.run(get_job_coaching(r,p))
        call.assert_called_once();self.assertFalse(self.calls)
if __name__=='__main__':unittest.main()
