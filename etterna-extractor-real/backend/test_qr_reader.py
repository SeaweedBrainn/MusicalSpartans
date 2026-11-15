"""QR regressions; real camera fixture remains outside the distributed bundle."""
import os
import tempfile
import unittest
from unittest.mock import patch, Mock
import cv2
import numpy as np
from extract import extract
from qr_reader import scan_qr

PAYLOAD='https://example.test/sessions/'+'a'*32+'/?key='+'b'*32

def generated(text=PAYLOAD):
 qr=cv2.QRCodeEncoder_create().encode(text)
 qr=cv2.copyMakeBorder(qr,4,4,4,4,cv2.BORDER_CONSTANT,value=255)
 return cv2.cvtColor(cv2.resize(qr,None,fx=7,fy=7,interpolation=cv2.INTER_NEAREST),cv2.COLOR_GRAY2BGR)

class QrReaderTests(unittest.TestCase):
 def test_generated_rotation_and_tilt(self):
  image=generated();n=image.shape[0]
  source=np.array([[0,0],[n-1,0],[n-1,n-1],[0,n-1]],np.float32)
  target=np.array([[180,100],[n+140,40],[n+220,n+100],[250,n+170]],np.float32)
  tilt=cv2.warpPerspective(image,cv2.getPerspectiveTransform(source,target),(n+400,n+250),borderValue=(100,100,100))
  for photo in (image,cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE),tilt):self.assertEqual(scan_qr(photo).payload,PAYLOAD)
 def test_game_link_priority_and_ambiguity(self):
  from qr_reader import choose
  self.assertEqual(choose(['https://example.org',PAYLOAD],'fake').payload,PAYLOAD)
  self.assertTrue(choose([PAYLOAD,PAYLOAD.replace('a'*32,'c'*32)],'fake').ambiguous)
 def test_no_code_allows_cv(self):
  self.assertFalse(scan_qr(np.full((240,320,3),127,np.uint8)).detected)
 def test_outline_only_never_becomes_etterna(self):
  quad=np.array([[[40,40],[200,40],[200,200],[40,200]]],np.float32)
  fake=Mock();fake.detectAndDecode.return_value=('',quad,None)
  with patch('qr_reader.zxing',return_value=None),patch('qr_reader.cv2.QRCodeDetector',return_value=fake),patch('registration.register_content',side_effect=AssertionError('CV must not run')),tempfile.TemporaryDirectory() as tmp:
   result=extract(np.full((300,300,3),127,np.uint8),tmp)
  self.assertEqual(result['status'],'qr_unreadable')
 @unittest.skipUnless(os.getenv('QR_CAMERA_TEST_IMAGE'),'Set QR_CAMERA_TEST_IMAGE to the supplied private camera example')
 def test_supplied_camera_screenshot(self):
  image=cv2.imread(os.environ['QR_CAMERA_TEST_IMAGE']);self.assertIsNotNone(image)
  scan=scan_qr(image);self.assertIsNotNone(scan.payload)
  from session_qr import parse_link
  self.assertIsNotNone(parse_link(scan.payload));self.assertEqual(scan.engine,'zxing-cpp')
  with patch('extract.qr_result',return_value={'status':'test_qr_decoded'}),patch('registration.register_content',side_effect=AssertionError('CV must not run')),tempfile.TemporaryDirectory() as tmp:
   self.assertEqual(extract(image,tmp)['status'],'test_qr_decoded')
if __name__=='__main__':unittest.main()
