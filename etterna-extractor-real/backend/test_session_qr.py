import json
import os
import tempfile
import unittest
from unittest.mock import patch
import cv2
import httpx
import numpy as np
import session_qr as sq
from coach_domain import OcrReview, song_request, summarize
from extract import extract, qr_result

ORIGIN='https://sessions.example'
SID='a'*32
RID='b'*32
KEY='c'*32
LINK=f'{ORIGIN}/sessions/{SID}/?key={KEY}'
SUMMARY='02,103,3,2000,120,1,1000000,-12'
SERIES='game_id,2\nsong_id,103\nchart_id,1\nbpm,120\nsample_interval_sec,1\ngame_time,percent_accuracy,avg_latency,bpm,nps,latency_spread\n0,,,120,0,\n1,100,-12,120,1,\n'
def entry(rid=RID,sequence=1):
 return dict(run_id=rid,sequence=sequence,status='completed',completed_at='2026-11-15T00:00:00Z',game_id=2,song_id=103,chart_id=1,sample_interval_sec=1,autoplay=False,successful_hit_count=1,summary_exceeds_format_range=False,latency_basis='successful_hits_only_v1')
class SessionQrTests(unittest.TestCase):
 def setUp(self):
  sq._LINKS.clear();self.cache=tempfile.TemporaryDirectory();self.cache_patch=patch('session_cache.ROOT',__import__('pathlib').Path(self.cache.name));self.cache_patch.start();self.requests=[];self.entries=[entry()];self.status=200;self.series=SERIES;self.summary=SUMMARY
  self.env=patch.dict(os.environ,{'RHYTHM_SESSION_ORIGINS':ORIGIN});self.env.start()
  real=httpx.Client
  def serve(request):
   self.requests.append(request)
   if request.url.path=='/health':return httpx.Response(200,json={'status':'ok'})
   self.assertEqual(request.headers['Authorization'],'Bearer '+KEY);self.assertNotIn('key=',str(request.url))
   if self.status!=200:return httpx.Response(self.status,headers={'Location':'https://evil.example/'},json={'error':{'code':'unauthorized','message':KEY}})
   if request.url.path.endswith('/runs'):
    after=int(request.url.params.get('after_sequence',0));entries=[e for e in self.entries if e['sequence']>after]
    return httpx.Response(200,json={'session_id':SID,'runs':entries,'has_more':False,'next_after_sequence':entries[-1]['sequence'] if entries else after})
   return httpx.Response(200,text=self.series if request.url.path.endswith('/series.csv') else self.summary)
  self.client=patch.object(sq.httpx,'Client',side_effect=lambda **kwargs:real(**kwargs,transport=httpx.MockTransport(serve)));self.client.start()
 def tearDown(self):
  self.client.stop();self.env.stop();self.cache_patch.stop();self.cache.cleanup();sq._LINKS.clear()
 def test_link_origin_and_key_rejection(self):
  self.assertEqual(sq.parse_link(LINK),(ORIGIN,SID,KEY))
  for link in [LINK.replace(ORIGIN,ORIGIN+'.evil'),LINK+'&key='+KEY,LINK+'#x',LINK.replace('/sessions/','/other/'),LINK.replace('https://','http://'),LINK.replace('sessions.example','user@sessions.example')]:self.assertIsNone(sq.parse_link(link))
  result=qr_result(LINK.replace(ORIGIN,'https://evil.example'));self.assertEqual(result['status'],'session_error');self.assertNotIn(KEY,json.dumps(result));self.assertFalse(self.requests)
 def test_csv_and_grounded_coaching(self):
  result=sq.resolve(LINK);self.assertEqual(result['status'],'run_analyzed');self.assertNotIn(KEY,json.dumps(result))
  facts=song_request(result,OcrReview());self.assertEqual(facts['runs'][0]['facts']['overall']['offset_mean_ms'],-12);self.assertIsNone(facts['runs'][0]['facts']['sections'][0]['offset_mean_ms']);self.assertEqual(len(self.requests),3)
 def test_empty_session_later_runs_and_selection(self):
  self.entries=[];result=sq.resolve(LINK);self.assertEqual(result['status'],'session_waiting');handle=result['remote_session']['handle']
  self.entries=[entry(),entry('d'*32,2)];self.assertEqual(sq.refresh(handle)['remote_session']['selected_run_id'],'d'*32);self.assertEqual(sq.refresh(handle,RID)['remote_session']['selected_run_id'],RID);self.assertEqual(sq.refresh('missing')['status'],'session_error')
 def test_no_hit_sentinel_and_autoplay_and_clamp(self):
  self.entries[0]['successful_hit_count']=0;self.series=SERIES.replace('1,100,-12,120,1,','1,0,,120,1,');self.summary=SUMMARY.replace('1000000,-12','0,0')
  result=sq.resolve(LINK);self.assertIsNone(summarize(result).mean_offset_ms)
  self.entries[0]['run_id']='d'*32;self.entries[0]['sequence']=2;self.entries[0]['autoplay']=True;result=sq.resolve(LINK);self.assertFalse(summarize(result).usable_for_coaching);self.assertEqual(result['game_run']['analysis']['tips'],[])
  self.entries[0].update(run_id='e'*32,sequence=3,autoplay=False,summary_exceeds_format_range=True);self.assertFalse(summarize(sq.resolve(LINK)).usable_for_coaching)
 def test_http_redirect_errors_invalid_metadata_and_key_redaction(self):
  for status in [301,401,410,429,503]:
   self.status=status;result=sq.resolve(LINK);self.assertEqual(result['status'],'session_error');self.assertNotIn(KEY,json.dumps(result))
  self.status=200;self.series=SERIES.replace('chart_id,1','chart_id,2');self.assertEqual(sq.resolve(LINK)['status'],'session_error')
 def test_auth_diagnostics_are_credential_free(self):
  self.status=401
  result=sq.resolve(LINK)
  diagnostic=result['session_diagnostic']
  self.assertEqual(diagnostic['http_status'],401)
  self.assertEqual(diagnostic['stage'],'list_runs')
  self.assertEqual(diagnostic['backend_error_code'],'unauthorized')
  self.assertEqual(diagnostic['api_origin'],ORIGIN)
  self.assertNotIn(KEY,json.dumps(result))
  self.assertNotIn(SID,json.dumps(result))
  self.assertIn('registration',result['warnings'][0])
 def test_diagnostic_cli_never_echoes_credentials(self):
  import contextlib,io,diagnose_session
  self.status=401
  buffer=io.StringIO()
  with patch('sys.argv',['diagnose_session.py']),patch('getpass.getpass',return_value=LINK),contextlib.redirect_stdout(buffer):
   diagnose_session.main()
  output=buffer.getvalue()
  self.assertNotIn(KEY,output)
  self.assertNotIn(SID,output)
  diagnostic=json.loads(output)
  self.assertEqual(diagnostic['health_http'],200)
  self.assertEqual(diagnostic['http_status'],401)
  self.assertEqual(diagnostic['backend_error_code'],'unauthorized')
 def test_two_second_fractional_bpm_and_authoritative_mean(self):
  self.entries[0].update(sample_interval_sec=2,successful_hit_count=3);self.summary='02,103,3,6000,120,3,900000,-20'
  self.series=SERIES.replace('sample_interval_sec,1','sample_interval_sec,2').split('game_time,')[0]+'game_time,percent_accuracy,avg_latency,bpm,nps,latency_spread\n0,100,5,120.25,1,\n2,80,-30,120.25,1,\n4,90,-35,120.25,1,\n'
  result=sq.resolve(LINK);self.assertEqual(result['status'],'run_analyzed');self.assertEqual(result['game_run']['analysis']['mean_offset_ms'],-20);self.assertEqual(result['game_run']['run']['samples'][0]['bpm'],120.25);self.assertEqual(result['game_run']['analysis']['sections'][0]['end_ms'],6000)
 def test_qr_priority_and_no_qr_cv_fallback(self):
  qr=cv2.QRCodeEncoder_create().encode(LINK);qr=cv2.copyMakeBorder(qr,4,4,4,4,cv2.BORDER_CONSTANT,value=255);qr=cv2.resize(qr,None,fx=6,fy=6,interpolation=cv2.INTER_NEAREST);image=cv2.cvtColor(qr,cv2.COLOR_GRAY2BGR)
  with tempfile.TemporaryDirectory() as tmp,patch('registration.register_content',side_effect=AssertionError('CV should not run')):self.assertEqual(extract(image,tmp)['status'],'run_analyzed')
  with tempfile.TemporaryDirectory() as tmp,patch('registration.register_content',return_value=None) as cv,patch('extract.identify_layout',return_value=None),patch('extract.screen_candidates',return_value=[]):result=extract(np.zeros((240,320,3),np.uint8),tmp)
  cv.assert_called_once();self.assertNotEqual(result.get('source'),'game_csv')
 def test_untrusted_csv_paths_are_not_followed(self):
  self.entries[0]['files']={'series':'https://evil.example/secret','summary':'https://evil.example/secret'};self.assertEqual(sq.resolve(LINK)['status'],'run_analyzed');self.assertTrue(all(r.url.host=='sessions.example' for r in self.requests))
if __name__=='__main__':unittest.main()
