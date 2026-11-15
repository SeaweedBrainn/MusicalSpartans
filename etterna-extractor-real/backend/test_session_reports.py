import unittest
from coach_domain import SongSummary,build_report

class SessionReportsTests(unittest.TestCase):
 def song(self,id,seq,accuracy,bias,bpm=120,density=4):
  return SongSummary(id=id,source='custom_game_csv',scoring_system='game1',title=id,played_at=1000-seq,
   remote_session_id='session',server_sequence=seq,accuracy_pct=accuracy,accuracy_is_approximate=True,
   mean_offset_ms=bias,offset_spread_ms=20 if seq==1 else 16,bpm=bpm,peak_nps=density,reviewed=True)
 def test_two_paragraphs_trends_bias_spread_density_and_next_steps(self):
  a=self.song('Song A',1,90,-40);b=self.song('Song B',2,95.2,-25,150,8)
  report=build_report([b,a]);g=report['groups'][0]
  self.assertAlmostEqual(g['first_to_last_change_pct'],5.2)
  self.assertEqual(g['timing_distance_change_ms'],-15)
  self.assertEqual(g['best_song'],'Song B');self.assertEqual(g['weakest_song'],'Song A')
  self.assertEqual(g['repeated_early'],2)
  self.assertEqual(len(report['spoken_summary'].split('\n\n')),2)
  self.assertIn('approximate',report['spoken_summary']);self.assertIn('120 to 150',report['spoken_summary'])
  self.assertIn('4 to 8',report['spoken_summary']);self.assertTrue(1<=len(report['next_steps'])<=2)
 def test_missing_data_never_becomes_zero_or_best(self):
  report=build_report([SongSummary(id='unknown',title='Unknown',source='screen_ocr',scoring_system='other',played_at=0)])
  self.assertIsNone(report['groups'][0]['average_accuracy_pct']);self.assertIsNone(report['groups'][0]['best_song'])
  self.assertNotIn('0.0 percent',report['spoken_summary'])
 def test_autoplay_unusable_and_different_scoring_groups_are_separate(self):
  a=self.song('A',1,90,20);b=self.song('B',2,100,0);b.usable_for_coaching=False
  c=self.song('C',3,50,10);c.scoring_system='different'
  report=build_report([a,b,c]);self.assertEqual(len(report['groups']),2)
  self.assertEqual(next(g for g in report['groups'] if g['scoring_system']=='game1')['best_song'],'A')
if __name__=='__main__':unittest.main()
