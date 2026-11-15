import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import game_runs
from coach_domain import OcrReview,song_request,summarize
from coach_api import validate_session_coach
import test_session_qr as fixtures
ORIGIN,SID,RID,LINK,KEY=fixtures.ORIGIN,fixtures.SID,fixtures.RID,fixtures.LINK,fixtures.KEY
from test_native_coaching import reply

SUMMARY='01,010,2,5000,120,4,900000,10'
SERIES='game_id,1\nsong_id,10\nchart_id,2\nbpm,120\nformat_version,2\nnote_index,time_ms,lane,judgement,accuracy_delta,latency_ms,nps,bpm,combo,std_ms\n0,500,0,P,100,0,20,120,1,\n2,1000,1,G,-10,20,20,120,2,10\n3,2000,1,M,-20,999,1,120,0,10\n8,4000,2,P,5,,20,120,1,10\n'

class CsvV2Tests(unittest.TestCase):
 def test_notes_gaps_blanks_misses_density_and_unknown_accuracy(self):
  run=game_runs.import_run(SUMMARY,SERIES);analysis=game_runs.analyze(run)
  self.assertEqual(run['format_version'],2);self.assertEqual(run['samples'],[])
  self.assertEqual([n['note_index'] for n in run['notes']],[0,2,3,8])
  self.assertEqual(run['notes'][0]['latency_ms'],0);self.assertIsNone(run['notes'][3]['latency_ms'])
  self.assertEqual(run['notes'][2]['latency_ms'],999)
  self.assertEqual(sum(n['nps'] for n in run['notes']),61)
  self.assertEqual(analysis['mean_offset_ms'],10);self.assertEqual(analysis['spread_ms'],10)
  self.assertEqual(analysis['accuracy'],.75);self.assertTrue(analysis['accuracy_is_approximate']);self.assertIsNone(analysis['grade'])
  self.assertEqual(analysis['judgments'],{'P':2,'G':1,'M':1})
  self.assertFalse(run['warnings'])
 def test_section_hit_rate_is_separate_from_weighted_accuracy(self):
  run=game_runs.import_run(SUMMARY,SERIES);section=game_runs.analyze(run)['sections'][0]
  self.assertIsNone(section['accuracy'])
  self.assertEqual(section['hit_rate'],.75)
  self.assertEqual((section['perfect'],section['good'],section['misses'],section['judged_notes']),(2,1,1,4))
  self.assertEqual(section['measured_offsets'],2)
  self.assertEqual(section['mean_offset_ms'],10)
  self.assertEqual(section['spread_ms'],10)
 def test_approximate_accuracy_blank_zero_and_out_of_range(self):
  run=game_runs.import_run(SUMMARY,SERIES.replace('P,100,0','P,,0'))
  self.assertIsNone(game_runs.analyze(run)['accuracy'])
  run=game_runs.import_run(SUMMARY,SERIES.replace('P,100,0','P,200,0'))
  self.assertIsNone(game_runs.analyze(run)['accuracy'])
  run=game_runs.import_run(SUMMARY,SERIES.replace('P,100,0','P,25,0'))
  self.assertEqual(game_runs.analyze(run)['accuracy'],0)
  self.assertIn('approximately',game_runs.analyze(run)['spoken_summary'].lower())
 def test_invalid_v2_never_falls_back(self):
  for text in [SERIES.replace('format_version,2','format_version,3'),SERIES.replace('std_ms','bad_header',1),SERIES.replace('2,1000','0,1000'),SERIES.replace('P,100,0','X,100,0'),SERIES.replace('120,2,10','120,1,10'),SERIES.replace('120,1,\n','120,1,0\n'),SERIES.replace('120,0,10','120,0,999'),SERIES.replace('P,100,0','P,nan,0')]:
   with self.assertRaises(ValueError):game_runs.import_run(SUMMARY,text)
 def test_no_hits_preserves_unknown_timing(self):
  series=SERIES.split('note_index,')[0]+'note_index,time_ms,lane,judgement,accuracy_delta,latency_ms,nps,bpm,combo,std_ms\n1,1000,0,M,-100,,5,120,0,\n'
  run=game_runs.import_run('01,010,2,5000,120,1,0,0',series)
  self.assertIsNone(game_runs.analyze(run)['mean_offset_ms'])
 def test_notes_can_be_simultaneous_or_scheduled_out_of_index_order(self):
  run=game_runs.import_run(SUMMARY,SERIES.replace('2,1000','2,500').replace('3,2000','3,100'))
  self.assertEqual(len(run['notes']),4)

