"""Synthetic command outcomes test inventory logic; they do not validate hardware."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'infra/scripts/preflight.sh'
SOURCE = SCRIPT.read_text(encoding='utf-8').split('# BEGIN_FORTRESS_PREFLIGHT_PY', 1)[1].split('# END_FORTRESS_PREFLIGHT_PY', 1)[0]
PREFLIGHT = types.ModuleType('fortress_preflight')
exec(compile(SOURCE, str(SCRIPT), 'exec'), PREFLIGHT.__dict__)


def outcome(command, stdout='', status='ok'):
    return {'command':command, 'status':status, 'exit_code':0 if status == 'ok' else None,
            'stdout':stdout, 'stderr':'' if status == 'ok' else 'synthetic missing executable'}


class SyntheticCommands:
    def __init__(self, outputs=None, bad_origin=False):
        self.outputs = outputs or {}
        self.calls = []
        self.bad_origin = bad_origin

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[0] == 'git':
            fixed = {
                ('rev-parse','--show-toplevel'):str(ROOT),
                ('remote','get-url','origin'):'https://github.com/wrong/repository' if self.bad_origin else PREFLIGHT.EXPECTED_ORIGIN,
                ('cat-file','-t',PREFLIGHT.EXPECTED_BASE):'commit',
                ('branch','--show-current'):'codex/synthetic-fixture',
                ('rev-parse','HEAD'):PREFLIGHT.EXPECTED_BASE,
                ('rev-parse','refs/remotes/origin/main'):PREFLIGHT.EXPECTED_BASE,
                ('merge-base','--is-ancestor',PREFLIGHT.EXPECTED_BASE,'HEAD'):'',
            }
            return outcome(command, fixed.get(tuple(command[1:]), ''))
        value = self.outputs.get(tuple(command))
        return outcome(command, value) if value is not None else outcome(command, status='missing')


class PreflightTests(unittest.TestCase):
    def test_missing_dependencies_produce_honest_json(self):
        fake = SyntheticCommands()
        report = PREFLIGHT.collect(ROOT, runner=fake)
        self.assertEqual(report['report_status'], 'collected')
        self.assertFalse(report['readiness']['service_ready'])
        self.assertFalse(report['readiness']['gpu_ready'])
        self.assertEqual(report['checks']['docker_engine']['status'], 'missing')
        self.assertTrue(report['blockers'])
        json.dumps(report)

    def test_repository_mismatch_stops_runtime_and_network_probes(self):
        fake = SyntheticCommands(bad_origin=True)
        with patch.object(PREFLIGHT.socket, 'create_connection') as network:
            report = PREFLIGHT.collect(ROOT, runner=fake, external_url='https://example.invalid', probe_external=True)
        self.assertEqual(report['report_status'], 'repository_mismatch')
        self.assertTrue(all(command[0] == 'git' for command in fake.calls))
        network.assert_not_called()

    def test_network_only_skips_runtime_probes_and_unrelated_blockers(self):
        fake = SyntheticCommands()
        report = PREFLIGHT.collect(ROOT, runner=fake, network_only=True,
                                   container_smoke=True, gpu_image='trusted:fixture')
        self.assertTrue(all(command[0] == 'git' for command in fake.calls))
        self.assertEqual(report['checks'], {})
        self.assertEqual(report['blockers'], report['network']['blockers'])
        self.assertEqual(report['network']['tls_probe']['status'], 'not_run')
        self.assertFalse(report['readiness']['external_access_verified'])

    def test_network_only_repository_mismatch_still_prevents_tls(self):
        fake = SyntheticCommands(bad_origin=True)
        with patch.object(PREFLIGHT.socket, 'create_connection') as network:
            report = PREFLIGHT.collect(ROOT, runner=fake, network_only=True,
                                       external_url='https://example.invalid', probe_external=True)
        self.assertEqual(report['report_status'], 'repository_mismatch')
        self.assertTrue(all(command[0] == 'git' for command in fake.calls))
        network.assert_not_called()

    def test_network_only_cli_returns_only_network_scope_without_runtime_checks(self):
        fake = SyntheticCommands()
        collect = PREFLIGHT.collect
        def network_collect(*args, **kwargs):
            return collect(*args, runner=fake, **kwargs)
        output = io.StringIO()
        with patch.object(PREFLIGHT, 'collect', side_effect=network_collect), contextlib.redirect_stdout(output):
            exit_code = PREFLIGHT.main(['--network-only', '--require-tls'])
        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(report['blockers'], report['network']['blockers'])
        self.assertTrue(all(command[0] == 'git' for command in fake.calls))
        self.assertIn('no OS, WSL, Docker or GPU probes', report['scope'])

    def test_network_only_successful_tls_never_claims_external_upload(self):
        fake = SyntheticCommands()
        collect = PREFLIGHT.collect
        def network_collect(*args, **kwargs):
            return collect(*args, runner=fake, **kwargs)
        output = io.StringIO()
        with patch.object(PREFLIGHT, 'collect', side_effect=network_collect), \
             patch.object(PREFLIGHT.socket, 'create_connection'), \
             patch.object(PREFLIGHT.ssl, 'create_default_context') as tls, \
             contextlib.redirect_stdout(output):
            secured = tls.return_value.wrap_socket.return_value.__enter__.return_value
            secured.getpeercert.return_value = {'notAfter':'synthetic date'}
            secured.version.return_value = 'TLSv1.3'
            exit_code = PREFLIGHT.main(['--network-only', '--probe-external', '--require-tls',
                                        '--external-url', 'https://example.invalid'])
        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(report['network']['tls_probe']['status'], 'ok')
        self.assertFalse(report['network']['external_access_verified'])
        self.assertTrue(all(command[0] == 'git' for command in fake.calls))

    def test_network_only_cli_keeps_certificate_failure_nonzero(self):
        fake = SyntheticCommands()
        collect = PREFLIGHT.collect
        def network_collect(*args, **kwargs):
            return collect(*args, runner=fake, **kwargs)
        output = io.StringIO()
        with patch.object(PREFLIGHT, 'collect', side_effect=network_collect), \
             patch.object(PREFLIGHT.socket, 'create_connection',
                          side_effect=PREFLIGHT.ssl.SSLCertVerificationError(1, 'synthetic invalid certificate')), \
             contextlib.redirect_stdout(output):
            exit_code = PREFLIGHT.main(['--network-only', '--probe-external', '--require-tls',
                                        '--external-url', 'https://example.invalid'])
        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(report['network']['tls_probe']['status'], 'failed')
        self.assertFalse(report['network']['external_access_verified'])
        self.assertTrue(all(command[0] == 'git' for command in fake.calls))

    def test_docker_cli_does_not_imply_working_daemon(self):
        fake = SyntheticCommands({('docker','--version'):'Docker version fixture', ('docker','compose','version','--short'):'2.39.0'})
        report = PREFLIGHT.collect(ROOT, runner=fake)
        self.assertFalse(report['readiness']['docker_ready'])
        self.assertFalse(report['readiness']['compose_ready'])

    def test_host_gpu_and_driver_cuda_are_not_container_readiness(self):
        fake = SyntheticCommands({('nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader,nounits'):'Synthetic GPU, 999.0, 8192', ('nvidia-smi',):'CUDA Version: 99.0'})
        report = PREFLIGHT.collect(ROOT, runner=fake)
        self.assertEqual(report['hardware']['gpus'][0]['memory_mib'], 8192)
        self.assertFalse(report['readiness']['gpu_ready'])
        self.assertFalse(any(command[:2] == ['docker','run'] for command in fake.calls))

    def test_compose_version_must_support_explicit_reset_overlay(self):
        engine_command=('docker','info','--format','{"server_version":{{json .ServerVersion}},"os_type":{{json .OSType}},"runtimes":{{json .Runtimes}}}')
        for version,expected in [('2.23.0',False),('2.24.4',True),('v2.39.0',True)]:
            fake=SyntheticCommands({engine_command:json.dumps({'server_version':'fixture','os_type':'linux'}),('docker','compose','version','--short'):version})
            with self.subTest(version=version):
                self.assertEqual(PREFLIGHT.collect(ROOT,runner=fake)['readiness']['compose_ready'],expected)

    def test_optional_gpu_smoke_only_uses_local_image_without_network(self):
        engine_command = ('docker','info','--format','{"server_version":{{json .ServerVersion}},"os_type":{{json .OSType}},"runtimes":{{json .Runtimes}}}')
        outputs = {engine_command:json.dumps({'server_version':'fixture','os_type':'linux','runtimes':{}}),
                   ('docker','image','inspect','trusted:fixture','--format','{{.Id}}'):'sha256:fixture'}
        fake = SyntheticCommands(outputs)
        PREFLIGHT.collect(ROOT, runner=fake, container_smoke=True, gpu_image='trusted:fixture')
        calls = [command for command in fake.calls if command[:2] == ['docker','run']]
        self.assertEqual(len(calls), 1)
        self.assertIn('never', calls[0])
        self.assertIn('none', calls[0])
        self.assertIn('--read-only', calls[0])
        self.assertEqual(calls[0][-1], 'sha256:fixture')
        self.assertFalse(any(command[:2] == ['docker','pull'] for command in fake.calls))

    def test_timeout_is_recorded_not_raised_or_marked_passed(self):
        with patch.object(PREFLIGHT.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['fixture'], 1)):
            result = PREFLIGHT.run(['fixture'], timeout=1)
        self.assertEqual(result['status'], 'timeout')
        self.assertIsNone(result['exit_code'])

    def test_windows_utf16_wsl_output_is_readable(self):
        self.assertEqual(PREFLIGHT.decode_output('WSL not installed'.encode('utf-16-le')), 'WSL not installed')

    def test_invalid_or_credential_url_never_connects(self):
        with patch.object(PREFLIGHT.socket, 'create_connection') as network:
            for url in ['http://example.invalid', 'https://user:secret@example.invalid', 'https://[broken', 'https://example.invalid?token=secret']:
                result = PREFLIGHT.network_inventory(url, probe_external=True)
                self.assertEqual(result['tls_probe']['status'], 'invalid_input')
                self.assertIsNone(result['configured_url'])
        network.assert_not_called()

    def test_tls_failure_and_unknown_cgnat_do_not_become_external_pass(self):
        with patch.object(PREFLIGHT.socket, 'create_connection', side_effect=OSError('synthetic refused')):
            result = PREFLIGHT.network_inventory('https://example.invalid', probe_external=True)
        self.assertEqual(result['tls_probe']['status'], 'failed')
        self.assertEqual(result['cgnat']['state'], 'unknown')
        self.assertFalse(result['external_access_verified'])

    def test_successful_tls_still_does_not_prove_external_upload(self):
        with patch.object(PREFLIGHT.socket, 'create_connection') as connection, patch.object(PREFLIGHT.ssl, 'create_default_context') as tls:
            secured = tls.return_value.wrap_socket.return_value.__enter__.return_value
            secured.getpeercert.return_value = {'notAfter':'synthetic date'}
            secured.version.return_value = 'TLSv1.3'
            result = PREFLIGHT.network_inventory('https://example.invalid', probe_external=True)
        self.assertEqual(result['tls_probe']['status'], 'ok')
        self.assertFalse(result['external_access_verified'])
        self.assertFalse(result['independent_external_client_verified'])

    def test_shared_address_is_only_cgnat_suspicion(self):
        result = PREFLIGHT.network_inventory(wan_ip='100.64.1.2', public_ip='203.0.113.8')
        self.assertEqual(result['cgnat']['state'], 'suspected')
        self.assertFalse(result['external_access_verified'])

    def test_missing_command_is_safe(self):
        result = PREFLIGHT.run(['fortress_nonexistent_preflight_executable_629b'])
        self.assertEqual(result['status'], 'missing')

    def test_strict_exit_is_nonzero_without_service_evidence(self):
        report = PREFLIGHT.collect(ROOT, runner=SyntheticCommands())
        with patch.object(PREFLIGHT, 'collect', return_value=report), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(PREFLIGHT.main(['--strict']), 2)

    def test_shell_cli_without_python_returns_blocker_json(self):
        git = shutil.which('git')
        shell = shutil.which('sh')
        if not shell and git:
            candidate = Path(git).parent.parent / 'bin/bash.exe'
            if candidate.exists():
                shell = str(candidate)
        if not shell:
            self.skipTest('No POSIX shell available for bootstrap check')
        with tempfile.TemporaryDirectory(prefix='fortress-no-python-') as directory:
            env = dict(os.environ, PATH=directory, FORTRESS_PYTHON='')
            result = subprocess.run([shell, str(SCRIPT)], env=env, cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['report_status'], 'bootstrap_blocked')
        self.assertFalse(report['readiness']['gpu_ready'])

    def test_powershell_cli_without_python_returns_blocker_json(self):
        shell = shutil.which('pwsh')
        if not shell:
            self.skipTest('No PowerShell 7 available for bootstrap check')
        with tempfile.TemporaryDirectory(prefix='fortress-no-python-') as directory:
            env = dict(os.environ, PATH=directory)
            result = subprocess.run([shell,'-NoProfile','-File',str(SCRIPT.with_suffix('.ps1'))], env=env, cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['report_status'], 'bootstrap_blocked')
        self.assertFalse(report['readiness']['service_ready'])


if __name__ == '__main__':
    unittest.main()
