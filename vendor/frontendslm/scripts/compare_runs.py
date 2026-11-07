"""Compare paired first-attempt baseline runs without changing either run's observations."""
import argparse
import json
from pathlib import Path

from frontendslm.evidence import compact_evidence
from frontendslm.io import parse_json_response, write_json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def describe(directory):
    run = read(directory / 'run.json')
    summary = read(directory / 'summary.json')
    generations = [read(p) for p in sorted(directory.glob('A*/*/generation.json'))]
    critiques = [read(p) for p in sorted(directory.glob('A*/*/critique.json'))]
    failures = []
    for path in sorted(directory.glob('A*/*/critique.json')):
        critique = read(path)
        evidence = read(path.parent / 'render/evidence.json')
        compact = compact_evidence(evidence)
        failed = [c['id'] for c in compact['measured_checks'] if c['status'] == 'fail']
        try:
            raw = parse_json_response(critique['raw'])
        except (ValueError, TypeError):
            raw = {}
        if failed:
            failures.append({'candidate': str(path.parent.relative_to(directory)), 'failed_groups': failed,
                             'raw_verdict': raw.get('verdict'),
                             'measurement_validation': critique.get('measurement_validation')})
    return {'run_id': run['run_id'], 'attempts': len(summary['rows']), 'summary': summary['summary'],
            'critic_attempts': len(critiques), 'critic_schema_valid': sum(c['schema_valid'] for c in critiques),
            'critic_measured_valid': sum(bool((c.get('measurement_validation') or {}).get('valid')) for c in critiques),
            'truncations': sum(g['truncated'] for g in generations),
            'architect_output_tokens': sum(g['output_tokens'] for g in generations),
            'architect_seconds': sum(g['seconds'] for g in generations),
            'critic_seconds': sum(c['seconds'] for c in critiques),
            'measured_failed_candidates_seen_by_critic': failures,
            'raw_false_accepts_on_measured_failures': sum(f['raw_verdict'] == 'accept' for f in failures)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('before')
    parser.add_argument('after')
    args = parser.parse_args()
    before, after = [ROOT / 'artifacts' / name for name in (args.before, args.after)]
    if any(p.parent != ROOT / 'artifacts' for p in (before, after)) or before == after:
        raise ValueError('Expected two different direct run directories')
    old, new = [read(p / 'run.json') for p in (before, after)]
    for key in ('case_ids', 'baselines', 'model_lock', 'benchmark_manifest', 'gpu', 'max_generation_attempts', 'max_revisions'):
        if old[key] != new[key]:
            raise ValueError(f'Runs are not paired on {key}')
    harness_files = [p for p in old['source_sha256'] if p.startswith('sandbox/')]
    if any(old['source_sha256'][p] != new['source_sha256'][p] for p in harness_files):
        raise ValueError('Browser harness or build template changed')
    old_rows, new_rows = [read(p / 'summary.json')['rows'] for p in (before, after)]
    old_by_id = {(r['baseline'], r['case_id']): r for r in old_rows}
    metrics = ['source_valid', 'build_pass', 'interaction_pass', 'no_overflow', 'no_serious_a11y', 'release_eligible']
    pairs = []
    for row in new_rows:
        previous = old_by_id[(row['baseline'], row['case_id'])]
        pairs.append({'candidate': f"{row['baseline']}/{row['case_id']}",
                      **{m: {'before': previous[m], 'after': row[m]} for m in metrics}})
    before_stats, after_stats = describe(before), describe(after)
    payload = {'before': before_stats, 'after': after_stats, 'paired_rows': pairs,
               'invariants_verified': ['case order', 'models and revisions', 'benchmark hash', 'A0/A1 conditions',
                                       'L40S', 'single attempt', 'no revisions', 'unchanged browser harness/build template'],
               'changed': ['raw component output and host-supplied CSS', 'shared code contract',
                           'Architect repetition_penalty 1.0 → 1.05', 'Critic XGrammar schema-constrained decoding',
                           'Critic measured-check ledger including after-interaction evidence',
                           'independent fail-closed measurement/reference validation'],
               'limitations': 'Same small evaluation set reused to assess engineering fixes; not a fresh holdout, model training gain, or human quality assessment.'}
    write_json(after / 'comparison.json', payload)
    lines = [f"# Baseline comparison: {args.before} → {args.after}", '',
             'Same ten briefs, A0/A1 conditions, pinned model revisions, seed 42, token limits, L40S and browser harness. One generation per candidate; no repair retries or training.', '',
             '| Metric | Before | After |', '|---|---:|---:|']
    for metric in metrics:
        lines.append(f"| {metric.replace('_', ' ')} | {sum(r[metric] for r in old_rows)}/20 | {sum(r[metric] for r in new_rows)}/20 |")
    lines += [f"| Critic schema validity (attempted only) | {before_stats['critic_schema_valid']}/{before_stats['critic_attempts']} | {after_stats['critic_schema_valid']}/{after_stats['critic_attempts']} |",
              f"| Truncated generations | {before_stats['truncations']} | {after_stats['truncations']} |",
              f"| Raw critic false acceptances on measured failures | {before_stats['raw_false_accepts_on_measured_failures']} | {after_stats['raw_false_accepts_on_measured_failures']} |", '',
              '## Changes and interpretation', '', *[f'- {c}' for c in payload['changed']], '', payload['limitations'], '',
              'Source-manifest validity is protocol-specific: v1 required model-generated JSON and CSS; v2 validates a generated component assembled with fixed CSS. Build and browser pass rates are directly comparable on the unchanged harness.', '',
              'Critic schema correctness is now constrained at decoding, not learned. Raw model issues/verdicts remain separate from the independent gate. Measurement validation checks coverage and references; it does not prove every sentence or visual claim true.', '',
              '## A0 and A1', '', '| Condition | Builds before → after | All gates before → after |', '|---|---|---|']
    for b in new['baselines']:
        old_b, new_b = before_stats['summary'][b], after_stats['summary'][b]
        lines.append(f"| {b} | {old_b['build_pass']['passed']}/10 → {new_b['build_pass']['passed']}/10 | {old_b['release_eligible']['passed']}/10 → {new_b['release_eligible']['passed']}/10 |")
    lines += ['', '## Paired outcomes', '', '| Candidate | Build before → after | All gates before → after |', '|---|---|---|']
    for pair in pairs:
        state = lambda m, pair=pair: f"{'pass' if pair[m]['before'] else 'fail'} → {'pass' if pair[m]['after'] else 'fail'}"
        lines.append(f"| {pair['candidate']} | {state('build_pass')} | {state('release_eligible')} |")
    lines += ['', '## Inference usage', '',
              f"Architect output tokens: {before_stats['architect_output_tokens']:,} → {after_stats['architect_output_tokens']:,}.", '',
              f"Measured Architect generation time: {before_stats['architect_seconds']/60:.1f} → {after_stats['architect_seconds']/60:.1f} minutes; Critic: {before_stats['critic_seconds']/60:.1f} → {after_stats['critic_seconds']/60:.1f} minutes.", '',
              'These timings exclude startup, image building, model loading and idle time. They are not billed GPU duration or dollar costs.', '',
              'See comparison.json for every measured-failure verdict, and review.html for screenshots and source exports. Human visual preference and critique grounding remain unmeasured.']
    (after / 'comparison.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'before': before_stats, 'after': after_stats}, indent=2))


if __name__ == '__main__':
    main()
