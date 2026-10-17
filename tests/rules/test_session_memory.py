"""Explicit synthetic K observations; not actor/ML validation."""
from copy import deepcopy
import unittest

from rules.session_memory import SessionMemory


def observation(action, start, end, scene='s1', actor='operator', kind='session', reference='session-1', known=True, visibility='visible', state='present'):
    return {'class_id':action,'interval':{'start_sec':start,'end_sec':end,'scene_id':scene},'score':0.99,
            'state':state,'known_mask':state in ('present','absent_verified'),'visibility':visibility,
            'actor_id':actor,'relations':[{'kind':kind,'subject_id':actor if known else None,'object_id':reference if known else None,'known':known}]}


def timeline(*observations, scene='s1', video='video-1'):
    return {'schema_version':'1.0','video_id':video,'scene_id':scene,'preprocessing_version':'synthetic-v1',
            'model_version':'synthetic-not-trained','coverage':'partial','observations':list(observations),'findings':[]}


class MemoryTests(unittest.TestCase):
    def test_overlapping_windows_deduplicate_and_keep_whole_video(self):
        memory=SessionMemory('job-1','video-1')
        first=observation('service_start',0,1)
        memory.ingest(timeline(first),job_id='job-1')
        memory.ingest(timeline(first,observation('service_end',9,10)),job_id='job-1')
        self.assertEqual(len(memory.observations),2)
        self.assertEqual(memory.sessions[0].end_sec,10)
        self.assertFalse(memory.sessions[0].visibility_complete)

    def test_late_event_rebuilds_in_source_time_order(self):
        memory=SessionMemory('j','video-1')
        memory.ingest(timeline(observation('service_end',9,10)),job_id='j')
        memory.ingest(timeline(observation('service_start',0,1)),job_id='j')
        self.assertEqual(memory.sessions[0].end_sec,10)

    def test_unknown_actor_and_link_are_never_inferred_from_score(self):
        memory=SessionMemory('j','video-1')
        memory.ingest(timeline(observation('service_start',0,1,actor=None,known=False)),job_id='j')
        self.assertEqual(memory.sessions,[])
        self.assertTrue(memory.unknown_links)

    def test_occlusion_does_not_resolve_party(self):
        memory=SessionMemory('j','video-1')
        memory.ingest(timeline(observation('party_opened',0,1,kind='party',reference='p1'),observation('party_stored',3,4,kind='party',reference='p1',visibility='occluded',state='unknown')),job_id='j')
        self.assertEqual(len(memory.unresolved),1)

    def test_two_job_instances_are_isolated(self):
        first=SessionMemory('one','video-1'); second=SessionMemory('two','video-1')
        first.ingest(timeline(observation('service_start',0,1)),job_id='one')
        self.assertFalse(second.observations)
        with self.assertRaises(ValueError): first.ingest(timeline(),job_id='two')

    def test_new_video_cannot_reuse_state(self):
        with self.assertRaises(ValueError): SessionMemory('j','video-1').ingest(timeline(video='video-2'),job_id='j')

    def test_independent_sessions_and_parties_do_not_close_each_other(self):
        memory=SessionMemory('j','video-1')
        memory.ingest(timeline(observation('party_opened',0,1,kind='party',reference='p1'),observation('party_cleared',2,3,kind='party',reference='p2')),job_id='j')
        self.assertEqual(memory.unresolved,{('s1','operator','p1')})


if __name__=='__main__': unittest.main()