class RemoteV2Tests(unittest.TestCase):
 setUp=fixtures.SessionQrTests.setUp
 tearDown=fixtures.SessionQrTests.tearDown
 def v2(self):
  self.summary=SUMMARY;self.series=SERIES
  self.entries[0].update(game_id=1,song_id=10,chart_id=2,successful_hit_count=2)
 def test_v2_session_saves_exact_bytes_and_summary_without_inferred_accuracy(self):
  import session_qr as sq
  self.v2();self.series=SERIES.replace('\n','\r\n')
  result=sq.resolve(LINK);self.assertEqual(result['status'],'run_analyzed')
  summary=summarize(result);self.assertEqual(summary.accuracy_pct,75);self.assertTrue(summary.accuracy_is_approximate);self.assertIsNone(summary.native_grade)
  self.assertEqual(summary.mean_offset_ms,10);self.assertTrue(summary.usable_for_coaching)
  from session_cache import ROOT
  self.assertEqual(next(ROOT.rglob('series.csv')).read_bytes(),self.series.encode())
  self.assertEqual(next(ROOT.rglob('summary.csv')).read_bytes(),SUMMARY.encode())
  self.assertNotIn(KEY,json.dumps(result))
 def test_v2_successful_hit_envelope_is_checked(self):
  import session_qr as sq
  self.v2();self.entries[0]['successful_hit_count']=3
  self.assertEqual(sq.resolve(LINK)['status'],'session_error')
 def test_v2_native_focus_is_grounded_on_note_seconds(self):
  import session_qr as sq
  self.v2();result=sq.resolve(LINK);p=song_request(result,OcrReview());c=reply()
  c['focus_section']={'start_s':4,'end_s':5,'reason':'Reported note interval'}
  validate_session_coach(c,p,result)
  c['focus_section']={'start_s':0,'end_s':3,'reason':'Measured notes inside this supported time range'}
  validate_session_coach(c,p,result)
  c['focus_section']={'start_s':40,'end_s':50,'reason':'Invented'}
  with self.assertRaises(ValueError):validate_session_coach(c,p,result)
 def test_401_and_410_withdraw_read_capability(self):
  import session_qr as sq
  for status in [401,410]:
   self.status=status;result=sq.resolve(LINK)
   self.assertTrue(result['session_access_revoked']);self.assertIsNone(result['remote_session']);self.assertFalse(sq._LINKS)

class CacheAndRetryTests(unittest.TestCase):
 def test_exact_pair_is_immutable_and_metadata_commits_last(self):
  import session_cache
  with tempfile.TemporaryDirectory() as tmp,patch.object(session_cache,'ROOT',Path(tmp)):
   session_cache.save_pair(ORIGIN,SID,RID,b'a\r\n',b'b,\r\n',{'sequence':1})
   self.assertEqual(next(Path(tmp).rglob('series.csv')).read_bytes(),b'b,\r\n')
   with self.assertRaises(ValueError):session_cache.save_pair(ORIGIN,SID,RID,b'changed',b'b,\r\n',{'sequence':1})
 def test_retry_after_cooldown_prevents_repeat_request(self):
  import httpx,time,session_qr as sq
  calls=[]
  def fail(request):
   calls.append(request)
   return httpx.Response(429,headers={'Retry-After':'12'},json={'error':{'code':'rate_limited'}})
  with httpx.Client(base_url=ORIGIN,transport=httpx.MockTransport(fail)) as client:
   with self.assertRaises(sq.SessionReadError) as caught:sq.read(client,'/v1/sessions/x/runs',KEY,4096)
  self.assertEqual(caught.exception.retry_after_seconds,12)
  sq.remember_error('retry-test',caught.exception)
  with self.assertRaises(sq.SessionReadError):sq.cooldown('retry-test')
  sq._COOLDOWNS.pop('retry-test',None)
  self.assertEqual(len(calls),1)
