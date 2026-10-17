import unittest
from rules.session_memory import SessionMemory
from test_session_memory import observation, timeline


class SceneResetTests(unittest.TestCase):
    def test_scene_cut_clears_current_relations_and_preserves_history(self):
        memory=SessionMemory('j','video-1')
        memory.ingest(timeline(observation('service_start',0,1),observation('party_opened',1,2,kind='party',reference='p1')),job_id='j')
        memory.ingest(timeline(observation('unrelated',3,4,scene='s2',actor=None,known=False),scene='s2'),job_id='j')
        self.assertFalse(memory.unresolved)
        self.assertTrue(memory.sessions[0].closed_by_scene)
        self.assertIsNone(memory.sessions[0].end_sec)
        self.assertEqual(len(memory.whole_video_observations),3)
        memory.ingest(timeline(observation('party_cleared',5,6,kind='party',reference='p1')),job_id='j')
        self.assertEqual(memory.scene_id,'s2')
        self.assertEqual(memory.late_scene_events,1)

    def test_window_with_wrong_scene_fails(self):
        with self.assertRaises(ValueError):
            SessionMemory('j','video-1').ingest(timeline(observation('service_start',0,1,scene='other')),job_id='j')


if __name__=='__main__': unittest.main()
