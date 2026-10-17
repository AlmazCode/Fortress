import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]


class MappingTests(unittest.TestCase):
    def test_all_routes_are_explicit_without_invented_classes_or_law(self):
        pack=json.loads((ROOT/'rules/packs/cases.v1.json').read_text(encoding='utf-8'))
        self.assertEqual([case['id'] for case in pack['cases']],[f'C{i:02}' for i in range(1,16)])
        for case in pack['cases']:
            self.assertEqual(case['support'],'unsupported')
            self.assertEqual(case['legal_status'],'unknown')
            self.assertIsNone(case['normative_source_id'])
            self.assertEqual(case['action_classes'],[])
            for field in ('prerequisites','data_required','exceptions','limitations','absence_requirements','tests'):
                self.assertTrue(case[field])

    def test_local_summary_hash_does_not_certify_a_normative_source(self):
        index=json.loads((ROOT/'rules/sources/index.json').read_text(encoding='utf-8'))
        records=[json.loads(line) for line in (ROOT/'rules/sources/snapshots.jsonl').read_text(encoding='utf-8').splitlines()]
        for source in index['sources']:
            record=next(r for r in records if r['source_id']==source['id'])
            self.assertEqual(hashlib.sha256(record['content'].encode('utf-8')).hexdigest(),source['snapshot_sha256'])
            self.assertFalse(source['verified'])
            self.assertFalse(source['normative'])
            self.assertIsNone(source['jurisdiction'])


if __name__=='__main__': unittest.main()
