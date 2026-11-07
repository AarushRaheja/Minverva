"""Measured facts and fail-closed critique validation; no human quality labels."""
import json
from copy import deepcopy

from frontendslm.schemas import Critique, validate_critique_references

VIEWPORTS = {"desktop", "mobile", "tablet", "stress", "wide"}


def measured_issue_text(check: dict, plans: list[dict]) -> tuple[str, str]:
    """Verbatim measurement facts and required assertions, not model paraphrases."""
    if check['id'] == 'interaction':
        facts, requirements = [], []
        for test in (check.get('details') or {}).get('tests', []):
            if test.get('passed') is not False:
                continue
            failed_step = next(((n, s) for n, s in enumerate(test.get('steps', [])) if s.get('passed') is False), None)
            if failed_step:
                n, step = failed_step
                facts.append(f"{test['id']}: step {n + 1} {step['action']}({step.get('test_id', '')}): {step.get('error', '')[:160]}")
            else:
                facts.append(f"{test['id']}: failed")
            plan_id = test['id'].rsplit(':', 1)[0]
            for plan in plans:
                if plan['id'] == plan_id and plan not in requirements:
                    requirements.append(plan)
        compact_plans = [{'id': p['id'], 'steps': [f"{s['action']}({s.get('test_id', '')}, {s.get('value', '')})"
                                                 for s in p['steps']]} for p in requirements]
        return ('Measured failures: ' + ' | '.join(facts[:2]),
                'Rerun these complete required workflows on desktop and mobile; all steps must pass: ' +
                json.dumps(compact_plans, separators=(',', ':')))
    details = json.dumps(check.get('details'), ensure_ascii=False, separators=(',', ':'))
    return (f"Measured {check['id']} failure: {details[:800]}",
            f"Rerun the complete browser audit; the {check['id']} measured group must pass in all required states.")


def critic_output_schema(evidence: dict) -> dict:
    """Require measured findings as a schema prefix; explanations remain model-generated.

    This is tool-enforced reporting, not evidence of independent model defect discovery.
    The ordinary Critique contract and independent validator still apply to every output.
    """
    schema = Critique.model_json_schema()
    review_refs = content_review_refs(evidence) if evidence.get('evidence_protocol') == 'explicit-content-review-v2' else []
    if review_refs:
        schema['required'].append('content_reviews')
        reviews = []
        for ref in review_refs:
            review = deepcopy(schema['$defs']['ContentReview'])
            review['properties']['test_ref'] = {'type': 'string', 'const': ref}
            reviews.append(review)
        schema['properties']['content_reviews'] = {'type': 'array', 'minItems': len(reviews),
            'maxItems': len(reviews), 'prefixItems': reviews, 'items': False}
    schema["$defs"]["Issue"]["properties"]["evidence"]["maxItems"] = 3
    failed = [c for c in evidence["measured_checks"] if c["status"] == "fail"]
    unknown = any(c["status"] == "unknown" for c in evidence["measured_checks"])
    if failed:
        schema["properties"]["verdict"]["enum"] = ["revise"]
    elif unknown:
        schema["properties"]["verdict"]["enum"] = ["revise", "uncertain"]
    if unknown:
        schema["properties"]["uncertainties"]["minItems"] = 1
    known = {(r["type"], r["ref"]) for r in evidence.get("references", [])}
    # Passing assertions may support a copy/behavior contradiction, not a failed
    # interaction. The independent validator restricts that exception by category.
    allowed = {(r['type'], r['ref']) for c in failed for r in c['references']} | {
        pair for pair in known if pair[0] == 'screenshot'} | {
        ('test', a['test_ref']) for a in evidence.get('passed_assertions', [])}
    alternatives = []
    for kind, name in sorted(allowed & known):
        entry = deepcopy(schema['$defs']['EvidenceReference'])
        entry['properties']['type'] = {'type': 'string', 'const': kind}
        entry['properties']['ref'] = {'type': 'string', 'const': name}
        if kind == 'screenshot':
            entry['properties']['region'] = {'type': 'array', 'items': {'type': 'number', 'minimum': 0, 'maximum': 1},
                                              'minItems': 4, 'maxItems': 4}
            entry['required'] = ['type', 'ref', 'region']
        else:
            entry['properties']['region'] = {'type': 'null'}
        alternatives.append(entry)
    if alternatives:
        schema['$defs']['Issue']['properties']['evidence']['items'] = {'anyOf': alternatives}
    else:
        schema['properties']['issues']['maxItems'] = 0
    prefix = []
    for check in failed:
        refs = [r for r in check["references"] if (r["type"], r["ref"]) in known]
        if not refs:
            continue  # Independent validation will reject an uncitable measured finding.
        issue = deepcopy(schema["$defs"]["Issue"])
        properties = issue["properties"]
        properties["id"] = {"type": "string", "const": f"measured-{check['id']}"}
        properties["category"]["enum"] = check["allowed_issue_categories"]
        properties["severity"]["enum"] = ["major", "blocker"]
        observation, acceptance = measured_issue_text(check, evidence.get('required_test_plans', []))
        properties['observation'] = {'type': 'string', 'const': observation}
        properties['acceptance_test'] = {'type': 'string', 'const': acceptance}
        properties["evidence"]["items"] = {"type": "object", "additionalProperties": False,
            "required": ["type", "ref"], "properties": {
                "type": {"type": "string", "const": refs[0]["type"]},
                "ref": {"type": "string", "enum": [r["ref"] for r in refs]},
                "region": {"type": "null"},
            }}
        prefix.append(issue)
    schema["properties"]["issues"].update(maxItems=8 if alternatives else 0, minItems=len(prefix))
    if prefix:
        schema["properties"]["issues"]["prefixItems"] = prefix
    return schema


