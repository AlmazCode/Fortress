"""Actual frozen local model -> explicitly experimental jury-shaped result.

The binary verdict has no validated event attribution. A review frame is a real
source frame; it is not presented as a proven rule violation or exact onset.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from contracts.python_ports import AnalysisBundle, validate_contract
from backend.app.media import EvidenceProvider, MediaService
from backend.app.schemas import media_links
from backend.app.storage import LocalStorage
from .repository import LocalRepository


LIMITATIONS = [
    'Локальный исследовательский прототип: средняя grouped accuracy 71.30%; цель 80% не достигнута.',
    'Точный тип нарушения, причинная связь кадра с вердиктом и границы события не подтверждены.',
    'Нормативная применимость неизвестна; результат требует ручной проверки.',
    'Новый ракурс и CPU/CUDA numerical parity не валидированы.'
]


def predictor(bundle, device):
    # Preserve the measured GRU control; do not deploy the regressing boundary candidates.
    from ml.object_state_infer import Predictor
    return Predictor(Path(bundle), device)


def make_result(job, raw, evidence, *, deadline_monotonic):
    if raw['source_sha256'] != job.upload.sha256:
        raise ValueError('Input identity changed')
    if raw.get('normative_status') != 'unknown' or not raw.get('frames'):
        raise ValueError('Unsupported model output')
    violations = []
    if raw['prediction'] == 'violation':
        # This is a review anchor only, not an event-localization claim.
        keys = ('safe_open', 'storage_open', 'green_bag_visible', 'bag_interaction', 'cup_to_mouth')
        frame = max(raw['frames'], key=lambda f: max((f['state_scores'].get(k) or 0) for k in keys))
        snapshots = evidence.frames(job.upload.path, [frame['timestamp_sec']], deadline_monotonic=deadline_monotonic)
        violations.append({
            'type': 'Возможное нарушение: сигнал видеоклассификатора',
            'timecode_sec': snapshots[0].timestamp_sec,
            'description': 'Модель отметила ролик как подозрительный. Показан исходный кадр для ручной проверки; '
                           'точный тип нарушения и момент события пока не подтверждены.',
            'evidence_frames': [snapshots[0].public()]
        })
    elif raw['prediction'] != 'no_violation':
        raise ValueError('Unknown prediction')
    public = {'job_id': job.job_id, 'status': 'done', 'verdict': raw['prediction'], 'violations': violations}
    diagnostics = {
        'schema_version': '1.0', 'job_id': job.job_id, 'public': public, 'stage': 'done',
        'processed_sec': job.upload.video.duration_sec, 'duration_sec': job.upload.video.duration_sec,
        'coverage': 'partial', 'unknown': ['Тип/границы события и нормативная применимость неизвестны.'],
        'unsupported': ['Проверенные по нормативам типы нарушений и точная локализация события.'],
        'limitations': [*LIMITATIONS, f"Оценка модели: {raw['score']:.6f}; фиксированный порог: {raw['threshold']:.6f}."],
        'versions': {'dataset': 'existing-development-36', 'annotations': 'assistant-review', 'split': 'grouped-family',
                     'rules': None, 'model': raw['model_sha256'], 'preprocessing': 'spatial-object-inputs-v2',
                     'taxonomy': 'experimental-video-verdict'},
        'timeline': None, 'media': media_links(job),
        'provenance': {'kind': 'original', 'source_id': job.job_id, 'sha256': job.upload.sha256}
    }
    validate_contract('job', public)
    validate_contract('diagnostics', diagnostics)
    return AnalysisBundle(public, diagnostics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    config = request['config']
    runtime = Path(config['runtime_root'])
    repo = LocalRepository(runtime/'jobs.sqlite3')
    job = repo.get(request['job_id'])
    if job is None:
        raise ValueError('Missing job')
    deadline = time.monotonic() + max(0, (job.deadline_at-datetime.now(timezone.utc)).total_seconds())
    model = predictor(config['bundle_root'], config['device'])
    raw = model.analyze(job.upload.path)
    evidence = EvidenceProvider()
    result = make_result(job, raw, evidence, deadline_monotonic=deadline)
    media = MediaService(repo, LocalStorage(runtime/'media', sync_directories=False))
    media.preview(job.job_id, deadline_monotonic=deadline)
    print(json.dumps(asdict(result), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
