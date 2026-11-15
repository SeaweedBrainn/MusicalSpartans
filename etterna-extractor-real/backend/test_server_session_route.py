import asyncio
import time
import unittest
from unittest.mock import patch
import httpx
import session_qr
from coach_api import server_session_debrief,SessionDebriefBody
from fastapi import HTTPException

class ServerSessionRouteTests(unittest.TestCase):
 def setUp(self):
  self.sid='a'*32;self.key='b'*32;self.calls=[];self.status=200
  session_qr._LINKS['session-handle']=(('https://session.example',self.sid,self.key),time.monotonic()+60)
  speech=' '.join(['Measured session trend and available timing stayed clearly recorded.']*6)+'\n\n'+' '.join(['Practice the same chart and compare the next recorded attempt.']*5)
  self.body={'session_id':self.sid,'coaching':{'mode':'session_debrief','tier':'A','speech':speech,'phone_text':[],
   'coaching_focus':'none','data_notes':[],'confidence':'low','evidence_basis':'game_heuristic','focus_section':None,'drill':None,'next_target':None},'session_facts':{}}
  real=httpx.Client
  def serve(req):
   self.calls.append(req);self.assertEqual(req.method,'POST');self.assertEqual(req.url.path,f'/v1/sessions/{self.sid}/coach')
   self.assertEqual(req.headers['Authorization'],'Bearer '+self.key);self.assertFalse(req.content)
   return httpx.Response(self.status,json=self.body)
  self.mock=patch.object(session_qr.httpx,'Client',side_effect=lambda **kw:real(**kw,transport=httpx.MockTransport(serve)));self.mock.start()
 def tearDown(self):self.mock.stop();session_qr._LINKS.clear()
 def test_session_endpoint_and_two_paragraph_reply(self):
  out=asyncio.run(server_session_debrief(SessionDebriefBody(handle='session-handle')))
  self.assertEqual(out['provider'],'rhythm_backend');self.assertEqual(len(out['coach']['speech'].split('\n\n')),2)
 def test_server_report_has_saved_song_summaries_and_ai_paragraphs(self):
  self.body['session_facts']['runs']=[{'run_id':'d'*32,'sequence':1,'completed_at':'2026-11-15T00:00:00Z',
   'game_id':1,'song_id':10,'chart_id':1,'difficulty':2,'game_time_ms':5000,'total_notes':4,'bpm':120,'score':900000,
   'accuracy_pct':75,'accuracy_is_approximate':True,'offset_mean_ms':10,'offset_spread_ms':10,'peak_nps':20,'usable_for_coaching':True}]
  out=asyncio.run(server_session_debrief(SessionDebriefBody(handle='session-handle')))
  self.assertEqual(out['report']['songs'][0]['accuracy_pct'],75)
  self.assertTrue(out['report']['songs'][0]['accuracy_is_approximate'])
  self.assertEqual(out['report']['spoken_summary'],out['coach']['speech'])
  self.assertTrue(out['report']['id'].startswith('server-report-'))
 def test_undeployed_endpoint_is_explicit(self):
  self.status=404
  with self.assertRaises(HTTPException) as caught:asyncio.run(server_session_debrief(SessionDebriefBody(handle='session-handle')))
  self.assertEqual(caught.exception.status_code,404);self.assertIn('not deployed',caught.exception.detail)
 def test_unknown_handle_and_bad_paragraphs_do_not_generate_fake_success(self):
  self.body['coaching']['speech']=self.body['coaching']['speech'].replace('\n\n',' ')
  with self.assertRaises(HTTPException):asyncio.run(server_session_debrief(SessionDebriefBody(handle='session-handle')))
if __name__=='__main__':unittest.main()