def measured_checks(evidence: dict, expected_tests: list[dict] | None = None) -> list[dict]:
    checks = []

    def add(name, status, categories, refs, details):
        checks.append({"id": name, "status": status, "allowed_issue_categories": categories,
                       "references": refs, "details": details})

    def ref(kind, name):
        return {"type": kind, "ref": name}

    build = (evidence.get("build") or {}).get("passed")
    add("build", "pass" if build is True else "fail" if build is False else "unknown",
        ["runtime"], [ref("build", "build")] if evidence.get("build") else [], evidence.get("build"))
    views = evidence.get("views", {})
    incomplete = sorted(VIEWPORTS - set(views)) + [v for v, data in views.items() if data.get("harness_error")]
    empty = [v for v, data in views.items() if "text_length" in data and data["text_length"] <= 20]
    render_unknown = bool(incomplete or evidence.get("harness_error") or
                          any("text_length" not in v for v in views.values()))
    add("render", "fail" if empty else "unknown" if render_unknown else "pass", ["runtime"],
        [ref("runtime", v) for v in empty], {"missing_or_failed_views": incomplete, "empty_views": empty,
        "harness_error": evidence.get("harness_error")})
    tests = evidence.get("tests", [])
    expected_ids = {f"{test['id']}:{view}" for test in expected_tests or [] for view in ("desktop", "mobile")}
    missing = sorted(expected_ids - {test["id"] for test in tests})
    failed = [test for test in tests if test.get("passed") is False]
    test_complete = not missing and len(tests) >= 2 and all(test.get("passed") is True for test in tests)
    add("interaction", "fail" if failed else "pass" if test_complete else "unknown", ["interaction"],
        [ref("test", t["id"]) for t in failed], {"missing_tests": missing, "tests": tests})
    violations, overflows, runtime, a11y_missing, overflow_missing = [], [], [], [], []
    audited = bool(evidence.get("audit_version") or any("interaction_states" in v for v in views.values()))
    for view, data in views.items():
        for state, key in [("initial", "accessibility"), ("after", "after_accessibility")]:
            if state == "after" and view not in {"desktop", "mobile"}:
                continue
            if key not in data:
                a11y_missing.append(f"{view}/{state}")
            for item in data.get(key, []):
                if item.get("impact") in {"serious", "critical"}:
                    violations.append({"view": view, "state": state, "rule": item.get("id"),
                                       "impact": item["impact"], "description": item.get("description"),
                                       "nodes": [{k: n.get(k) for k in ("target", "failureSummary")}
                                                 for n in item.get("nodes", [])[:4]]})
        for state, key in [("initial", "horizontal_overflow"), ("after", "after_overflow")]:
            if state == "after" and view not in {"desktop", "mobile"}:
                continue
            if key not in data:
                overflow_missing.append(f"{view}/{state}")
            if data.get(key) is True:
                overflows.append({"view": view, "state": state})
        if data.get("broken_images"):
            runtime.append({"view": view, "broken_images": data["broken_images"]})
        if audited and view in {"desktop", "mobile"}:
            states = data.get("interaction_states", [])
            expected = {f"{test['id']}:step-{i}" for test in tests if test.get("view", test["id"].split(":")[-1]) == view
                        for i, step in enumerate(test.get("steps", [])) if step.get("passed") is True and
                        step["action"] in {"click", "click_if_enabled", "fill", "select", "press"}}
            absent = sorted(expected - {s["ref"] for s in states})
            a11y_missing.extend(absent)
            overflow_missing.extend(absent)
            for state in states:
                if "accessibility" not in state or state.get("harness_error"):
                    a11y_missing.append(state["ref"])
                if "horizontal_overflow" not in state or state.get("harness_error"):
                    overflow_missing.append(state["ref"])
                for item in state.get("accessibility", []):
                    if item.get("impact") in {"serious", "critical"}:
                        violations.append({"view": state["ref"], "viewport": view, "state": "intermediate",
                            "rule": item.get("id"), "impact": item["impact"], "description": item.get("description"),
                            "nodes": [{k: n.get(k) for k in ("target", "failureSummary")}
                                      for n in item.get("nodes", [])[:4]]})
                if state.get("horizontal_overflow") is True:
                    overflows.append({"view": state["ref"], "viewport": view, "state": "intermediate"})
    runtime += evidence.get("runtime_errors", []) + evidence.get("failed_requests", [])
    if audited:
        runtime += evidence.get("console_errors", [])
    for name, failures, missing_data, kind, categories in [
        ("accessibility", violations, a11y_missing, "accessibility",
         ["accessibility", "color"] if violations and all(v["rule"] == "color-contrast" for v in violations)
         else ["accessibility"]),
        ("overflow", overflows, overflow_missing, "overflow", ["responsive"]),
        ("runtime", runtime, [v for v, d in views.items() if "broken_images" not in d] +
         [k for k in ("runtime_errors", "failed_requests") if k not in evidence], "runtime", ["runtime"]),
    ]:
        add(name, "fail" if failures else "unknown" if render_unknown or missing_data else "pass", categories,
            [ref(kind, v) for v in sorted({f["view"] for f in failures})],
            {"failures": failures, "missing_measurements": missing_data})
    return checks


