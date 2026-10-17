"""Native real HTTP/TLS client tests. Protocol fixture is not the application."""
import base64
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('benchmark_client', ROOT/'tests/performance/benchmark.py')
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)
FIXTURES = json.loads((ROOT/'contracts/fixtures.json').read_text(encoding='utf-8'))['cases']
PUBLIC = next(case['payload'] for case in FIXTURES if case['name'] == 'violation')
KEY = 'synthetic-protocol-fixture-key'
JOB = PUBLIC['job_id']
VIDEO = b'EXPLICIT SYNTHETIC PROTOCOL FIXTURE; NOT DECODED VIDEO'


class ProtocolServer(ThreadingHTTPServer):
    daemon_threads = True
    production = True
    fail_reason = None
    corrupt_original = False
    foreign_link = False
    foreign_job = False
    no_coverage = False
    redirect = False
    keep_processing = False
    legacy_not_found = False
    truncated = False
    drip = False
    uploads = 0
    requests_seen = 0

    def handle_error(self, request, client_address):
        pass


class ProtocolHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body, content_type='application/json'):
        raw = json.dumps(body).encode() if content_type == 'application/json' else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw) + (5 if self.server.truncated else 0)))
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.server.drip:
            for byte in raw:
                self.wfile.write(bytes([byte]))
                self.wfile.flush()
                time.sleep(.03)
        else:
            self.wfile.write(raw)

    def error(self, status, code):
        self.reply(status, {'error': {'code': code, 'message': 'Synthetic protocol check.', 'status': status}})

    def authorized(self):
        self.server.requests_seen += 1
        if self.headers.get('X-API-Key') != KEY:
            self.error(401, 'invalid_key')
            return False
        return True

    def public(self):
        if self.server.keep_processing:
            return {'job_id': JOB, 'status': 'processing'}
        if self.server.fail_reason:
            return {'job_id': JOB, 'status': 'failed', 'reason': self.server.fail_reason}
        return copy.deepcopy(PUBLIC)

    def do_GET(self):
        if not self.authorized():
            return
        if self.server.redirect:
            self.send_response(302)
            self.send_header('Location', 'https://example.invalid/private-key-collector')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if self.path == '/api/ui/v1/model':
            self.reply(200, {'schema_version': '1.0', 'status': 'not_ready', 'reason': 'model_not_ready',
                'release_version': None, 'trained': False, 'validated': False,
                'test_only': not self.server.production, 'limitations': ['Protocol fixture only.']})
        elif self.path == f'/api/v1/jobs/{JOB}':
            value = self.public()
            if self.server.foreign_job:
                value['job_id'] = '11111111-1111-4111-8111-111111111111'
            self.reply(200, value)
        elif self.path == f'/api/ui/v1/jobs/{JOB}':
            public = self.public()
            prefix = f'/api/ui/v1/jobs/{JOB}'
            media = {'url': prefix+'/media', 'content_type': 'video/mp4', 'max_bytes': 200*1024*1024}
            if self.server.foreign_link:
                media['url'] = '/api/ui/v1/jobs/11111111-1111-4111-8111-111111111111/media'
            self.reply(200, {'schema_version': '1.0', 'job_id': JOB, 'public': public,
                'stage': 'inference' if public['status'] == 'processing' else public['status'],
                'processed_sec': None, 'duration_sec': 1, 'coverage': 'none' if self.server.no_coverage else 'partial',
                'unknown': ['Synthetic observations.'], 'unsupported': ['Production norms.'],
                'limitations': ['Protocol fixture is not a real backend or ML.'],
                'versions': {name: None for name in ['dataset','annotations','split','rules','model','preprocessing','taxonomy']},
                'timeline': None, 'media': {'original': media, 'preview':
                    {**media, 'url': prefix+'/preview'} if public['status'] == 'done' else None},
                'provenance': {'kind': 'synthetic', 'source_id': 'protocol-fixture', 'sha256': BENCH.hashlib.sha256(VIDEO).hexdigest()}})
        elif self.path == f'/api/ui/v1/jobs/{JOB}/media':
            self.reply(200, b'corrupt' if self.server.corrupt_original else VIDEO, 'video/mp4')
        elif self.path == f'/api/ui/v1/jobs/{JOB}/preview':
            self.reply(200, b'synthetic-preview', 'video/mp4')
        elif self.path == f'/api/ui/v1/jobs/{JOB}/frames/v0f0':
            self.reply(200, base64.b64decode(PUBLIC['violations'][0]['evidence_frames'][0]['image_base64']), 'image/jpeg')
        else:
            self.error(404, 'not_found' if self.server.legacy_not_found else 'job_not_found')

    def do_POST(self):
        if not self.authorized():
            return
        body = self.rfile.read(int(self.headers['Content-Length']))
        self.server.uploads += 1
        if self.server.production:
            self.error(503, 'model_not_ready')
        elif b'name="file"' in body and VIDEO in body:
            self.reply(202, {'job_id': JOB})
        else:
            self.error(400, 'invalid_request')


class ClientProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='fortress-protocol-')
        self.addCleanup(self.directory.cleanup)
        self.video = Path(self.directory.name)/'synthetic.mp4'
        self.video.write_bytes(VIDEO)
        self.server = ProtocolServer(('127.0.0.1', 0), ProtocolHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.client = BENCH.Client(self.url, KEY, allow_local_http=True)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def test_real_http_gate_and_no_accepted_job(self):
        result = BENCH.production_gate(self.client)
        self.assertEqual(result['upload_status'], 503)
        self.assertFalse(result['accepted_job'])
        self.assertFalse(self.client.tls_verified)

    def test_noncontract_not_found_error_is_rejected(self):
        self.server.legacy_not_found = True
        with self.assertRaises(ValueError):
            BENCH.production_gate(self.client)

    def test_synthetic_upload_status_original_preview_and_jpeg(self):
        self.server.production = False
        result = BENCH.analysis_run(self.client, self.video)
        self.assertEqual(result['terminal'], 'done')
        self.assertEqual(result['source_frames_checked'], 1)
        self.assertTrue(all(value is None for value in result['server_stage_sec'].values()))
        self.assertIsNone(result['server_receipt_to_response_sec'])
        self.assertIsNone(result['vram_peak_mib'])

    def test_explicit_insufficient_evidence_is_not_clean_verdict(self):
        self.server.production = False
        self.server.fail_reason = 'insufficient_evidence'
        result = BENCH.analysis_run(self.client, self.video, expected_terminal='failed', expected_reason='insufficient_evidence')
        self.assertEqual(result['terminal'], 'failed')
        self.assertEqual(result['source_frames_checked'], 0)
        self.assertIsNone(BENCH.latency_summary([result])['p95'])

    def test_analysis_refuses_production_before_upload(self):
        with self.assertRaisesRegex(BENCH.ProbeError, 'synthetic_test_profile_required'):
            BENCH.analysis_run(self.client, self.video)
        self.assertEqual(self.server.uploads, 0)

    def test_changed_job_or_foreign_media_are_rejected(self):
        self.server.production = False
        for flag in ('foreign_job', 'foreign_link'):
            with self.subTest(flag=flag):
                setattr(self.server, flag, True)
                with self.assertRaises(BENCH.ProbeError):
                    BENCH.analysis_run(self.client, self.video)
                setattr(self.server, flag, False)

    def test_source_hash_and_no_coverage_regressions_are_rejected(self):
        self.server.production = False
        self.server.corrupt_original = True
        with self.assertRaisesRegex(BENCH.ProbeError, 'original_hash_mismatch'):
            BENCH.analysis_run(self.client, self.video)
        self.server.corrupt_original = False
        self.server.no_coverage = True
        with self.assertRaises(ValueError):
            BENCH.analysis_run(self.client, self.video)

    def test_redirect_is_not_followed(self):
        self.server.redirect = True
        with self.assertRaisesRegex(BENCH.ProbeError, 'redirect_refused'):
            BENCH.production_gate(self.client)

    def test_binary_response_is_bounded(self):
        with self.assertRaisesRegex(BENCH.ProbeError, 'response_too_large'):
            self.client.request(f'/api/ui/v1/jobs/{JOB}/media', deadline=time.monotonic()+2, binary_limit=3)

    def test_truncated_valid_json_body_is_still_a_transport_failure(self):
        self.server.truncated = True
        with self.assertRaisesRegex(BENCH.ProbeError, 'incomplete_response_body'):
            self.client.json('/api/ui/v1/model', deadline=time.monotonic()+2)

    def test_slow_drip_body_cannot_extend_absolute_deadline(self):
        self.server.drip = True
        started = time.monotonic()
        with self.assertRaises(BENCH.ProbeError):
            self.client.json('/api/ui/v1/model', deadline=started+.15)
        self.assertLess(time.monotonic()-started, 1)

    def test_processing_has_an_absolute_client_deadline(self):
        self.server.production = False
        self.server.keep_processing = True
        started = time.monotonic()
        with self.assertRaises(BENCH.ProbeError):
            BENCH.analysis_run(self.client, self.video, timeout=.15, poll_interval=.03)
        self.assertLess(time.monotonic()-started, 1)

    def test_cli_report_has_no_key_or_path_and_cannot_overwrite_evidence(self):
        key_file = Path(self.directory.name)/'key.txt'
        key_file.write_text(KEY, encoding='ascii')
        output = Path(self.directory.name)/'report.json'
        command = [sys.executable, str(ROOT/'tests/performance/benchmark.py'), '--url', self.url,
                   '--key-file', str(key_file), '--output', str(output), '--allow-local-http']
        process = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        raw = output.read_text(encoding='utf-8')
        report = json.loads(raw)
        self.assertFalse(report['external_access_verified'])
        self.assertFalse(report['tls_verified'])
        self.assertNotIn(KEY, raw + process.stdout + process.stderr)
        self.assertNotIn(self.directory.name, raw)
        before = self.server.requests_seen
        process = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(self.server.requests_seen, before)
        self.assertEqual(output.read_text(encoding='utf-8'), raw)


class TlsClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get('FORTRESS_TEST_OPENSSL') or shutil.which('openssl')
        if not executable:
            raise unittest.SkipTest('OpenSSL needed for ephemeral TLS certificate')
        cls.directory = tempfile.TemporaryDirectory(prefix='fortress-client-tls-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.certificate = Path(cls.directory.name)/'certificate.pem'
        cls.private_key = Path(cls.directory.name)/'key.pem'
        process = subprocess.run([executable, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
            '-keyout', str(cls.private_key), '-out', str(cls.certificate)], capture_output=True, timeout=20)
        if process.returncode:
            raise RuntimeError('Ephemeral TLS fixture generation failed')

    def setUp(self):
        self.server = ProtocolServer(('127.0.0.1', 0), ProtocolHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.certificate, self.private_key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'https://localhost:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def test_verified_private_ca_is_local_and_untrusted_or_wrong_hostname_fails(self):
        client = BENCH.Client(self.url, KEY, ca_file=str(self.certificate))
        self.assertTrue(BENCH.production_gate(client)['passed'])
        self.assertTrue(client.tls_verified)
        self.assertTrue(client.local_only)
        for origin, ca in [(self.url, None), (self.url.replace('localhost','127.0.0.1'),str(self.certificate))]:
            with self.subTest(origin=origin):
                client = BENCH.Client(origin, KEY, ca_file=ca)
                with self.assertRaises(ssl.SSLCertVerificationError):
                    BENCH.production_gate(client)
                self.assertFalse(client.tls_verified)


if __name__ == '__main__':
    unittest.main()
