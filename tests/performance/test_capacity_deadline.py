"""Client timing/statistical checks; real admission/fencing tests still require I."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('timing_benchmark', ROOT/'tests/performance/benchmark.py')
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


class StatisticsTests(unittest.TestCase):
    def test_nearest_rank_p95_excludes_warmup_failed_and_wrong_terminal_samples(self):
        samples = [{'passed':True,'terminal':'done','client_upload_to_terminal_sec':value} for value in range(1,21)]
        samples += [{'passed':True,'terminal':'done','client_upload_to_terminal_sec':999,'warmup':True},
                    {'passed':False,'terminal':'done','client_upload_to_terminal_sec':999},
                    {'passed':True,'terminal':'failed','client_upload_to_terminal_sec':999}]
        result = BENCH.latency_summary(samples)
        self.assertEqual((result['n'],result['p95'],result['max']), (20,19,20))
        self.assertEqual(result['unit'],'seconds')

    def test_missing_samples_are_not_zero_latency(self):
        self.assertEqual(BENCH.latency_summary([]),{'unit':'seconds','method':'nearest_rank','n':0,'p95':None,'max':None,'min':None})

    def test_sampling_count_interval_and_duplicate_pid_budgets_are_bounded(self):
        for count, interval in [(0,1),(301,1),(1,float('nan')),(30,60), (1,0)]:
            with self.subTest(count=count,interval=interval), self.assertRaises(BENCH.ProbeError):
                BENCH.collect_resources({'api':[1]},count=count,interval=interval)


if __name__ == '__main__':
    unittest.main()