ASSERTION_SEMANTICS = {
    'expect_text': 'Target text contains the expected string; not an exact text or numeric equality check.',
    'expect_text_exact': 'Target text equals the expected string after Playwright whitespace normalization.',
    'expect_count': 'Locator count equals the expected integer.',
    'expect_visible': 'Target locator is visible.',
    'expect_hidden': 'Target locator is hidden or absent.',
}


def passed_assertions(evidence: dict) -> list[dict]:
    """Expose executed assertions, never promote test plans or clicks to observations."""
    return [{'test_ref': test['id'], 'step_index': index, 'action': step['action'],
             'test_id': step.get('test_id'), 'expected': step.get('value', ''),
             'semantics': ASSERTION_SEMANTICS[step['action']],
             **({'observation': step['observation']} if 'observation' in step else {})}
            for test in evidence.get('tests', []) for index, step in enumerate(test.get('steps', []))
            if step.get('passed') is True and step.get('action') in ASSERTION_SEMANTICS]


def content_review_refs(evidence: dict) -> list[str]:
    """One comparison per executed workflow; duplicate viewport runs remain in evidence."""
    refs = {}
    for assertion in evidence.get('passed_assertions', []):
        ref = assertion['test_ref']
        refs.setdefault(ref.rsplit(':', 1)[0], ref)
    return list(refs.values())


def compact_evidence(evidence: dict, expected_tests: list[dict] | None = None, *,
                     explicit_content_review: bool = False) -> dict:
    """Preserve measured states and readable initial copy with explicit assertion limits."""
    return {
        'evidence_protocol': 'explicit-content-review-v2' if explicit_content_review else 'readable-copy-and-assertions-v1',
        "measured_checks": measured_checks(evidence, expected_tests),
        'required_test_plans': expected_tests or [],
        'passed_assertions': passed_assertions(evidence),
        'initial_screen_text': {name: {'text': data['dom_snapshot'][:8000],
                                      'truncated': len(data['dom_snapshot']) > 8000,
                                      'state': 'initial', 'screenshot_ref': name}
                                for name, data in evidence.get('views', {}).items()
                                if name in {'desktop', 'mobile'} and isinstance(data.get('dom_snapshot'), str)},
        "references": [r for r in evidence.get("references", [])
                       if r["type"] != "screenshot" or r["ref"] in {"desktop", "mobile"}],
        "console_errors": evidence.get("console_errors", []),
        "views": {name: {k: value for k, value in data.items() if k in {
            "horizontal_overflow", "after_overflow", "text_length", "harness_error", "broken_images",
            "scroll_width", "viewport_width", "controls",
        }} | {key: [{"id": a.get("id"), "impact": a.get("impact"), "description": a.get("description"),
                    "nodes": [{"target": n.get("target"), "failureSummary": n.get("failureSummary")}
                              for n in a.get("nodes", [])[:4]]} for a in data.get(key, [])]
              for key in ("accessibility", "after_accessibility") if key in data}
                  for name, data in evidence.get("views", {}).items()},
        'manual_review_not_confirmed': {name: sorted({a.get('id', 'unknown') for a in data.get('accessibility_incomplete', [])})
                                      for name, data in evidence.get('views', {}).items()
                                      if data.get('accessibility_incomplete')},
    }


