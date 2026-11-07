"""Bounded Architect → measured browser audit → Critic → repair loop on Modal."""
import argparse
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

import modal_app
from audit.cases import audit_case
from audit.scoring import audit_score
from audit.source_units import localization_hints, source_catalog, validate_generation_syntax
from frontendslm.evidence import compact_evidence
from frontendslm.inference import architect_decoding_parameters
from frontendslm.io import sha256, write_json
from frontendslm.lineage import read_verified_generation, source_generation
from frontendslm.repair import recover_repair_context


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--source-run')
    parser.add_argument('--source-round', type=int, choices=range(4), help='Select an explicit saved round from a repair run')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--max-revisions', type=int, default=2)
    parser.add_argument('--candidates', help='Optional comma-separated baseline/case subset for a diagnostic repair run')
    parser.add_argument('--design-run', help='Validated intent run to use before generation')
    parser.add_argument('--baselines', default='A0,A1')
    parser.add_argument('--repair-strategy', choices=['component', 'line', 'units'], default='component')
    parser.add_argument('--repair-decoding', choices=['greedy', 'qwen-recommended', 'thinking-recommended'])
    parser.add_argument('--architect-profile', choices=['instruct', 'thinking'], default='instruct')
    parser.add_argument('--prepare-models', action='store_true', help='Cache the selected pinned models on Modal before inference')
    parser.add_argument('--composition-example', action='store_true')
    args = parser.parse_args()
    args.repair_decoding = args.repair_decoding or ('thinking-recommended' if args.architect_profile == 'thinking' else 'greedy')
    lock_path = ROOT / 'configs' / ('models-thinking.lock.json' if args.architect_profile == 'thinking' else 'models.lock.json')
    model_lock = read(lock_path)
    architect_decoding_parameters(repairing=True, patching=args.repair_strategy != 'component',
        repair_decoding=args.repair_decoding, output_mode=model_lock['architect'].get('output_mode', 'component'))
    if args.repair_strategy != 'component' and args.repair_decoding != 'greedy':
        raise ValueError('Sampling profile is only supported for component repairs')
    if args.repair_strategy == 'units':
        source_catalog('export default function App() { return null; }')  # Parser dependency preflight only.
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', args.run_id):
        raise ValueError('Invalid run ID')
    if not 0 <= args.max_revisions <= 3 or not 0 <= args.offset < 50 or not 1 <= args.count <= 20:
        raise ValueError('Keep bounded revisions (0–3) and batch size (1–20)')
    directory = ROOT / 'artifacts' / args.run_id
    source = ROOT / 'artifacts' / args.source_run if args.source_run else None
    if args.source_round is not None and source is None:
        raise ValueError('A source round requires a source run')
    if source and (source.parent != ROOT / 'artifacts' or source == directory):
        raise ValueError('Source must be another direct run directory')
    originals = modal_app.read_cases(50)
    if source:
        previous = read(source / 'run.json')
        by_id = {c['id']: c for c in originals}
        selected = [by_id[i] for i in previous['case_ids']]
        baselines = previous['baselines']
    else:
        selected = originals[args.offset:args.offset + args.count]
        baselines = args.baselines.split(',')
        if not baselines or not set(baselines) <= {'A0', 'A1'}:
            raise ValueError('Expected A0,A1 baselines')
    cases = {c['id']: audit_case(c) for c in selected}
    if args.composition_example:
        for case in cases.values():
            case['composition_example'] = (ROOT / 'design/composition-example.tsx').read_text()
    candidate_filter = set(args.candidates.split(',')) if args.candidates else None
    if candidate_filter and not candidate_filter <= {f'{b}/{c}' for b in baselines for c in cases}:
        raise ValueError('Candidate filter names an unavailable case')
    source_inputs = {f'{b}/{c}': source_generation(source, b, c, args.source_round)
                     for b in baselines for c in cases if not candidate_filter or f'{b}/{c}' in candidate_filter} if source else {}
    if args.design_run:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', args.design_run):
            raise ValueError('Invalid design run ID')
        for case_id, case in cases.items():
            if candidate_filter and not any(f'{b}/{case_id}' in candidate_filter for b in baselines):
                continue
            intent = read(ROOT / 'artifacts' / args.design_run / case_id / 'intent.json')
            if not intent or not intent['schema_valid'] or intent['provenance_errors'] or intent['intent']['unresolved_descriptors']:
                raise ValueError(f'Design intent needs correction or clarification: {case_id}')
            case['design_intent'] = intent['intent']
    tracked = [*ROOT.glob('src/**/*.py'), *ROOT.glob('audit/*.*'), *ROOT.glob('sandbox/*.*'),
               *ROOT.glob('sandbox/src/*'), *ROOT.glob('design/*.*'), ROOT / 'modal_app.py', Path(__file__), ROOT / 'uv.lock', lock_path]
    hashes = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sorted(tracked) if p.is_file()}
    run = {'schema_version': '1.0', 'pipeline_version': '8.3', 'audit_version': '2.1', 'run_id': args.run_id,
           'source_run': args.source_run, 'case_ids': list(cases), 'baselines': baselines,
           'source_round': args.source_round, 'source_inputs': source_inputs,
           'model_lock': model_lock, 'architect_profile': args.architect_profile,
           'model_lock_file': str(lock_path.relative_to(ROOT)), 'gpu': 'L40S', 'source_sha256': hashes,
           'max_revisions': args.max_revisions, 'max_generation_attempts_per_round': 1,
           'training_performed': False, 'initial_cases_previously_generated': bool(source),
           'candidate_filter': sorted(candidate_filter) if candidate_filter else None,
           'design_run': args.design_run, 'design_intents': {k: v.get('design_intent') for k, v in cases.items()},
           'repair_strategy': args.repair_strategy,
           'repair_decoding': args.repair_decoding,
           'composition_example': args.composition_example,
           'acceptance': 'Complete functional audit and valid measured critic with effective accept verdict'}
    existing = read(directory / 'run.json')
    if existing:
        for key in ('source_sha256', 'model_lock', 'architect_profile', 'case_ids', 'max_revisions', 'source_run', 'source_round', 'source_inputs', 'candidate_filter', 'design_run', 'design_intents', 'baselines', 'repair_strategy', 'repair_decoding', 'composition_example'):
            if existing[key] != run[key]:
                raise ValueError(f'Resume settings/source changed: {key}')
    else:
        write_json(directory / 'run.json', run | {'started_at': datetime.now(UTC).isoformat()})
        write_json(directory / 'cases.json', list(cases.values()))
        for name in hashes:
            target = directory / 'pipeline-source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
    modal_app.render_image = modal_app.render_image.add_local_file(ROOT / 'audit/evaluate.mjs', '/work/evaluate.mjs', copy=True)
    records, history = {}, []
    with modal.enable_output(), modal_app.app.run():
        if args.prepare_models:
            write_json(directory / 'download.json', modal_app.download_models.remote(model_lock))
        for round_number in range(args.max_revisions + 1):
            round_dir = directory / f'round-{round_number}'
            remote_id = f'{args.run_id}/round-{round_number}'
            jobs = []
            for baseline in baselines:
                for case_id, case in cases.items():
                    key = f'{baseline}/{case_id}'
                    if candidate_filter and key not in candidate_filter:
                        continue
                    if records.get(key, {}).get('accepted'):
                        continue
                    job = case | {'repair_baseline': baseline, 'repair_strategy': args.repair_strategy,
                                  'repair_decoding': args.repair_decoding}
                    if round_number:
                        last = records[key]
                        last_dir = directory / last['artifact_path']
                        generation = read(last_dir / 'generation.json') or {}
                        evidence = read(last_dir / 'render/evidence.json') or {}
                        critique = read(last_dir / 'critique.json') or {}
                        earlier = []
                        if not generation.get('manifest'):
                            for previous in history:
                                if previous['candidate'] != key:
                                    continue
                                previous_dir = directory / previous['artifact_path']
                                previous_generation = read(previous_dir / 'generation.json') or {}
                                previous_source = (previous_generation.get('manifest') or {}).get('files', {}).get('src/App.tsx')
                                if previous_source is not None:
                                    earlier.append({'source': previous_source,
                                        'evidence': read(previous_dir / 'render/evidence.json') or {},
                                        'artifact_path': previous['artifact_path']})
                        previous_source, evidence, recovered_from = recover_repair_context(generation, evidence, earlier)
                        job['repair_context'] = {
                            'previous_source': previous_source, 'evidence_recovered_from': recovered_from,
                            'generation_error': generation.get('error'), 'measured_evidence': compact_evidence(evidence, case['tests']),
                            'critic': critique.get('critique'), 'critic_validation': critique.get('measurement_validation'),
                            'audit_score': audit_score(evidence) if recovered_from else last['audit'], 'revision_number': round_number,
                        }
                        if args.repair_strategy == 'units':
                            catalog = source_catalog(previous_source)
                            job['repair_context']['source_catalog'] = catalog
                            job['repair_context']['source_hints'] = localization_hints(catalog, job['repair_context']['measured_evidence'])
                            if catalog['diagnostics']:
                                job['repair_context']['generation_error'] = json.dumps({'previous_error': generation.get('error'),
                                    'source_parse_errors': catalog['diagnostics']})
                    jobs.append(job)
            if not jobs:
                break
            write_json(round_dir / 'jobs.json', jobs)
            if round_number == 0 and source:
                for job in jobs:
                    baseline, case_id = job['repair_baseline'], job['id']
                    write_json(round_dir / baseline / case_id / 'generation.json',
                               read_verified_generation(source, source_inputs[f'{baseline}/{case_id}']))
            else:
                generated = modal_app.architect_batch.remote(jobs, baselines, model_lock, remote_id)
                for row in generated:
                    if args.repair_strategy == 'units':
                        row = validate_generation_syntax(row)
                    write_json(round_dir / row['baseline'] / row['case_id'] / 'generation.json', row)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                for job in jobs:
                    baseline, case_id = job['repair_baseline'], job['id']
                    path = round_dir / baseline / case_id
                    generation = read(path / 'generation.json')
                    write_json(path / 'case.json', cases[case_id])
                    if not generation or not generation.get('manifest'):
                        continue
                    for name, content in generation['manifest']['files'].items():
                        target = path / 'source' / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(content)
                    if not (path / 'render/evidence.json').exists():
                        futures[pool.submit(modal_app.render_case, cases[case_id], generation['manifest'], path / 'render')] = f'{baseline}/{case_id}'
                for future in as_completed(futures):
                    evidence = future.result()
                    print(json.dumps({'stage': 'audit', 'round': round_number, 'candidate': futures[future], **audit_score(evidence)}), flush=True)
            with modal_app.results.batch_upload(force=True) as batch:
                batch.put_directory(round_dir, f'/{remote_id}')
            measured_candidates = sum((round_dir / j['repair_baseline'] / j['id'] / 'render/evidence.json').exists()
                                      for j in jobs)
            write_json(round_dir / 'critic-phase.json', {'measured_candidates': measured_candidates,
                'requested': measured_candidates > 0,
                'reason': 'Evaluate measured results' if measured_candidates else 'No measured candidates; all generations rejected'})
            if measured_candidates:
                critiques = modal_app.critic_batch.remote(list(cases.values()), baselines, model_lock, remote_id)
            else:
                critiques = []
                print(json.dumps({'stage': 'critic_skipped', 'round': round_number, 'reason': 'No measured candidates'}), flush=True)
            for critique in critiques:
                write_json(round_dir / critique['baseline'] / critique['case_id'] / 'critique.json', critique)
            round_rows = []
            for job in jobs:
                baseline, case_id = job['repair_baseline'], job['id']
                path = round_dir / baseline / case_id
                evidence = read(path / 'render/evidence.json') or {}
                critique = read(path / 'critique.json') or {}
                audit = audit_score(evidence)
                critic_valid = bool(critique.get('schema_valid') and (critique.get('measurement_validation') or {}).get('valid'))
                row = {'candidate': f'{baseline}/{case_id}', 'round': round_number, 'audit': audit,
                       'critic_valid': critic_valid, 'effective_verdict': critique.get('effective_verdict'),
                       'accepted': bool(audit['audit_pass'] and critic_valid and critique.get('effective_verdict') == 'accept'),
                       'artifact_path': str(path.relative_to(directory))}
                records[row['candidate']] = row
                round_rows.append(row)
            history.extend(round_rows)
            write_json(round_dir / 'summary.json', {'rows': round_rows})
            payload = {'run_id': args.run_id, 'total': len(candidate_filter) if candidate_filter else len(cases) * len(baselines),
                       'accepted': sum(r['accepted'] for r in records.values()),
                       'first_attempt_accepted': sum(r['accepted'] for r in history if r['round'] == 0),
                       'revision_attempts': sum(r['round'] > 0 for r in history),
                       'latest': list(records.values()), 'history': history, 'human_visual_quality': 'unmeasured'}
            write_json(directory / 'summary.json', payload)
            print(json.dumps({'round': round_number, 'accepted': payload['accepted'], 'total': payload['total']}), flush=True)
        with modal_app.results.batch_upload(force=True) as batch:
            batch.put_directory(directory, f'/{args.run_id}')
    print(f"Completed bounded pipeline: {payload['accepted']}/{payload['total']} accepted. Remaining candidates stay rejected.")


if __name__ == '__main__':
    main()
