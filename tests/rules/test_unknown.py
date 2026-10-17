import unittest
from rules.engine import RuleEngine
from test_session_memory import observation, timeline


class UnknownTests(unittest.TestCase):
    def test_every_unsupported_route_is_unknown_even_with_high_scores(self):
        engine=RuleEngine(job_id='j')
        findings=engine.evaluate(timeline(observation('cash_on_table',0,1),observation('touch_pc',1,2),observation('bright_frame',2,3),observation('leave',3,4)))
        self.assertEqual(len(findings),15)
        self.assertTrue(all(f['status']=='unknown' and f['support']=='unsupported' for f in findings))
        self.assertTrue(all(f['actor_id'] is None for f in findings))

    def test_no_observations_do_not_yield_clean_verdict(self):
        empty=timeline(); empty['coverage']='none'
        findings=RuleEngine(job_id='j').evaluate(empty)
        self.assertTrue(all(f['status']=='unknown' for f in findings))
        self.assertTrue(all(f['observability']=='none' for f in findings))


if __name__=='__main__': unittest.main()
