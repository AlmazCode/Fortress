import unittest
from rules.engine import RuleEngine
from test_session_memory import observation, timeline


class CaseTests(unittest.TestCase):
    def test_every_output_has_fact_indicator_source_limitation_and_versions(self):
        engine=RuleEngine(job_id='j')
        for finding in engine.evaluate(timeline(observation('synthetic_action',0,1,actor=None,known=False))):
            positions=[finding['reason'].index(label) for label in ('Факт:','Признак возможного несоответствия:','Источник:','Ограничение:')]
            self.assertEqual(positions,sorted(positions))
            self.assertIn('rules_version=',finding['reason'])
            self.assertFalse(finding['source']['verified'])
            self.assertNotIn('evidence_frames',finding)
        self.assertTrue(engine.diagnostics()['source_provenance'])

    def test_different_job_engine_memory_is_not_shared(self):
        first=RuleEngine(job_id='one'); second=RuleEngine(job_id='two')
        first.evaluate(timeline(observation('service_start',0,1)))
        self.assertIsNone(second.memory)


if __name__=='__main__': unittest.main()