def validate_measured_critique(critique: Critique, evidence: dict) -> dict:
    checks = evidence["measured_checks"]
    failed = [c for c in checks if c["status"] == "fail"]
    unknown = [c["id"] for c in checks if c["status"] == "unknown"]
    errors, covered = [], []
    if evidence.get('evidence_protocol') == 'explicit-content-review-v2':
        expected_refs = content_review_refs(evidence)
        if [r.test_ref for r in critique.content_reviews] != expected_refs:
            errors.append('Content reviews must cover each executed workflow in evidence order')
        screen_text = '\n'.join(v['text'] for v in evidence.get('initial_screen_text', {}).values())
        for review in critique.content_reviews:
            if review.status in {'consistent', 'contradicted'} and not review.screen_quote.strip():
                errors.append(f'Content review {review.test_ref} needs an exact screen quotation')
            if review.screen_quote and review.screen_quote not in screen_text:
                errors.append(f'Content review {review.test_ref} quotation is absent from initial screen text')
            if review.status == 'contradicted' and (critique.verdict != 'revise' or not any(
                i.category == 'content_consistency' and i.severity in {'major', 'blocker'} and
                any(r.type == 'test' and r.ref == review.test_ref for r in i.evidence) for i in critique.issues
            )):
                errors.append(f'Content contradiction {review.test_ref} requires revise and a matching significant issue')
            if review.status == 'unknown' and (critique.verdict == 'accept' or not critique.uncertainties):
                errors.append(f'Unknown content review {review.test_ref} requires uncertainty and prohibits acceptance')
    if failed and critique.verdict != "revise":
        errors.append("Measured failures require a revise verdict")
    if unknown and critique.verdict == "accept":
        errors.append("Incomplete measurements prohibit acceptance")
    if unknown and not critique.uncertainties:
        errors.append("Incomplete measurements require an explicit uncertainty")
    if critique.verdict == "accept" and any(i.severity in {"blocker", "major"} for i in critique.issues):
        errors.append("Acceptance contradicts significant reported issues")
    if critique.verdict == 'revise' and not critique.issues:
        errors.append('A revise verdict requires an actionable evidence-backed issue')
    refs = validate_critique_references(critique, evidence)
    valid_issues = {r["issue_id"] for r in refs if r["reference_valid"]}
    for check in failed:
        allowed = {(r["type"], r["ref"]) for r in check["references"]}
        if any(issue.id in valid_issues and issue.category in check["allowed_issue_categories"] and
               issue.severity in {"major", "blocker"} and
               any((r.type, r.ref) in allowed for r in issue.evidence) for issue in critique.issues):
            covered.append(check["id"])
        else:
            errors.append(f"Missing measured failure issue: {check['id']}")
    failed_test_ids = {r["ref"] for c in failed if c["id"] == "interaction" for r in c["references"]}
    assertion_test_ids = {a['test_ref'] for a in evidence.get('passed_assertions', [])}
    for issue in critique.issues:
        copy_contradiction = issue.category == 'content_consistency'
        if copy_contradiction and not (
            any(r.type == 'screenshot' for r in issue.evidence) and
            any(r.type == 'test' and r.ref in assertion_test_ids for r in issue.evidence)
        ):
            errors.append(f'Content consistency issue {issue.id} requires a screenshot and an executed passing assertion')
        for reference in issue.evidence:
            supported_copy_assertion = (copy_contradiction and reference.type == 'test' and
                                        reference.ref in assertion_test_ids)
            if reference.type != 'screenshot' and not supported_copy_assertion and not any(
                issue.category in check['allowed_issue_categories'] and
                {'type': reference.type, 'ref': reference.ref} in check['references'] for check in failed
            ):
                errors.append(f'Issue {issue.id} cites a tool reference without a matching measured failure: '
                              f'{reference.type}/{reference.ref}')
        if issue.category == "interaction" and not any(r.type == "test" and r.ref in failed_test_ids
                                                       for r in issue.evidence):
            errors.append(f"Interaction defect {issue.id} is not supported by a failed test")
    return {"valid": not errors and all(r["reference_valid"] for r in refs), "errors": errors,
            "required_failure_groups": [c["id"] for c in failed], "covered_failure_groups": covered,
            "unknown_groups": unknown, "human_grounding_verified": None}


def effective_verdict(critique: Critique | None, checks: list[dict], validation: dict | None) -> str:
    # This independent gate never repairs or overwrites the model response.
    if any(c["status"] == "fail" for c in checks):
        return "revise"
    if critique is None or not validation or not validation["valid"] or any(c["status"] == "unknown" for c in checks):
        return "uncertain"
    return critique.verdict
