"""Package accepted candidates and clearly separate first attempts from bounded repair outcomes."""
import argparse
import html
import json
import zipfile
from pathlib import Path

from frontendslm.io import sha256, write_json
from frontendslm.schemas import SourceManifest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_ids', nargs='+')
    parser.add_argument('--output', default='reliability-review')
    args = parser.parse_args()
    output = ROOT / 'artifacts' / args.output
    if output.parent != ROOT / 'artifacts':
        raise ValueError('Use a direct artifact folder')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'exports').mkdir(exist_ok=True)
    sections, reports, all_candidates = [], [], []
    reused_briefs = set(read(ROOT / 'artifacts/pilot-baseline-v2/run.json')['case_ids'])
    e = html.escape
    for run_id in args.run_ids:
        directory = ROOT / 'artifacts' / run_id
        if directory.parent != ROOT / 'artifacts':
            raise ValueError('Use direct run directories')
        run, summary = read(directory / 'run.json'), read(directory / 'summary.json')
        findings = read(directory / 'review-findings.json') if (directory / 'review-findings.json').exists() else []
        cases = {c['id']: c for c in read(directory / 'cases.json')}
        final_tests = final_states = critic_calls = schema_valid = measured_valid = 0
        generation_tokens = generation_seconds = critic_seconds = 0
        cards = []
        for event in summary['history']:
            path = directory / event['artifact_path']
            generation = read(path / 'generation.json')
            if not (event['round'] == 0 and run.get('source_run')):
                generation_tokens += generation['output_tokens']
                generation_seconds += generation['seconds']
            critic_path = path / 'critique.json'
            if critic_path.exists():
                critique = read(critic_path)
                critic_calls += 1
                schema_valid += bool(critique['schema_valid'])
                measured_valid += bool((critique.get('measurement_validation') or {}).get('valid'))
                critic_seconds += critique['seconds']
        for row in summary['latest']:
            baseline, case_id = row['candidate'].split('/')
            path = directory / row['artifact_path']
            generation = read(path / 'generation.json')
            evidence = read(path / 'render/evidence.json') if (path / 'render/evidence.json').exists() else {}
            final_tests += len(evidence.get('tests', []))
            final_states += row['audit'].get('intermediate_states', 0)
            relative = f'../{run_id}/{row["artifact_path"]}'
            archive = None
            candidate_findings = [f for f in findings if f['candidate'] == row['candidate']]
            export_blocked = any(f.get('block_export') for f in candidate_findings)
            if row['accepted'] and not export_blocked:
                manifest = SourceManifest.model_validate(generation['manifest'])
                archive = f'{run_id}-{baseline}-{case_id}.zip'
                with zipfile.ZipFile(output / 'exports' / archive, 'w', zipfile.ZIP_DEFLATED) as z:
                    for template in (ROOT / 'sandbox').rglob('*'):
                        name = template.relative_to(ROOT / 'sandbox')
                        if template.is_file() and not set(name.parts) & {'node_modules', 'dist'} and str(name) != 'evaluate.mjs' and str(name) not in manifest.files:
                            z.write(template, str(name))
                    for name, content in manifest.files.items():
                        z.writestr(name, content)
                    z.writestr('specification.json', json.dumps(cases[case_id]['spec'], indent=2))
                    z.writestr('acceptance-tests.json', json.dumps(cases[case_id]['tests'], indent=2))
                    z.writestr('validation.json', json.dumps(row, indent=2))
                    z.writestr('README.txt', 'Generated local demonstration frontend, validated in isolated Modal sandboxes.\nUse npm ci, npm run build, npm run preview in an isolated environment.\nNo real backend, payment or authentication integration is provided.\nValidation covers the saved brief and measured tests; visual preference and universal correctness are unmeasured.\n')
            preview = ''
            for view in ('desktop', 'mobile'):
                if view in evidence.get('screenshots', {}):
                    preview += f'<a href="{relative}/render/{view}.png"><img loading="lazy" src="{relative}/render/{view}.png" alt="{e(row["candidate"])} {view}"></a>'
            failures = ', '.join(k for k, value in row['audit'].items() if value is False)
            details = f'Passed measured gates after {row["round"]} repair round(s)' if row['accepted'] else f'Rejected: {e(failures)}'
            for finding in candidate_findings:
                details += '<br><strong>Review finding:</strong> ' + e(finding['description'])
            if export_blocked:
                details += '<br>Source export withheld pending correction. Original measured result is preserved.'
            if not generation.get('manifest'):
                details = 'Rejected before browser execution: ' + e(generation.get('error') or 'No valid source manifest')
            link_items = [f'<a href="{relative}/generation.json">Generation</a>']
            if (path / 'render/evidence.json').exists():
                link_items.append(f'<a href="{relative}/render/evidence.json">Measurements</a>')
            if (path / 'critique.json').exists():
                link_items.append(f'<a href="{relative}/critique.json">Critic</a>')
            links = ' · '.join(link_items)
            if archive:
                links += f' · <a href="exports/{archive}">Download source</a>'
            cards.append(f'<article><h3>{e(row["candidate"])}</h3><p>{e(cases[case_id]["spec"]["user_goal"])}</p><p class="{"pass" if row["accepted"] else "fail"}">{details}</p><div class="previews">{preview}</div><p>{links}</p></article>')
            all_candidates.append({'run_id': run_id, **row, 'source_export': archive,
                                   'review_findings': candidate_findings, 'export_blocked': export_blocked})
        mode = 'regression with reused initial sources' if run.get('source_run') else (
            'development on reused briefs' if reused_briefs & set(run['case_ids']) else 'prospective generation')
        report = {'run_id': run_id, 'mode': mode,
                  'total': summary['total'], 'accepted': summary['accepted'], 'first_attempt_accepted': summary['first_attempt_accepted'],
                  'revision_attempts': summary['revision_attempts'], 'maximum_repairs_per_candidate': run['max_revisions'],
                  'final_interaction_tests': final_tests, 'final_intermediate_state_scans': final_states,
                  'critic_calls': critic_calls, 'critic_schema_valid': schema_valid, 'critic_measured_valid': measured_valid,
                  'new_generation_output_tokens': generation_tokens, 'new_generation_seconds': generation_seconds,
                  'critic_seconds': critic_seconds, 'pipeline_source_sha256': run['source_sha256']}
        reports.append(report)
        sections.append(f'<section><h2>{e(run_id)}</h2><p>{e(report["mode"])} · {summary["first_attempt_accepted"]}/{summary["total"]} passed initially · {summary["accepted"]}/{summary["total"]} after bounded repairs · {summary["revision_attempts"]} revision attempts</p><div class="grid">{"".join(cards)}</div></section>')
    total, accepted = sum(r['total'] for r in reports), sum(r['accepted'] for r in reports)
    blocked = sum(c['export_blocked'] for c in all_candidates)
    write_json(output / 'summary.json', {'accepted': accepted, 'total': total, 'runs': reports, 'candidates': all_candidates,
        'exports_withheld_for_review_findings': blocked,
        'limitations': ['Results are limited to these authored local frontend briefs and tests.',
                        'Runs can reuse briefs; combined totals are not independent or unique examples.',
                        'No model training was performed.', 'Critic measured findings are schema-enforced, not independent detection accuracy.',
                        'Human visual preference, critique factual grounding and full WCAG conformance are unmeasured.']})
    lines = ['# FrontEndSLM reliability results', '', f'{accepted}/{total} candidate-run outcomes accepted by the measured functional audit and critic gate. Runs can reuse briefs; this total is not an independent accuracy estimate.', '',
             f'{blocked} candidate source exports withheld because of documented review findings. Measured results above are historical and unchanged.', '',
             '| Run | Initial acceptance | Final acceptance | Revision attempts | Final interaction tests |', '|---|---:|---:|---:|---:|']
    for r in reports:
        lines.append(f"| {r['run_id']} | {r['first_attempt_accepted']}/{r['total']} | {r['accepted']}/{r['total']} | {r['revision_attempts']} | {r['final_interaction_tests']} |")
    lines += ['', 'First attempts and revisions remain separate. A candidate is accepted only after compilation, five initial viewport renders, all supplied desktop/mobile interaction assertions, complete intermediate-state scans, no measured serious accessibility/overflow/runtime failure, and valid measured critic output with an accept verdict.', '',
              'The original paired baseline remains unchanged: builds 7/20 → 20/20, critic schema validity 0/11 → 20/20, and all original engineering gates 5/20 → 7/20. The expanded audit adds requirements missing from that baseline and corrects the disabled-boundary test; its rates must not be presented as an unchanged-harness baseline comparison.', '',
              'Measured issue coverage in the repair pipeline is enforced by the decoding schema and an independent validator. It is not learned detection accuracy or independently labeled grounding precision. All generated output, measurements, prompts, source snapshots and unsuccessful attempts are retained in the run directories.', '',
              'These are small local demonstration applications. Passing these tests does not prove correctness for arbitrary frontends, production integrations, visual excellence, or complete accessibility conformance. No benchmark data entered training.', '',
              'Open review.html for screenshots, raw evidence links and accepted source ZIPs. Rejected candidates have no accepted-source export.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n')
    (output / 'review.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FrontEndSLM reliability review</title><style>
body{{margin:0;background:#f4f5f2;color:#182820;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1480px;margin:auto;padding:40px 24px}}h1{{font-size:44px;letter-spacing:-.04em;line-height:1.1}}h2{{font-size:27px}}h3{{font-size:18px}}.lede{{max-width:900px}}section{{border-top:1px solid #c6d0c8;margin-top:40px;padding-top:24px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}article{{background:white;padding:22px;border:1px solid #d8dfd9;border-radius:12px;min-width:0}}article p{{font-size:14px}}a{{color:#126147}}.pass{{color:#15583c;font-weight:650}}.fail{{color:#93321d;font-weight:650}}.previews{{display:flex;align-items:start;gap:8px}}.previews a:first-child{{width:76%}}.previews a:nth-child(2){{width:22%}}img{{width:100%;border:1px solid #d8dfd9;border-radius:4px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}h1{{font-size:34px}}main{{padding:24px 16px}}}}</style><main><p>FRONTENDSLM / MEASURED RELIABILITY</p><h1>{accepted} of {total} candidates passed the measured gates.</h1><p class="lede">Generated interfaces evaluated through isolated builds, real browser interactions, responsive and accessibility checks, and a measured critic. First attempts and bounded repairs are reported separately.</p><p class="lede">These results cover the tested local workflows. Human visual quality and universal frontend correctness remain unmeasured.</p><p><a href="report.md">Results and limitations</a> · <a href="summary.json">Machine-readable data</a> · <a href="../pilot-baseline-v2/comparison.md">Original baseline comparison</a></p>{''.join(sections)}</main></html>''')
    write_json(output / 'artifact-manifest.json', {'files': {str(p.relative_to(output)): {'sha256': sha256(p.read_bytes()), 'bytes': p.stat().st_size}
        for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'artifact-manifest.json'}})
    print(f'Packaged {accepted}/{total} accepted candidates at {output}')


if __name__ == '__main__':
    main()
