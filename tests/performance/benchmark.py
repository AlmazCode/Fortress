"""Bounded real-HTTP software probe. Does not train, restart or emulate a backend."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import shutil
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from contracts.python_ports import validate_contract

MAX_MEDIA = 200 * 1024 * 1024
MAX_JSON = 32 * 1024 * 1024
STAGES = ('receipt', 'queue', 'decode', 'inference', 'rules', 'preview_evidence', 'response')
PROBE = b'FORTRESS_SYNTHETIC_READINESS_PROBE\nnot-a-decodable-video\n'


class ProbeError(ValueError):
    """Only fixed, non-sensitive codes may cross the CLI boundary."""


def digest_file(path, limit=None):
    digest, size = hashlib.sha256(), 0
    with Path(path).open('rb') as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if limit is not None and size > limit:
                raise ProbeError('input_too_large')
            digest.update(chunk)
    if not size:
        raise ProbeError('empty_input')
    return digest.hexdigest(), size


def origin_parts(origin, allow_local_http=False):
    value = urlsplit(origin)
    if (not value.hostname or value.username or value.password or value.query or value.fragment
            or value.path not in ('', '/') or value.scheme not in ('http', 'https')):
        raise ProbeError('invalid_origin')
    try:
        local = ipaddress.ip_address(value.hostname).is_loopback
    except ValueError:
        local = value.hostname.lower() == 'localhost'
    if value.scheme != 'https' and not (allow_local_http and local):
        raise ProbeError('https_required')
    value.port  # Reject malformed/out-of-range ports before any request.
    return value, local


class Client:
    def __init__(self, origin, key, *, allow_local_http=False, ca_file=None):
        self.origin, self.local_only = origin_parts(origin, allow_local_http)
        if not 16 <= len(key) <= 1024 or not key.isascii() or any(c.isspace() for c in key):
            raise ProbeError('invalid_private_key')
        self.key = key
        self.context = ssl.create_default_context(cafile=ca_file)
        self.tls_verified = False

    def request(self, path, *, deadline, auth=True, wrong_key=False, upload=None, binary_limit=None):
        # Never follow redirects or attach the key to URLs supplied by a response.
        if not path.startswith('/api/') or path.startswith('//') or '?' in path or '#' in path:
            raise ProbeError('unsafe_api_path')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeError('client_deadline_exceeded')
        timeout = min(5, remaining)
        if self.origin.scheme == 'https':
            connection = http.client.HTTPSConnection(self.origin.hostname, self.origin.port,
                context=self.context, timeout=timeout)
        else:
            connection = http.client.HTTPConnection(self.origin.hostname, self.origin.port, timeout=timeout)
        supplied = self.key
        if wrong_key:
            supplied = uuid.uuid4().hex
            while supplied == self.key:
                supplied = uuid.uuid4().hex
        headers = {'X-API-Key': supplied} if auth else {}
        response = None
        try:
            if upload is None:
                connection.request('GET', path, headers=headers)
            else:
                file, expected_hash, size = upload
                boundary = 'fortress-' + uuid.uuid4().hex
                prefix = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                          'filename="synthetic.mp4"\r\nContent-Type: video/mp4\r\n\r\n').encode('ascii')
                suffix = f'\r\n--{boundary}--\r\n'.encode('ascii')
                connection.putrequest('POST', path)
                for name, value in {**headers, 'Content-Type': 'multipart/form-data; boundary=' + boundary,
                                    'Content-Length': str(len(prefix) + size + len(suffix))}.items():
                    connection.putheader(name, value)
                connection.endheaders()
                connection.send(prefix)
                digest, sent = hashlib.sha256(), 0
                if file is None:
                    chunks = iter([PROBE])
                    source = None
                else:
                    source = Path(file).open('rb')
                    chunks = iter(lambda: source.read(1024 * 1024), b'')
                try:
                    for chunk in chunks:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ProbeError('client_deadline_exceeded')
                        if connection.sock:
                            connection.sock.settimeout(min(5, remaining))
                        sent += len(chunk)
                        if sent > size:
                            raise ProbeError('input_changed')
                        digest.update(chunk)
                        connection.send(chunk)
                finally:
                    if source is not None:
                        source.close()
                if sent != size or digest.hexdigest() != expected_hash:
                    raise ProbeError('input_changed')
                connection.send(suffix)
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'client_deadline_exceeded')
            transport_socket = connection.sock
            if transport_socket:
                transport_socket.settimeout(min(5, remaining))
            response = connection.getresponse()
            if self.origin.scheme == 'https':
                self.tls_verified = True
            if 300 <= response.status < 400:
                raise ProbeError('redirect_refused')
            limit = binary_limit if binary_limit is not None else MAX_JSON
            declared = response.getheader('Content-Length')
            if declared is not None:
                require(declared.strip().isdecimal(), 'invalid_response_length')
                declared = int(declared)
                require(declared <= limit, 'response_too_large')
            digest, total, chunks = hashlib.sha256(), 0, []
            while True:
                if response.isclosed():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProbeError('client_deadline_exceeded')
                # CPython 3.11 hands a Connection: close socket to the response
                # reader. The connection's old socket may already be closed.
                reader_socket = getattr(getattr(response.fp, 'raw', None), '_sock', None)
                if reader_socket is None:
                    raise ProbeError('unsupported_response_transport')
                reader_socket.settimeout(min(5, remaining))
                chunk = response.read1(min(65536, limit - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ProbeError('response_too_large')
                digest.update(chunk)
                if binary_limit is None:
                    chunks.append(chunk)
            require(declared is None or total == declared, 'incomplete_response_body')
            content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
            payload = {'sha256': digest.hexdigest(), 'bytes': total} if binary_limit is not None else json.loads(b''.join(chunks))
            return response.status, content_type, payload
        except TimeoutError:
            raise ProbeError('request_timed_out') from None
        finally:
            if response is not None:
                response.close()
            connection.close()

    def json(self, path, *, deadline, auth=True, wrong_key=False, upload=None):
        status, content_type, payload = self.request(path, deadline=deadline, auth=auth, wrong_key=wrong_key, upload=upload)
        if content_type != 'application/json' or not isinstance(payload, dict):
            raise ProbeError('invalid_json_response')
        return status, payload


def require(condition, reason):
    if not condition:
        raise ProbeError(reason)


def validate_error(status, payload, code):
    validate_contract('diagnostics', payload)
    require(payload.get('error', {}).get('status') == status and payload['error']['code'] == code,
            'error_envelope_disagrees_with_http')


def auth_checks(client, deadline):
    unknown = str(uuid.uuid4())
    for path in ('/api/ui/v1/model', f'/api/v1/jobs/{unknown}', f'/api/ui/v1/jobs/{unknown}/media'):
        status, payload = client.json(path, deadline=deadline, auth=False)
        require(status == 401, 'unauthorized_route_exposed')
        validate_error(status, payload, 'invalid_key')
    status, payload = client.json('/api/ui/v1/model', deadline=deadline, wrong_key=True)
    require(status == 401, 'wrong_key_accepted')
    validate_error(status, payload, 'invalid_key')
    status, payload = client.json(f'/api/v1/jobs/{unknown}', deadline=deadline)
    require(status == 404, 'unknown_job_not_rejected')
    validate_error(status, payload, 'job_not_found')


def model_state(client, deadline):
    status, value = client.json('/api/ui/v1/model', deadline=deadline)
    require(status == 200, 'model_status_unavailable')
    validate_contract('diagnostics', value)
    return value


def production_gate(client, *, timeout=30):
    started = time.monotonic()
    deadline = started + timeout
    auth_checks(client, deadline)
    model = model_state(client, deadline)
    require(model.get('status') == 'not_ready' and model.get('test_only') is False,
            'expected_production_model_gate')
    upload = (None, hashlib.sha256(PROBE).hexdigest(), len(PROBE))
    status, value = client.json('/api/v1/analyze', deadline=deadline, upload=upload)
    require(status == 503, 'upload_was_not_gated')
    validate_error(status, value, 'model_not_ready')
    require('job_id' not in value,
            'unexpected_readiness_failure')
    return {'passed': True, 'kind': 'production_gate', 'unauthenticated_status': 401,
            'unknown_job_status': 404, 'upload_status': 503, 'accepted_job': False,
            'probe_is_decodable_video': False, 'elapsed_sec': time.monotonic() - started}


def fetch_media(client, path, *, deadline, limit, content_type):
    status, actual_type, value = client.request(path, deadline=deadline, binary_limit=limit)
    require(status == 200 and actual_type == content_type and value['bytes'] > 0, 'invalid_media_response')
    return value


def analysis_run(client, video, *, timeout=300, poll_interval=.5, expected_terminal='done', expected_reason=None):
    sha, size = digest_file(video, MAX_MEDIA)
    started = time.monotonic()
    deadline = started + timeout
    auth_checks(client, deadline)
    readiness = model_state(client, deadline)
    require(readiness.get('test_only') is True, 'synthetic_test_profile_required')
    upload_started = time.monotonic()
    status, value = client.json('/api/v1/analyze', deadline=deadline, upload=(video, sha, size))
    require(status == 202 and set(value) == {'job_id'}, 'upload_not_accepted')
    job = str(uuid.UUID(value['job_id']))
    accepted = time.monotonic()
    observations = []
    while True:
        status, public = client.json(f'/api/v1/jobs/{job}', deadline=deadline)
        require(status == 200, 'job_status_unavailable')
        validate_contract('job', public)
        require(public['job_id'] == job, 'job_identity_changed')
        status, diagnostics = client.json(f'/api/ui/v1/jobs/{job}', deadline=deadline)
        require(status == 200, 'diagnostics_unavailable')
        validate_contract('diagnostics', diagnostics)
        require(diagnostics['job_id'] == job and diagnostics['provenance']['kind'] == 'synthetic',
                'synthetic_job_identity_changed')
        stage = diagnostics['stage']
        if not observations or observations[-1]['stage'] != stage:
            require(len(observations) < 64, 'unbounded_stage_changes')
            observations.append({'stage': stage, 'client_elapsed_sec': time.monotonic() - upload_started})
        if public['status'] != 'processing':
            terminal_at = time.monotonic()
            break
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'client_deadline_exceeded')
        time.sleep(min(poll_interval, remaining))
    require(public['status'] == expected_terminal, 'unexpected_terminal_state')
    require(public['status'] != 'done' or diagnostics['coverage'] != 'none', 'no_coverage_cannot_be_done')
    if expected_reason is not None:
        require(public.get('reason') == expected_reason, 'unexpected_failure_reason')
    # Diagnostics may have advanced after the public poll; compare at terminal only.
    require(diagnostics['public'] == public, 'terminal_diagnostics_disagree')
    prefix = f'/api/ui/v1/jobs/{job}'
    media_started = time.monotonic()
    original = diagnostics['media']['original']
    require(original is not None and original['url'] == prefix + '/media', 'unsafe_original_link')
    downloaded = fetch_media(client, original['url'], deadline=deadline,
                             limit=min(original['max_bytes'], MAX_MEDIA), content_type=original['content_type'])
    require(downloaded == {'sha256': sha, 'bytes': size}, 'original_hash_mismatch')
    frames = 0
    if public['status'] == 'done':
        preview = diagnostics['media']['preview']
        require(preview is not None and preview['url'] == prefix + '/preview', 'unsafe_preview_link')
        fetch_media(client, preview['url'], deadline=deadline,
                    limit=min(preview['max_bytes'], MAX_MEDIA), content_type='video/mp4')
        for event_index, event in enumerate(public['violations']):
            for frame_index, frame in enumerate(event['evidence_frames']):
                expected = hashlib.sha256(base64.b64decode(frame['image_base64'], validate=True)).hexdigest()
                actual = fetch_media(client, f'{prefix}/frames/v{event_index}f{frame_index}',
                                     deadline=deadline, limit=6 * 1024 * 1024, content_type='image/jpeg')
                require(actual['sha256'] == expected, 'evidence_frame_mismatch')
                frames += 1
    return {'passed': True, 'kind': 'synthetic_analysis', 'job_id': job, 'terminal': public['status'],
            'reason': public.get('reason'), 'coverage': diagnostics['coverage'],
            'source_sha256': sha, 'source_bytes': size, 'source_frames_checked': frames,
            'versions': diagnostics['versions'], 'upload_accept_elapsed_sec': accepted - upload_started,
            'accept_to_terminal_elapsed_sec': terminal_at - accepted,
            'client_upload_to_terminal_sec': terminal_at - upload_started,
            'media_fetch_elapsed_sec': time.monotonic() - media_started,
            'observed_stages': observations,
            'server_stage_sec': {stage: None for stage in STAGES},
            'server_stage_reason': 'No per-stage timing telemetry in the accepted K API contract',
            'server_receipt_to_response_sec': None, 'ram_peak_bytes': None, 'vram_peak_mib': None}


def latency_summary(samples):
    values = sorted(sample['client_upload_to_terminal_sec'] for sample in samples
                    if sample.get('passed') and not sample.get('warmup') and sample.get('terminal') == 'done')
    return {'unit': 'seconds', 'method': 'nearest_rank', 'n': len(values),
            'p95': values[math.ceil(.95 * len(values)) - 1] if values else None,
            'max': max(values) if values else None, 'min': min(values) if values else None}


def parse_pid_map(items):
    roles = {'api', 'worker', 'postgres', 'redis', 'nginx'}
    result, seen = {}, set()
    for item in items:
        name, separator, raw = item.partition('=')
        require(separator and name in roles and name not in result, 'invalid_pid_map')
        values = raw.split(',')
        require(values and all(value.isascii() and value.isdecimal() for value in values), 'invalid_pid_map')
        pids = [int(value) for value in values]
        require(all(0 < value < 2**31 for value in pids) and len(set(pids)) == len(pids)
                and not seen.intersection(pids), 'duplicate_or_invalid_pid')
        result[name] = pids
        seen.update(pids)
        require(len(seen) <= 64, 'too_many_resource_pids')
    require(bool(result), 'explicit_service_pids_required')
    return result


def process_rss_bytes(pid, *, timeout=3):
    if not isinstance(pid, int) or isinstance(pid, bool) or not 0 < pid < 2**31:
        raise ProbeError('invalid_process_id')
    if sys.platform == 'win32':
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                   f'(Get-Process -Id {pid} -ErrorAction Stop).WorkingSet64']
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        require(process.returncode == 0 and process.stdout.strip().isdecimal(), 'process_memory_unavailable')
        return int(process.stdout.strip())
    if sys.platform.startswith('linux'):
        values = Path(f'/proc/{pid}/statm').read_text(encoding='ascii').split()
        require(len(values) >= 2 and values[1].isdecimal(), 'process_memory_unavailable')
        return int(values[1]) * os.sysconf('SC_PAGE_SIZE')
    raise ProbeError('unsupported_resource_sampler_platform')


def worker_vram_mib(pids, *, timeout=3):
    executable = shutil.which('nvidia-smi')
    if executable is None or not pids:
        return None
    try:
        process = subprocess.run([executable, '--query-compute-apps=pid,used_gpu_memory',
                                  '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=timeout)
        if process.returncode:
            return None
        readings = []
        for line in process.stdout.splitlines():
            columns = [column.strip() for column in line.split(',')]
            if len(columns) == 2 and columns[0].isdecimal() and int(columns[0]) in pids:
                if not columns[1].isdecimal():
                    return None  # E.g. N/A under Windows WDDM is unknown, never zero.
                readings.append(int(columns[1]))
        return sum(readings) if readings else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def collect_resources(pid_map, *, count=10, interval=1):
    require(1 <= count <= 300 and math.isfinite(interval) and .1 <= interval <= 60
            and count * interval <= 300, 'invalid_sampling_budget')
    started = time.monotonic()
    deadline = started + max(10, min(300, count * interval + 5))
    complete_scope = set(pid_map) == {'api', 'worker', 'postgres', 'redis', 'nginx'}
    report = {'schema_version': '1.0', 'scope': 'resource_sampling_only',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.system(),
        'rss_unit': 'bytes', 'vram_unit': 'MiB', 'service_pids': pid_map,
        'pid_scope_verified': False, 'complete_service_scope': complete_scope,
        'matched_to_benchmark_job': False, 'samples': [],
        'limitations': ['Operator must include every service/child PID and correlate the sampling window with the job.',
                       'Sum of process RSS/working sets may double-count shared pages; this is not cgroup accounting.',
                       'Observed maximum is sampled, not a guaranteed instantaneous peak. No ML quality measured.']}
    report['status'] = 'collected'
    report['requested_samples'] = count
    for index in range(count):
        next_sample = started + index * interval
        delay = next_sample - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        try:
            values = {}
            for name, pids in pid_map.items():
                values[name] = 0
                for pid in pids:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, 'resource_sampler_deadline')
                    values[name] += process_rss_bytes(pid, timeout=min(3, remaining))
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'resource_sampler_deadline')
            vram = worker_vram_mib(pid_map.get('worker', []), timeout=min(3, remaining))
            report['samples'].append({'elapsed_sec': time.monotonic() - started, 'rss_bytes': values,
                'service_total_rss_bytes': sum(values.values()) if complete_scope else None,
                'worker_vram_mib': vram})
        except (OSError, ValueError, subprocess.TimeoutExpired):
            report['status'] = 'failed'
            report['reason'] = 'resource_sample_unavailable_or_budget_exhausted'
            break
    totals = [sample['service_total_rss_bytes'] for sample in report['samples'] if sample['service_total_rss_bytes'] is not None]
    vram = [sample['worker_vram_mib'] for sample in report['samples'] if sample['worker_vram_mib'] is not None]
    report['observed_max'] = {'service_rss_bytes': max(totals) if totals else None,
                              'worker_vram_mib': max(vram) if vram else None}
    return report


def hardware_from_preflight(path):
    if path is None:
        return {'source': 'not_measured', 'cpu': None, 'ram_total_bytes': None, 'gpus': []}
    with Path(path).open('rb') as source:
        raw = source.read(1024 * 1024 + 1)
    require(len(raw) <= 1024 * 1024, 'preflight_report_too_large')
    value = json.loads(raw)
    hardware = value['hardware']
    cpu, ram = hardware['cpu'], hardware['ram_bytes']
    require(isinstance(cpu, str) and 0 < len(cpu) <= 16384 and isinstance(ram, int) and not isinstance(ram, bool)
            and ram > 0, 'invalid_hardware_report')
    gpus = []
    for gpu in hardware.get('gpus', []):
        require(isinstance(gpu['name'], str) and len(gpu['name']) <= 200
                and isinstance(gpu['driver_version'], str) and len(gpu['driver_version']) <= 100
                and isinstance(gpu['memory_mib'], int) and not isinstance(gpu['memory_mib'], bool)
                and gpu['memory_mib'] > 0, 'invalid_hardware_report')
        gpus.append({key: gpu[key] for key in ('name', 'driver_version', 'memory_mib')})
    return {'source': 'operator_supplied_preflight', 'independently_verified': False,
            'report_sha256': hashlib.sha256(raw).hexdigest(), 'cpu': cpu, 'ram_total_bytes': ram, 'gpus': gpus}


def code_revision():
    try:
        process = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=5)
        value = process.stdout.strip()
        return value if process.returncode == 0 and len(value) == 40 and all(c in '0123456789abcdef' for c in value) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def working_tree_dirty():
    try:
        process = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'],
                                 capture_output=True, text=True, timeout=5)
        return bool(process.stdout.strip()) if process.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url')
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['production-gate', 'synthetic-analysis'], default='production-gate')
    parser.add_argument('--video', type=Path)
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--warmup', type=int, default=0)
    parser.add_argument('--cache-state', choices=['unspecified', 'warm', 'cold'], default='unspecified')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--poll-interval', type=float, default=.5)
    parser.add_argument('--expect-terminal', choices=['done', 'failed'], default='done')
    parser.add_argument('--expect-reason')
    parser.add_argument('--allow-local-http', action='store_true')
    parser.add_argument('--ca-file')
    parser.add_argument('--dataset-manifest', type=Path)
    parser.add_argument('--release-manifest', type=Path)
    parser.add_argument('--preflight', type=Path)
    parser.add_argument('--service-commit', help='Operator-supplied deployed service SHA; independently verify it')
    parser.add_argument('--collect-resources', action='store_true')
    parser.add_argument('--pid', action='append', default=[], help='Explicit role=pid,pid; includes all children')
    parser.add_argument('--samples', type=int, default=10)
    parser.add_argument('--sample-interval', type=float, default=1)
    args = parser.parse_args(argv)
    if args.collect_resources:
        pid_map = parse_pid_map(args.pid)
        with args.output.open('x', encoding='utf-8') as destination:
            result = collect_resources(pid_map, count=args.samples, interval=args.sample_interval)
            json.dump(result, destination, indent=2, allow_nan=False)
            destination.write('\n')
        print(json.dumps({'status': result['status'], 'samples': len(result['samples']),
                          'complete_service_scope': result['complete_service_scope']}))
        return 0 if result['status'] == 'collected' else 2
    if not args.url or args.key_file is None:
        parser.error('--url and --key-file are required for HTTP probes')
    if args.service_commit and (len(args.service_commit) != 40 or any(c not in '0123456789abcdef' for c in args.service_commit)):
        parser.error('--service-commit must be a full lowercase Git SHA')
    if (not 1 <= args.runs <= 30 or not 0 <= args.warmup <= 5 or not math.isfinite(args.timeout)
            or not 1 <= args.timeout <= 300 or not .05 <= args.poll_interval <= 5):
        parser.error('Use bounded run counts, timeout and polling interval')
    if args.mode == 'synthetic-analysis' and (args.video is None or args.video.suffix.lower() not in ('.mp4', '.mov')):
        parser.error('Synthetic analysis requires an explicitly supplied synthetic MP4/MOV')
    if args.mode == 'production-gate' and (args.runs != 1 or args.warmup):
        parser.error('The production gate is one non-benchmark probe')
    if args.expect_reason and (args.expect_terminal != 'failed' or args.expect_reason not in
            {'insufficient_evidence', 'deadline_exceeded', 'decode_failed', 'inference_failed',
             'evidence_failed', 'worker_lost', 'internal_error', 'release_invalid'}):
        parser.error('Expected failure reason requires an explicit failed outcome')
    with args.key_file.open('rb') as source:
        raw = source.read(1025)
    if len(raw) > 1024:
        raise ProbeError('invalid_private_key')
    client = Client(args.url, raw.decode('ascii').strip(), allow_local_http=args.allow_local_http, ca_file=args.ca_file)
    hashes = {'uv_lock': digest_file(ROOT / 'uv.lock')[0],
              'rule_pack': digest_file(ROOT / 'rules/packs/cases.v1.json')[0],
              'dataset_manifest': digest_file(args.dataset_manifest)[0] if args.dataset_manifest else None,
              'release_manifest': digest_file(args.release_manifest)[0] if args.release_manifest else None}
    report = {'schema_version': '1.0', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'software_check_only', 'mode': args.mode, 'client_commit': code_revision(),
        'client_working_tree_dirty': working_tree_dirty(), 'service_commit': args.service_commit,
        'service_commit_verified': False, 'artifact_hashes': hashes,
        'origin_sha256': hashlib.sha256(args.url.rstrip('/').encode('utf-8')).hexdigest(),
        'tls_verified': False, 'local_only': client.local_only,
        'external_access_verified': False, 'independent_external_observer_required': True,
        'cache_state_label': args.cache_state, 'cache_state_verified': False,
        'hardware': hardware_from_preflight(args.preflight),
        'runtime': {'python': sys.version.split()[0]}, 'samples': [],
        'ml_quality': 'not_measured', 'trained_release_performance': 'not_measured'}
    with args.output.open('x', encoding='utf-8') as destination:
        # Reserve create-only output before requests. Existing evidence is never overwritten.
        for index in range(args.runs + args.warmup):
            try:
                sample = (production_gate(client, timeout=args.timeout) if args.mode == 'production-gate' else
                    analysis_run(client, args.video, timeout=args.timeout, poll_interval=args.poll_interval,
                                 expected_terminal=args.expect_terminal, expected_reason=args.expect_reason))
            except ProbeError as error:
                sample = {'passed': False, 'reason': str(error)}
            except (ValueError, OSError, http.client.HTTPException):
                sample = {'passed': False, 'reason': 'transport_or_contract_failure'}
            sample.update(index=index, warmup=index < args.warmup)
            report['samples'].append(sample)
            if not sample['passed']:
                break  # Never keep posting after an ambiguous acceptance/transport failure.
        report['tls_verified'] = client.tls_verified
        report['client_latency'] = latency_summary(report['samples'])
        report['status'] = 'passed' if all(sample['passed'] for sample in report['samples']) else 'failed'
        json.dump(report, destination, indent=2, allow_nan=False)
        destination.write('\n')
    print(json.dumps({'status': report['status'], 'samples': len(report['samples']),
                      'external_access_verified': False, 'ml_quality': 'not_measured'}))
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, http.client.HTTPException):
        print(json.dumps({'status': 'blocked', 'reason': 'invalid_configuration_or_output',
                          'external_access_verified': False}), file=sys.stderr)
        raise SystemExit(2)
