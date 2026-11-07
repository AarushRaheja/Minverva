"""Static source locations for measured failures; no candidate code is executed."""
import json
import re
import subprocess
from pathlib import Path

from frontendslm.io import sha256

PARSER = Path(__file__).resolve().with_name('source-units.cjs')


def source_catalog(source: str) -> dict:
    process = subprocess.run(['node', str(PARSER)], input=source, text=True, capture_output=True,
                             check=True, timeout=15)
    catalog = json.loads(process.stdout)
    if catalog['source_sha256'] != sha256(source.encode()):
        raise ValueError('Parser source checksum mismatch')
    return catalog


def validate_generation_syntax(generation: dict) -> dict:
    """Reject malformed assembled TSX without executing it or discarding raw output."""
    if not generation.get('manifest'):
        return generation
    source = generation['manifest']['files']['src/App.tsx']
    catalog = source_catalog(source)
    result = generation | {'source_validation': {
        'source_sha256': catalog['source_sha256'], 'parser': catalog['parser'],
        'node_version': catalog['node_version'], 'diagnostics': catalog['diagnostics'],
        'syntax_valid': not catalog['diagnostics'], 'typecheck_performed': False,
    }}
    if catalog['diagnostics']:
        result['rejected_manifest'] = result['manifest']
        result['manifest'] = None
        result['error'] = 'Source syntax rejected before browser execution: ' + json.dumps(catalog['diagnostics'])
    return result


def localization_hints(catalog: dict, measured_evidence: dict) -> list[dict]:
    nodes = catalog['nodes']
    by_id = {n['id']: n for n in nodes}
    hints = []
    seen = set()
    for group in measured_evidence.get('measured_checks', []):
        if group['status'] != 'fail':
            continue
        details = group.get('details') or {}
        if group['id'] == 'interaction':
            for test in details.get('tests', []):
                for step in test.get('steps', []):
                    if step.get('passed') is not False or not step.get('test_id'):
                        continue
                    target = step['test_id'].removesuffix(':first')
                    matches = [n for n in nodes if any(n['literal_attributes'].get(k) == target for k in ('data-testid', 'id'))]
                    ids = {n['id'] for n in matches}
                    handlers = {h for n in matches for h in n['event_handlers']}
                    ids.update(n['id'] for n in nodes if handlers.intersection(n['declared_names']))
                    key = ('test_id', target)
                    if key not in seen:
                        seen.add(key)
                        hints.append({'measured_target': target, 'possible_unit_ids': sorted(ids),
                            'note': 'Literal data-testid or HTML id matches, plus named event handlers. An HTML id alone does not satisfy data-testid.'})
        if group['id'] == 'accessibility':
            for failure in details.get('failures', []):
                for finding in failure.get('nodes', []):
                    for selector in finding.get('target', []):
                        if not isinstance(selector, str) or ('selector', selector) in seen:
                            continue
                        matches = []
                        for n in nodes:
                            attrs = n['literal_attributes']
                            if ((re.fullmatch(r'#[\w-]+', selector) and attrs.get('id') == selector[1:]) or
                                (re.fullmatch(r'\.[\w-]+', selector) and selector[1:] in attrs.get('className', '').split())):
                                matches.append(n)
                            elif re.fullmatch(r'[a-z][\w-]*(?:\s*>\s*[a-z][\w-]*)*', selector):
                                chain = re.split(r'\s*>\s*', selector)
                                parent_tags = [by_id[i]['tag'] for i in n['ancestor_unit_ids']]
                                if n['tag'] == chain[-1] and (len(chain) == 1 or parent_tags[-len(chain)+1:] == chain[:-1]):
                                    matches.append(n)
                        ids = {n['id'] for n in matches}
                        ids.update(i for n in matches for i in n['ancestor_unit_ids'])
                        seen.add(('selector', selector))
                        hints.append({'measured_selector': selector, 'possible_unit_ids': sorted(ids),
                            'note': 'Static source hints, including ancestors that may supply inherited styles; unsupported dynamic selectors may have no match.'})
    return hints
