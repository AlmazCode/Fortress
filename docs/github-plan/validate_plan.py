"""Check the GitHub migration without contacting Aster, GitHub or any runtime service."""
from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import re
import sys

DEVELOPERS = {1: 'DEV1_BACKEND.md', 2: 'DEV2_FRONTEND.md', 3: 'DEV3_ML_DATA.md', 4: 'DEV4_RULES_INFRA.md'}


def check(root: Path, refresh: bool = False) -> dict:
    doc = root / 'docs/github-plan'
    load = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    plan = load(doc / 'plan.json')
    archive = load(doc / 'archive/plan.aster.json')
    provenance = load(doc / 'PROVENANCE.json')
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    tasks = plan['tasks']
    by_id = {task['id']: task for task in tasks}
    old = {task['id']: task for task in archive['tasks']}
    require(len(tasks) == len(by_id) == 36, 'Expected 36 unique tasks')
    require(set(by_id) == set(old), 'Task IDs differ from original plan')
    require(plan['owners'] == archive['owners'], 'Owner assignments changed')
    require(plan['repository'] == archive['repository'], 'Repository or baseline changed')
    require(plan['executionMode'] == 'github-git', 'Execution mode must be github-git')
    require(plan['migration']['asterRequired'] is False, 'Aster must not be required')
    require(plan['futureStage'] == archive['futureStage'], 'Deferred training restrictions changed')
    require(Counter(t['owner'] for t in tasks) == {1:9, 2:6, 3:12, 4:9}, 'Developer task counts changed')
    changes = {(c['task'], c['acceptanceIndex']): c for c in plan['migration']['coordinationChanges']}
    require(set(changes) == {('E', 6), ('Z', 0)}, 'Unexpected acceptance policy substitutions')
    ancestors = {}
    visiting = set()

    def walk(key):
        if key in ancestors:
            return ancestors[key]
        if key in visiting:
            errors.append(f'Dependency cycle at {key}')
            return set()
        visiting.add(key)
        parents = set()
        for parent in by_id[key].get('depends', []):
            if parent not in by_id:
                errors.append(f'{key}: missing dependency {parent}')
                continue
            parents.add(parent)
            parents.update(walk(parent))
        visiting.remove(key)
        ancestors[key] = parents
        return parents

    for key in by_id:
        walk(key)

    coverage = {'files':0, 'acceptance':0, 'unchangedAcceptance':0}
    all_plan_text = (doc / 'PLAN.md').read_text(encoding='utf-8')
    for task in tasks:
        key = task['id']
        if key not in old:
            continue
        original = old[key]
        require(task['owner'] == plan['owners'][key], f'{key}: inconsistent owner')
        for field in ('title', 'files', 'depends', 'kind', 'phase'):
            require(task.get(field, []) == original.get(field, []), f'{key}: {field} changed')
        require(len(task['acceptance']) == len(original['acceptance']), f'{key}: acceptance count changed')
        for index, (actual, previous) in enumerate(zip(task['acceptance'], original['acceptance'])):
            change = changes.get((key, index))
            if change:
                require(actual == change['after'] and previous == change['before'], f'{key}: undocumented acceptance change')
                if key == 'E':
                    require(actual == previous.replace('manual review сохраняется.', 'Проверка точного commit и отчёта выполняется по GitHub-процессу.'), 'E: product criteria changed')
                if key == 'Z':
                    require(actual == previous.replace('приняты по manual policy,', 'приняты после фактической проверки точных commits и критериев по GitHub-процессу,'), 'Z: product criteria changed')
            else:
                require(actual == previous, f'{key}: product acceptance {index} changed')
                coverage['unchangedAcceptance'] += 1
        role_text = (doc / DEVELOPERS[task['owner']]).read_text(encoding='utf-8')
        for text, name in [(role_text, DEVELOPERS[task['owner']]), (all_plan_text, 'PLAN.md')]:
            pattern = rf'^## {re.escape(key)} — .+?$(.*?)(?=^## |\Z)'
            match = re.search(pattern, text, re.M | re.S)
            require(match is not None, f'{name}: missing task {key}')
            if match:
                section = match.group(1)
                for path in task['files']:
                    require(f'`{path}`' in section, f'{name}/{key}: missing file {path}')
                for criterion in task['acceptance']:
                    require(criterion in section, f'{name}/{key}: missing criterion')
        require(task['files'] and task['acceptance'] and task['outcomes'], f'{key}: incomplete definition')
        require(len(task['files']) == len(set(task['files'])), f'{key}: repeated file')
        for path in task['files']:
            parsed = PurePosixPath(path)
            require(not parsed.is_absolute() and '..' not in parsed.parts and '\\' not in path, f'{key}: invalid file path {path}')
        require('Сейчас только план' not in task['description'], f'{key}: obsolete planning-only text')
        require('manual policy' not in task['description'], f'{key}: obsolete review policy')
        coverage['files'] += len(task['files'])
        coverage['acceptance'] += len(task['acceptance'])

    edges = sum(len(t.get('depends', [])) for t in tasks)
    require(edges == 48, 'Expected 48 direct dependencies')
    require(sorted(t['id'] for t in tasks if not t.get('depends')) == ['K', 'O1'], 'Wrong root tasks')
    redundant = []
    overlaps = []
    for task in tasks:
        for dependency in task.get('depends', []):
            for other in task.get('depends', []):
                if other != dependency and dependency in ancestors.get(other, set()):
                    redundant.append([task['id'], dependency])
    for index, first in enumerate(tasks):
        for second in tasks[index+1:]:
            a, b = first['id'], second['id']
            if first['owner'] == second['owner'] or a in ancestors[b] or b in ancestors[a]:
                continue
            common = sorted(set(first['files']) & set(second['files']))
            if common:
                overlaps.append({'tasks':[a,b], 'files':common})
    require(not redundant, f'Redundant edges: {redundant}')
    require(not overlaps, f'Concurrent cross-developer file overlaps: {overlaps}')

    require(len(provenance['personalBriefs']) == 4, 'Four human briefs must be compared')
    for n, filename in DEVELOPERS.items():
        text = (doc / filename).read_text(encoding='utf-8')
        require('проект перешёл с Aster на обычный Git/GitHub' in text, f'{filename}: migration notice missing')
        require('Aster MCP' in text and 'больше не используются' in text, f'{filename}: Aster retirement missing')
        headings = set(re.findall(r'^## ([A-Z]+[0-9]?) — ', text, re.M))
        expected = {t['id'] for t in tasks if t['owner'] == n}
        require(headings == expected, f'{filename}: task scope mismatch')
        status = (doc / f'status/DEV-{n}.md').read_text(encoding='utf-8')
        # Ownership is declared in the Task/State table. Review and dependency
        # tables later in the journal may legitimately reference other roles.
        table = re.search(r'^\| Task \| State \|[^\n]*\n((?:\|[^\n]*(?:\n|$))+)', status, re.M)
        declared = [] if table is None else re.findall(r'^\| ([A-Z]+[0-9]?) \|', table.group(1), re.M)
        require(set(declared) == expected and len(declared) == len(expected), f'DEV-{n} journal task scope mismatch')
        item = next((x for x in provenance['personalBriefs'] if x['developer'] == n), {})
        require(item.get('matchingTasks') == len(expected) and item.get('matchingCopies') == 2 and item.get('reviewInstruction') == 'automatic-all', f'Developer {n}: brief provenance incomplete')

    link_count = 0
    active_markdown = [root/'AGENTS.md', root/'README.md'] + list(doc.glob('*.md')) + list((doc/'status').glob('*.md'))
    for file in active_markdown:
        text = file.read_text(encoding='utf-8')
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
            if '://' in target or target.startswith('#'):
                continue
            local = (file.parent / target.split('#')[0]).resolve()
            generated_audit = refresh and local == (doc/'AUDIT.json').resolve()
            require(local.is_relative_to(root.resolve()) and (local.exists() or generated_audit), f'{file.name}: broken link {target}')
            link_count += 1

    report = {
        'status':'passed' if not errors else 'failed',
        'scope':'Documentation, task graph, ownership, preserved product criteria and local links only; no application, Docker, GPU, HTTPS or ML runtime verified.',
        'tasks':len(tasks), 'edges':edges, 'roots':['K','O1'],
        'perDeveloper':{str(k):v for k,v in sorted(Counter(t['owner'] for t in tasks).items())},
        'acyclic':not any('cycle' in e for e in errors), 'redundantEdges':redundant,
        'concurrentCrossDeveloperFileOverlaps':overlaps, 'coverage':coverage,
        'coordinationOnlyAcceptanceSubstitutions':len(changes), 'localMarkdownLinks':link_count,
        'matchedHumanBriefs':4, 'matchedHumanBriefCopies':8,
        'implementationStatusesReconciled':False, 'errors':errors,
    }
    if refresh and not errors:
        (doc/'AUDIT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
        paths = [root/'AGENTS.md', root/'README.md'] + [p for p in doc.rglob('*') if p.is_file() and p.name != 'manifest.json' and '__pycache__' not in p.parts]
        manifest = {
            'version':2, 'coordination':'github-git', 'sourcePlanCommit':plan['migration']['sourcePlanCommit'],
            'tasks':36, 'edges':48, 'implementationStatusesReconciled':False,
            'hashNormalization':'UTF-8 file bytes with CRLF normalized to LF',
            'files':{str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sorted(paths)},
        }
        (doc/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n', encoding='utf-8', newline='\n')
    elif not refresh:
        manifest = load(doc/'manifest.json')
        require(manifest['coordination'] == 'github-git', 'Manifest execution mode mismatch')
        for relative, expected_hash in manifest['files'].items():
            path = root / relative
            require(path.exists() and hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == expected_hash, f'Manifest mismatch: {relative}')
        previous = load(doc/'AUDIT.json')
        require(previous == report, 'Saved audit differs; rerun --refresh after intentional changes')
        report['status'] = 'passed' if not errors else 'failed'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Refresh audit and hashes after deliberate documentation changes')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        result = check(args.root, args.refresh)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status':'failed', 'errors':[str(exc)]}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
