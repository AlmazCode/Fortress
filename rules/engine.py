"""Five tri-state templates; normative output is gated by verified local sources."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .session_memory import SessionMemory
from .types import Interval, RuleInputs, Truth

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = frozenset({'prerequisite','unresolved-state','cross-session','presence','response'})


def evaluate_template(template: str, evidence: RuleInputs) -> str:
    """Pure technical logic, used with explicit synthetic inputs in tests.

    condition means: prerequisite/resolution/previous-party-resolution/forbidden-
    presence/response, respectively. It is NOT inferred from missing observations.
    All negative conclusions and every absence-based trigger require the full gate.
    """
    if template not in TEMPLATES:
        raise ValueError('Unknown rule template')
    if not evidence.recognizer_validated or not evidence.relations_known or evidence.exception == Truth.UNKNOWN:
        return 'unknown'
    if evidence.exception == Truth.TRUE:
        return 'not_triggered' if evidence.absence_ready else 'unknown'
    if evidence.antecedent == Truth.FALSE:
        return 'not_triggered' if evidence.absence_ready else 'unknown'
    if evidence.antecedent != Truth.TRUE or evidence.condition == Truth.UNKNOWN:
        return 'unknown'
    if template == 'presence':
        if evidence.condition == Truth.TRUE and evidence.visibility_complete:
            return 'triggered'
        return 'not_triggered' if evidence.condition == Truth.FALSE and evidence.absence_ready else 'unknown'
    if not evidence.absence_ready:
        return 'unknown'
    return 'triggered' if evidence.condition == Truth.FALSE else 'not_triggered'


class RuleEngine:
    def __init__(self, *, job_id: str, pack_path: Path | None = None,
                 evidence: Mapping[str, RuleInputs] | None = None):
        self.pack_path = pack_path or ROOT/'rules/packs/cases.v1.json'
        self.pack = json.loads(self.pack_path.read_text(encoding='utf-8'))
        self.sources = json.loads((ROOT/'rules/sources/index.json').read_text(encoding='utf-8'))
        self.evidence = dict(evidence or {})
        self.job_id = job_id
        self.memory: SessionMemory | None = None

    def _source(self, case: dict[str, Any]) -> dict[str, Any]:
        # Default source is an unverified summary, never a manufactured regulation.
        index = next((source for source in self.sources['sources'] if source['id'] == case.get('normative_source_id')), None)
        if not index:
            summary = next((source for source in self.sources['sources'] if source['id'] == case.get('source_id')), None)
            summary_note = (f"Non-normative case summary={summary['id']}; content_sha256={summary.get('snapshot_sha256')}"
                            if summary else 'No case-summary provenance is available')
            return {'source_kind':'unverified','url':None,'revision':None,'section':None,'snapshot_sha256':None,'verified':False,
                    'limitations':['Applicable normative source and original case are not available',summary_note,f"rules_version={self.pack['version']}"]}
        verified = False
        if (index.get('verified') is True and index.get('normative') is True and index.get('source_kind') in ('official','internal_policy')
                and index.get('applicability') == 'confirmed' and index.get('exceptions_reviewed') is True and index.get('url')
                and index.get('revision') and index.get('retrieved_at_utc') and index.get('snapshot_path')):
            path = (ROOT/index['snapshot_path']).resolve()
            if path.is_relative_to(ROOT.resolve()) and path.is_file():
                verified = hashlib.sha256(path.read_bytes()).hexdigest() == index.get('snapshot_sha256')
        return {'source_kind':index.get('source_kind','unverified'),'url':index.get('url'),'revision':index.get('revision'),
                'section':index.get('section'),'snapshot_sha256':index.get('snapshot_sha256'),'verified':verified,
                'limitations':list(index.get('limitations',[]))+[f"rules_version={self.pack['version']}"]}

    def evaluate(self, timeline: dict[str, Any]) -> list[dict[str, Any]]:
        from contracts.python_ports import validate_contract
        validate_contract('events',timeline)
        if self.memory is None:
            self.memory = SessionMemory(self.job_id,timeline['video_id'])
        self.memory.ingest(timeline,job_id=self.job_id)
        intervals = [o['interval'] for o in timeline['observations']]
        interval = Interval(min((i['start_sec'] for i in intervals),default=0),max((i['end_sec'] for i in intervals),default=0),timeline['scene_id']).as_json()
        findings = []
        for case in self.pack['cases']:
            source = self._source(case)
            supported = case['support'] == 'supported' and source['verified']
            inputs = self.evidence.get(case['id'],RuleInputs())
            scoped = (inputs.video_id == timeline['video_id'] and inputs.scene_id == timeline['scene_id']
                      and inputs.interval is not None and inputs.interval.as_json() == interval)
            status = evaluate_template(case['template'],inputs) if supported and scoped else 'unknown'
            # No scene-specific input means no affirmative result. Metadata from a
            # previous scene is never accepted solely because a class score is high.
            if self.memory.late_scene_events or self.memory.scene_id != timeline['scene_id']:
                status = 'unknown'
            observability = 'full' if inputs.absence_ready and timeline['coverage'] == 'full' else 'none' if timeline['coverage'] == 'none' else 'partial'
            if observability == 'none' or (case['template'] != 'presence' and observability != 'full'):
                status = 'unknown'
            if status == 'not_triggered' and observability != 'full':
                status = 'unknown'
            reason = (f"Факт: {len(timeline['observations'])} исходных наблюдений в сцене {timeline['scene_id']}. "
                      f"Признак возможного несоответствия: {case['title']}; результат {status}, не самостоятельный юридический вывод. "
                      f"Источник: {source['url'] or 'применимый первоисточник не предоставлен'}. "
                      f"Ограничение: {'; '.join(case['limitations'])}; rules_version={self.pack['version']}.")
            findings.append({'rule_id':case['id'],'status':status,'interval':interval.copy(),'actor_id':None,'reason':reason,
                             'support':'supported' if supported else 'unsupported','observability':observability,'source':source})
        # Validate the exact serialization, including source/unknown constraints.
        validate_contract('events',{**timeline,'findings':findings})
        return findings

    def diagnostics(self) -> dict[str, Any]:
        return {'rules_version':self.pack['version'],'source_version':self.sources['version'],
                'case_support':{case['id']:case['support'] for case in self.pack['cases']},
                'source_provenance':self.sources['sources'], 'memory':self.memory.snapshot() if self.memory else None,
                'limitations':['Internal technical diagnostics; not extra public jury fields','Synthetic tests do not validate ML or source applicability']}
