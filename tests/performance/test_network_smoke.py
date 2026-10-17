"""Real loopback HTTP/TLS tests; no independent external route claim."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('fortress_smoke',ROOT/'infra/smoke_server.py')
SMOKE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(SMOKE)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.server=SMOKE.HarnessServer(('127.0.0.1',0),'synthetic-unit-test-key')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def test_actual_loopback_auth_upload_status_and_no_false_verdict(self):
        report=SMOKE.client_smoke(self.url,'synthetic-unit-test-key',allow_local_http=True)
        self.assertTrue(report['current_host_smoke_passed'])
        self.assertTrue(report['local_only'])
        self.assertFalse(report['external_access_verified'])
        self.assertFalse(report['tls_verified'])
        self.assertTrue(all('verdict' not in job for job in self.server.jobs.values()))

    def test_wrong_key_is_rejected(self):
        with self.assertRaises(HTTPError) as error:
            SMOKE.client_smoke(self.url,'invalid-key',allow_local_http=True)
        self.assertEqual(error.exception.code,401)

    def test_regular_media_and_oversized_input_are_rejected(self):
        for body,expected in [(b'not-marked-real-media',400),(b'x'*4097,413)]:
            request=Request(self.url+'/api/v1/analyze',data=body,headers={'X-API-Key':'synthetic-unit-test-key','X-Fortress-Synthetic':'1','Content-Type':'application/octet-stream'})
            with self.assertRaises(HTTPError) as error: urlopen(request,timeout=3)
            self.assertEqual(error.exception.code,expected)

    def test_missing_auth_never_returns_job_data(self):
        with self.assertRaises(HTTPError) as error: urlopen(self.url+'/api/v1/jobs/private',timeout=3)
        self.assertEqual(error.exception.code,401)

    def test_synthetic_store_is_bounded(self):
        self.server.jobs.update({str(index):{} for index in range(128)})
        request=Request(self.url+'/api/v1/analyze',data=SMOKE.PAYLOAD,headers={'X-API-Key':'synthetic-unit-test-key','X-Fortress-Synthetic':'1','Content-Type':'application/octet-stream'})
        with self.assertRaises(HTTPError) as error: urlopen(request,timeout=3)
        self.assertEqual(error.exception.code,429)
        self.assertEqual(len(self.server.jobs),128)

    def test_http_requires_explicit_local_only_option_and_rejects_secret_urls(self):
        for url in [self.url,'http://example.invalid','https://user:key@example.invalid','https://example.invalid?key=secret']:
            with self.assertRaises(ValueError): SMOKE.checked_url(url)
        with self.assertRaises(ValueError): SMOKE.checked_url('http://example.invalid',True)

    def test_cli_cannot_start_harness_implicitly(self):
        env={key:value for key,value in os.environ.items() if key!='FORTRESS_INFRA_SMOKE'}
        process=subprocess.run([sys.executable,str(ROOT/'infra/smoke_server.py'),'serve'],env=env,capture_output=True,timeout=5)
        self.assertEqual(process.returncode,2)


class HarnessTlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable=os.environ.get('FORTRESS_TEST_OPENSSL') or shutil.which('openssl')
        if not executable:
            raise unittest.SkipTest('OpenSSL needed to generate ephemeral local test certificates')
        cls.directory=tempfile.TemporaryDirectory(prefix='fortress-synthetic-tls-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.certificate=Path(cls.directory.name)/'certificate.pem'
        cls.key=Path(cls.directory.name)/'private-key.pem'
        process=subprocess.run([executable,'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
            '-keyout',str(cls.key),'-out',str(cls.certificate)],capture_output=True,timeout=20)
        if process.returncode:
            raise RuntimeError('Ephemeral OpenSSL certificate generation failed')

    def setUp(self):
        self.server=SMOKE.HarnessServer(('127.0.0.1',0),'synthetic-unit-test-key')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.certificate,self.key)
        self.server.socket=context.wrap_socket(self.server.socket,server_side=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'https://localhost:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def test_explicit_private_ca_checks_real_tls_and_stays_local(self):
        report=SMOKE.client_smoke(self.url,'synthetic-unit-test-key',ca_file=str(self.certificate))
        self.assertTrue(report['tls_verified'])
        self.assertTrue(report['local_only'])
        self.assertFalse(report['external_access_verified'])
        self.assertEqual(report['upload_status'],202)
        self.assertEqual(report['poll_status'],200)

    def test_untrusted_certificate_fails_before_upload(self):
        with self.assertRaises(URLError) as error:
            SMOKE.client_smoke(self.url,'synthetic-unit-test-key')
        self.assertIsInstance(error.exception.reason,ssl.SSLCertVerificationError)
        self.assertFalse(self.server.jobs)

    def test_trusted_certificate_with_wrong_hostname_fails_before_upload(self):
        with self.assertRaises(URLError) as error:
            SMOKE.client_smoke(self.url.replace('localhost','127.0.0.1'),
                               'synthetic-unit-test-key',ca_file=str(self.certificate))
        self.assertIsInstance(error.exception.reason,ssl.SSLCertVerificationError)
        self.assertFalse(self.server.jobs)


if __name__=='__main__': unittest.main()
