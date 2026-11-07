"""Let a teacher model reword a gold spec's prose, and nothing else. Pure logic, no network.

The gold spec's structure (ids, tasks, deps, tested symbols, acceptance criteria) is correct by
construction, so the teacher never touches it. It only rewrites the prose that gains from app-specific
wording: the architecture line, section summaries, group headings, and integration and system tests.
Step-level unit tests are exact statements about one symbol, so they stay as written. A pilot showed
models copying them verbatim, which spent most of the GPU time for no change.

A rewrite is kept only when it passes `problem_with`:
  - it keeps every exact identifier of the original (paths, function names, status words);
  - it names no technology outside the fixed stack (the classic hallucination here);
  - it states no latency, throughput or percentage target, since nothing in this project measures them.
A section with any rejected item keeps its original text, so one bad line cannot slip through.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from slm.contracts import Strict
from slm.domains import DOMAINS
from slm.manager.spec import ProjectSpec, SpecTest

PROJECT = "project"
SECTIONS: tuple[str, ...] = (PROJECT, *DOMAINS)
MIN_LEN, MAX_LEN = 12, 320

# Named technologies that are not in fastapi+react+postgres.
_OFF_STACK = re.compile(
    r"\b(redis|memcached|kafka|rabbitmq|celery|mongo(db)?|mysql|sqlite|cassandra|dynamo(db)?|elastic(search)?"
    r"|graphql|grpc|websockets?|jwts?|bcrypt|argon2|alembic|sqlalchemy|django|flask|express|node\.?js"
    r"|vue|angular|svelte|next\.?js|redux|kubernetes|k8s|docker|nginx|aws|gcp|azure|s3|terraform"
    r"|pytest|jest|cypress|selenium|playwright|okta|auth0|stripe|twilio|rbac|microservices?)\b",
    re.IGNORECASE,
)
_INVENTED_METRIC = re.compile(
    r"\d+(\.\d+)?\s*(ms|msec|milliseconds?|seconds?|secs?|minutes?|rps|qps|req/s|requests?\s*(per|/)|percent)\b"
    r"|\d+(\.\d+)?\s*%"
    r"|\bunder \d|\bwithin \d|\bless than \d|\b\d+\s*(k|concurrent)\b",
    re.IGNORECASE,
)
# Tokens that must survive a rewrite: paths, snake_case, camelCase, PascalCase with 2+ humps, HTTP verbs.
_ANCHOR = re.compile(r"/[\w/{}-]+(?:\.[\w/{}-]+)*|\b\w+_\w+\b|\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z]+[A-Z]\w*\b|\b(?:GET|POST)\b")


class TextItem(Strict):
    id: str
    text: str


class SectionText(Strict):
    """The teacher's whole reply for one section."""

    items: list[TextItem] = Field(min_length=1)


def _test_items(t: SpecTest) -> dict[str, str]:
    return {f"{t.id}.description": t.description, f"{t.id}.expected": t.expected}


def section_items(spec: ProjectSpec, section: str) -> dict[str, str]:
    """item id -> current text, for every piece of prose the teacher may reword in this section."""
    if section == PROJECT:
        out = {"architecture": spec.architecture}
        for t in spec.system_tests:
            out |= _test_items(t)
        return out
    dom = spec.domain(section)
    out = {f"{section}.summary": dom.summary}
    for t in dom.integration_tests:
        out |= _test_items(t)
    for g in dom.groups:
        out[f"{g.id}.heading"] = g.heading
    return out


TEACHER_SYSTEM = """You improve the wording of a software project spec for a specific web app.
You receive the project brief and a JSON list of items, each with an id and its current text.
Reword every item so a reader can tell which app it belongs to: use the brief's words for the people
and records involved. Do not copy an item unchanged unless it is a short heading. Keep the same meaning.

Rules:
- Return every id exactly once, unchanged. Each text is one sentence on one line.
- Keep every path, function name, component name and HTTP verb exactly as written.
- The stack is only FastAPI, React, TypeScript, Postgres and cookie sessions. Name no other technology.
- Do not add numbers for speed, load or percentages. Nothing in this project measures them.
- Do not add features the current text does not mention.

Reply with ONLY JSON: {"items": [{"id": "<id>", "text": "<text>"}]}"""


