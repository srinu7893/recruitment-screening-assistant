import base64
import os
import struct
import unittest
from unittest.mock import patch, MagicMock
from screening.scanning import scan_upload
from screening.documents import extract_upload


class ScanningTests(unittest.TestCase):
    def scan(self, replies):
        connection=MagicMock()
        connection.__enter__.return_value=connection
        connection.recv.side_effect=replies
        with patch('screening.scanning.check_signatures'), patch.dict(os.environ, {'SCREENING_SCAN_MODE':'clamd'}), patch('screening.scanning.socket.create_connection',return_value=connection):
            result=scan_upload(b'resume')
        self.assertEqual(connection.sendall.call_args_list[0].args[0],b'zINSTREAM\0')
        self.assertEqual(connection.sendall.call_args_list[1].args[0],struct.pack('!I',6)+b'resume')
        return result

    def test_clean_fragmented_reply(self):
        self.assertEqual(self.scan([b'stream: ',b'OK\0'])['status'],'clean')

    def test_nonclean_and_incomplete_verdicts_block(self):
        for reply in (b'stream: Test FOUND\0',b'error\0',b'stream: OK',b'',b'x'*4096):
            with self.subTest(reply=reply[:30]),self.assertRaises(ValueError):
                self.scan([reply,b''])

    def test_cloud_cannot_disable(self):
        with patch.dict(os.environ,{'K_SERVICE':'cloud','SCREENING_SCAN_MODE':'off'}),self.assertRaises(ValueError):
            scan_upload(b'resume')

    def test_connection_failure_blocks_before_parser(self):
        with patch.dict(os.environ,{'SCREENING_SCAN_MODE':'clamd'}),patch('screening.scanning.socket.create_connection',side_effect=TimeoutError),patch('screening.documents.subprocess.Popen') as parser:
            with self.assertRaisesRegex(ValueError,'upload blocked'):
                extract_upload('resume.txt',base64.b64encode(b'resume').decode())
            parser.assert_not_called()

    def test_unknown_or_stale_signatures_block(self):
        from screening.scanning import check_signatures
        connection=MagicMock();connection.__enter__.return_value=connection
        for reply in (b'ClamAV 1.0/123/Mon Jan 01 00:00:00 2001\0', b'ClamAV 1.0\0'):
            connection.recv.return_value=reply
            with patch('screening.scanning.socket.create_connection',return_value=connection),self.assertRaises(ValueError):
                check_signatures()


@unittest.skipUnless(os.environ.get('RUN_CLAMD_TEST') == '1', 'Real clamd CI integration')
class RealScannerTests(unittest.TestCase):
    def test_real_engine_clean_and_custom_benign_detection(self):
        import socket, subprocess, tempfile, time
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            marker=b'RECRUITMENT_BENIGN_SCANNER_TEST_MARKER_12345'
            (root/'test.ndb').write_text('RecruitmentTest:0:*:'+marker.hex()+'\n')
            config=root/'clamd.conf'
            config.write_text('TCPSocket 3310\nTCPAddr 127.0.0.1\nDatabaseDirectory '+directory+'\nForeground yes\n')
            proc=subprocess.Popen(['/usr/sbin/clamd','--config-file='+str(config),'--foreground=true'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if proc.poll() is not None:
                        self.fail(proc.communicate()[0].decode())
                    try:
                        with socket.create_connection(('127.0.0.1',3310),timeout=.1):break
                    except OSError:time.sleep(.1)
                # Custom test signatures have no daily.cvd version: freshness is unit tested separately.
                with patch.dict(os.environ,{'SCREENING_SCAN_MODE':'clamd'}),patch('screening.scanning.check_signatures'):
                    self.assertEqual(scan_upload(b'Clean fictional resume')['status'],'clean')
                    with self.assertRaisesRegex(ValueError,'blocked by malware'):scan_upload(marker)
            finally:
                proc.terminate()
                try:proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.communicate()
