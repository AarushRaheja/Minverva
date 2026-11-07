from copy import deepcopy
from itertools import pairwise

import pytest

from audit.source_units import localization_hints, source_catalog, validate_generation_syntax
from frontendslm.generation import component_manifest
from frontendslm.repair import UnitPatch, apply_unit_patch, recover_repair_context, unit_patch_schema

SOURCE = '''import React, {useState} from 'react';
const App = () => {
  const [count, setCount] = useState(1);
  const increase = () => { setCount(count + 1); };
  return <main><h1>🌿 Café</h1>
    <button id="counter-plus" onClick={increase}>+</button>
    <output>{count}</output>
    <footer className="text-gray-500"><p>Local only</p></footer>
  </main>;
};
export default App;
'''


def test_source_units_use_exact_utf8_ranges_and_preserve_unedited_code():
    catalog = source_catalog(SOURCE)
    assert not catalog['diagnostics']
    nodes = catalog['nodes']
    assert all(SOURCE.encode()[n['start_byte']:n['end_byte']].decode() == n['text'] for n in nodes)
    assert all(a['end_byte'] <= b['start_byte'] for a, b in pairwise(nodes))
    button = next(n for n in nodes if n['literal_attributes'].get('id') == 'counter-plus')
    replacement = button['text'].replace('id="counter-plus"', 'id="counter-plus" data-testid="counter-plus"')
    patch = UnitPatch(base_source_sha256=catalog['source_sha256'], edits=[{
        'node_id': button['id'], 'reason': 'Expose the required test target', 'replacement': replacement}])
    fixed = apply_unit_patch(SOURCE, patch, catalog).files['src/App.tsx']
    assert fixed == SOURCE.replace(button['text'], replacement)
    assert not source_catalog(fixed)['diagnostics']
    schema = unit_patch_schema(catalog)
    assert schema['properties']['base_source_sha256']['const'] == catalog['source_sha256']
    assert schema['$defs']['UnitEdit']['properties']['node_id']['enum'] == [n['id'] for n in nodes]


def test_stale_noop_unknown_and_overlapping_unit_edits_are_rejected():
    catalog = source_catalog(SOURCE)
    node = catalog['nodes'][0]
    edit = {'node_id': node['id'], 'reason': 'A test replacement', 'replacement': node['text'] + '\n'}
    for checksum, edits in [('0' * 64, [edit]), (catalog['source_sha256'], [edit | {'node_id': 'unknown'}]),
                            (catalog['source_sha256'], [edit | {'replacement': node['text']}]),
                            (catalog['source_sha256'], [edit, edit])]:
        with pytest.raises(ValueError):
            apply_unit_patch(SOURCE, UnitPatch(base_source_sha256=checksum, edits=edits), catalog)
    stale = deepcopy(catalog)
    stale['nodes'][0]['start_byte'] += 1
    with pytest.raises(ValueError, match='offsets or text'):
        apply_unit_patch(SOURCE, UnitPatch(base_source_sha256=catalog['source_sha256'], edits=[edit]), stale)


def test_localization_maps_missing_data_id_to_html_id_handler_and_inherited_style():
    catalog = source_catalog(SOURCE)
    evidence = {'measured_checks': [
        {'id': 'interaction', 'status': 'fail', 'details': {'tests': [{'steps': [
            {'passed': False, 'test_id': 'counter-plus'}]}]}},
        {'id': 'accessibility', 'status': 'fail', 'details': {'failures': [{'nodes': [
            {'target': ['footer > p']}]}]}}]}
    hints = localization_hints(catalog, evidence)
    by_id = {n['id']: n for n in catalog['nodes']}
    targets = [by_id[i] for i in hints[0]['possible_unit_ids']]
    assert any(n['literal_attributes'].get('id') == 'counter-plus' for n in targets)
    assert any('increase' in n['declared_names'] for n in targets)
    targets = [by_id[i] for i in hints[1]['possible_unit_ids']]
    assert any(n['tag'] == 'footer' for n in targets) and any(n['tag'] == 'p' for n in targets)


def test_parser_does_not_execute_source_and_rejects_syntax_errors_for_unit_patches():
    assert not source_catalog("throw new Error('must not execute');\n" + SOURCE)['diagnostics']
    broken = source_catalog('export default function App() { return <button; }')
    assert broken['diagnostics'] and not broken['nodes']
    with pytest.raises(ValueError):
        unit_patch_schema(broken)


def test_invalid_patch_retains_measurements_only_for_its_exact_base_source():
    previous = {'source': SOURCE, 'evidence': {'tests': [{'passed': False}]}, 'artifact_path': 'round-0/A1/example'}
    failed_patch = {'manifest': None, 'repair_base_source': SOURCE, 'raw': 'invalid patch'}
    source, evidence, path = recover_repair_context(failed_patch, {}, [previous])
    assert source == SOURCE and evidence == previous['evidence'] and path == previous['artifact_path']
    assert recover_repair_context(failed_patch | {'repair_base_source': SOURCE + ' '}, {}, [previous])[1:] == ({}, None)
    current = {'manifest': {'files': {'src/App.tsx': SOURCE}}}
    assert recover_repair_context(current, {'new': True}, [previous])[1:] == ({'new': True}, None)


def test_complete_element_edits_preserve_nested_content_without_duplicate_closings():
    source = SOURCE.replace('+</button>', '<span>+</span><svg><path d="M0 0" /></svg></button>')
    catalog = source_catalog(source)
    button = next(n for n in catalog['nodes'] if n['tag'] == 'button')
    assert button['kind'] == 'JsxElement' and button['text'].endswith('</button>')
    assert 'including children and closing tag' in button['replacement_scope']
    replacement = button['text'].replace('id="counter-plus"', 'id="counter-plus" className="min-w-10"')
    patch = UnitPatch(base_source_sha256=catalog['source_sha256'], edits=[{
        'node_id': button['id'], 'reason': 'Increase the target size', 'replacement': replacement}])
    revised = apply_unit_patch(source, patch, catalog).files['src/App.tsx']
    assert revised == source.replace(button['text'], replacement)
    assert revised.count('</button>') == 1 and not source_catalog(revised)['diagnostics']
    assert all(a['end_byte'] <= b['start_byte'] for a, b in pairwise(catalog['nodes']))


def test_syntax_rejection_preserves_raw_attempt_and_reuses_only_base_measurements():
    malformed = SOURCE.replace('<output>{count}</output>', '<output>{count}</output></output>')
    attempt = {'manifest': component_manifest(malformed).model_dump(), 'raw': 'model patch JSON',
               'repair_base_source': SOURCE, 'error': None}
    rejected = validate_generation_syntax(attempt)
    assert rejected['manifest'] is None and rejected['source_validation']['diagnostics']
    assert rejected['rejected_manifest'] == attempt['manifest']
    assert rejected['raw'] == attempt['raw'] and attempt['manifest'] is not None
    old = {'source': SOURCE, 'evidence': {'tests': ['measured']}, 'artifact_path': 'round-0/A0/example'}
    assert recover_repair_context(rejected, {}, [old]) == (SOURCE, old['evidence'], old['artifact_path'])
    valid = validate_generation_syntax(attempt | {'manifest': component_manifest(SOURCE).model_dump()})
    assert valid['source_validation']['syntax_valid']
    assert valid['source_validation']['typecheck_performed'] is False
    assert valid['manifest'] is not None