def section_prompt(brief: str, section: str, items: dict[str, str]) -> str:
    body = "\n".join(f'- "{k}": {v}' for k, v in items.items())
    return f"Project brief: {brief}\nSection: {section}\n\nItems:\n{body}\n\nJSON:"


def problem_with(original: str, new: str, entities: frozenset[str] = frozenset()) -> str | None:
    """Why this rewrite must be rejected, or None when it is acceptable.

    `entities` are the project's entity slugs. In prose, "ticket items" is a fair way to write the
    slug ticket_item, unlike a real code identifier such as owner_id, which must stay exact.
    """
    text = new.strip()
    if "\n" in text:
        return "multi_line"
    # Headings are short by nature, so the minimum length follows the original.
    if not min(MIN_LEN, len(original)) <= len(text) <= max(MAX_LEN, 2 * len(original)):
        return "length"
    off_stack = _OFF_STACK.search(text)
    if off_stack and not _OFF_STACK.search(original):
        return f"off_stack:{off_stack.group(0).lower()}"
    if _INVENTED_METRIC.search(text) and not _INVENTED_METRIC.search(original):
        return "invented_metric"
    for anchor in _ANCHOR.findall(original):
        if anchor in entities and anchor.replace("_", " ") in text.lower():
            continue
        if anchor not in text:
            return f"lost_anchor:{anchor}"
    return None


class SectionResult(BaseModel):
    section: str
    accepted: bool
    texts: dict[str, str] = {}  # item id -> new text, only when accepted
    problems: list[str] = []
    changed: int = 0  # items whose text really differs from the original


def judge_section(section: str, items: dict[str, str], reply: str,
                  entities: frozenset[str] = frozenset()) -> SectionResult:
    """All-or-nothing for one section: any bad item keeps the whole section's original text."""
    try:
        got = SectionText.model_validate_json(reply)
    except ValueError:
        return SectionResult(section=section, accepted=False, problems=["bad_json"])
    ids = [i.id for i in got.items]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append("duplicate_ids")
    if set(ids) != set(items):
        problems.append(f"wrong_ids:{len(set(items) - set(ids))}missing,{len(set(ids) - set(items))}extra")
    texts = {i.id: i.text.strip() for i in got.items if i.id in items}
    for k, v in texts.items():
        why = problem_with(items[k], v, entities)
        if why:
            problems.append(f"{k}:{why}")
    if problems:
        return SectionResult(section=section, accepted=False, problems=problems)
    return SectionResult(section=section, accepted=True, texts=texts,
                         changed=sum(texts[k] != items[k] for k in items))


def _apply_test(t: SpecTest, texts: dict[str, str]) -> SpecTest:
    return t.model_copy(update={
        "description": texts.get(f"{t.id}.description", t.description),
        "expected": texts.get(f"{t.id}.expected", t.expected),
    })


def apply_texts(spec: ProjectSpec, texts: dict[str, str]) -> ProjectSpec:
    """A copy of `spec` with prose replaced. Structural fields are never read from `texts`."""
    out = spec.model_copy(deep=True)
    out.architecture = texts.get("architecture", out.architecture)
    out.system_tests = [_apply_test(t, texts) for t in out.system_tests]
    for d in DOMAINS:
        dom = out.domain(d)
        dom.summary = texts.get(f"{d}.summary", dom.summary)
        dom.integration_tests = [_apply_test(t, texts) for t in dom.integration_tests]
        for g in dom.groups:
            g.heading = texts.get(f"{g.id}.heading", g.heading)
    return out
