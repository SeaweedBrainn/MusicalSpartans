import asyncio,copy,json,unittest
from unittest.mock import patch
from pathlib import Path
import session_qr as sq
from coach_api import validate_session_coach, server_session_debrief,SessionDebriefBody
from coach_domain import OcrReview,song_request
from test_native_coaching import result,reply
from test_csv_v2 import SUMMARY,SERIES
import test_session_qr as fixtures
from test_session_qr import entry,LINK,SID,RID,KEY,ORIGIN
import game_runs

class Handoff2ContractTests(unittest.TestCase):
 def test_new_schema_focus_evidence_and_observations(self):
  r=result();r['game_run']['run']=game_runs.import_run(SUMMARY,SERIES)
  r['game_run']['run']['envelope']={'autoplay':False,'summary_exceeds_format_range':False,'successful_hit_count':2}
  r['game_run']['analysis']=game_runs.analyze(r['game_run']['run']);p=song_request(r,OcrReview())
  c=reply();c.update(coaching_focus='judgement_quality',evidence_basis='measured_run_data',
   what_went_well='Several judgments were perfect.',observations=[{'label':'Misses','value':'1','interpretation':'One captured note was missed.'}])
  c['speech']=' '.join(['Review the captured judgments and compare another attempt with the same chart.']*3)
  out=validate_session_coach(c,p,r);self.assertEqual(out['observations'],c['observations'])
  self.assertEqual(out['what_went_well'],c['what_went_well'])
  c['observations']*=4
  with self.assertRaises(ValueError):validate_session_coach(c,p,r)
 def test_current_mixed_session_response_saves_without_fact_extension(self):
  c=reply();c.update(mode='session_debrief',tier='mixed',evidence_basis='cross_run_pattern',coaching_focus='progression',what_went_well='Your session is recorded.',observations=[])
  c['speech']=' '.join(['Compare the available completed attempts cautiously because chart differences limit personal conclusions.']*3)+'\n\n'+' '.join(['Practice a comfortable chart and compare the next attempt using the same settings.']*3)
  with patch('session_qr.coach_session',return_value={'session_id':SID,'coaching':c}):
   out=asyncio.run(server_session_debrief(SessionDebriefBody(handle='example')))
  self.assertEqual(out['coach']['tier'],'mixed');self.assertEqual(out['report']['scope'],'server_session')
  self.assertEqual(out['report']['songs'],[]);self.assertEqual(out['report']['coaching']['coach']['observations'],[])
 def test_post_retry_is_bounded_and_never_retries_auth(self):
  with patch('session_qr._read_once',side_effect=[sq.SessionReadError('Unavailable',503),b'ok']) as call:
   self.assertEqual(sq.read(None,'/coach',KEY,100,method='POST'),b'ok');self.assertEqual(call.call_count,2)
  with patch('session_qr._read_once',side_effect=sq.SessionReadError('Rejected',401)) as call:
   with self.assertRaises(sq.SessionReadError):sq.read(None,'/coach',KEY,100,method='POST')
   self.assertEqual(call.call_count,1)

class IncrementalIngestionTests(unittest.TestCase):
 setUp=fixtures.SessionQrTests.setUp
 tearDown=fixtures.SessionQrTests.tearDown
 def test_all_pairs_cursor_resume_and_restart(self):
  self.entries=[entry(),entry('d'*32,2)]
  result=sq.resolve(LINK);self.assertEqual(result['remote_session']['downloaded_count'],2)
  self.assertEqual(len(self.requests),5)
  first=len(self.requests);sq.refresh(result['remote_session']['handle'],RID)
  self.assertEqual(len(self.requests),first+1);self.assertEqual(self.requests[-1].url.params['after_sequence'],'2')
  sq._LINKS.clear();result=sq.resolve(LINK)
  self.assertEqual(self.requests[-1].url.params['after_sequence'],'2');self.assertEqual(result['remote_session']['run_count'],2)
  from session_cache import committed_entries
  self.assertEqual(len(committed_entries(ORIGIN,SID)),2)
 def test_second_file_failure_does_not_advance_that_attempt(self):
  self.entries=[entry(),entry('d'*32,2)];real=sq.read
  def read(client,path,*args,**kwargs):
   if 'd'*32 in path and path.endswith('series.csv'):raise sq.SessionReadError('Unavailable',503)
   return real(client,path,*args,**kwargs)
  with patch('session_qr.read',side_effect=read):out=sq.resolve(LINK)
  self.assertEqual(out['status'],'session_error')
  from session_cache import committed_entries
  self.assertEqual([e['sequence'] for e in committed_entries(ORIGIN,SID)],[1])
  out=sq.resolve(LINK)
  self.assertEqual(out['status'],'run_analyzed')
  listed=[r for r in self.requests if r.url.path.endswith('/runs')]
  self.assertEqual(listed[-1].url.params['after_sequence'],'1')
if __name__=='__main__':unittest.main()
