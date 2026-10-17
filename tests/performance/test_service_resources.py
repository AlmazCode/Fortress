"""Sampler software tests; observations here are not service/ML memory benchmarks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('resource_benchmark', ROOT/'tests/performance/benchmark.py')
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


class ResourceTests(unittest.TestCase):
    def test_real_native_own_process_rss_is_bytes(self):
        self.assertGreater(BENCH.process_rss_bytes(os.getpid()), 1024)

    def test_pid_map_requires_explicit_unique_bounded_service_pids(self):
        self.assertEqual(BENCH.parse_pid_map(['worker=12,13','api=14']), {'worker':[12,13],'api':[14]})
        for values in ([], ['worker=-1'], ['worker=1','api=1'], ['worker=1,1'], ['unknown=1'], ['api=0'], ['api=1;echo']):
            with self.subTest(values=values), self.assertRaises(BENCH.ProbeError):
                BENCH.parse_pid_map(values)

    def test_partial_scope_never_gets_total_service_ram(self):
        with patch.object(BENCH, 'process_rss_bytes', return_value=100):
            report = BENCH.collect_resources({'api':[1]}, count=1)
        self.assertIsNone(report['observed_max']['service_rss_bytes'])
        self.assertIsNone(report['observed_max']['worker_vram_mib'])
        self.assertFalse(report['complete_service_scope'])

    def test_full_synthetic_aggregation_has_explicit_units_and_unverified_scope(self):
        mapping = dict(zip(['api','worker','postgres','redis','nginx'], [[1],[2],[3],[4],[5]]))
        with patch.object(BENCH, 'process_rss_bytes', return_value=100), patch.object(BENCH, 'worker_vram_mib', return_value=None):
            report = BENCH.collect_resources(mapping, count=1)
        self.assertEqual(report['observed_max']['service_rss_bytes'], 500)
        self.assertEqual((report['rss_unit'], report['vram_unit']), ('bytes','MiB'))
        self.assertFalse(report['pid_scope_verified'])
        self.assertFalse(report['matched_to_benchmark_job'])
        self.assertIsNone(report['observed_max']['worker_vram_mib'])

    def test_missing_process_fails_and_does_not_become_zero_ram(self):
        with patch.object(BENCH, 'process_rss_bytes', side_effect=OSError):
            report = BENCH.collect_resources({'api':[1]}, count=1)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['samples'], [])
        self.assertIsNone(report['observed_max']['service_rss_bytes'])

    def test_cli_collects_two_real_native_samples_of_this_test_process(self):
        with tempfile.TemporaryDirectory(prefix='fortress-resource-test-') as directory:
            output = Path(directory)/'resource.json'
            process = subprocess.run([sys.executable,str(ROOT/'tests/performance/benchmark.py'),
                '--collect-resources','--pid',f'api={os.getpid()}','--samples','2','--sample-interval','.1',
                '--output',str(output)], capture_output=True,text=True,timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(len(report['samples']), 2)
            self.assertFalse(report['complete_service_scope'])
            self.assertTrue(all(sample['rss_bytes']['api'] > 0 for sample in report['samples']))
            self.assertIsNone(report['observed_max']['service_rss_bytes'])

    def test_hardware_import_excludes_private_preflight_paths_and_commands(self):
        with tempfile.TemporaryDirectory(prefix='fortress-hardware-test-') as directory:
            path = Path(directory)/'preflight.json'
            path.write_text(json.dumps({'repository':{'private_path':'DO_NOT_COPY'},'checks':{'key':'DO_NOT_COPY'},
                'hardware':{'cpu':'synthetic-test-cpu','ram_bytes':1000,'gpus':[]}}))
            result = BENCH.hardware_from_preflight(path)
            self.assertNotIn('DO_NOT_COPY', json.dumps(result))
            self.assertEqual(result['ram_total_bytes'], 1000)
            self.assertEqual(len(result['report_sha256']), 64)
            self.assertFalse(result['independently_verified'])


if __name__ == '__main__':
    unittest.main()
