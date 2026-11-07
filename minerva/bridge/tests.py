"""Browser tests compiled from the contract, so an arbitrary brief does not need FrontEndSLM's fixed pattern table.

Every test exists twice. The model reads the VISIBLE version, whose values are placeholders. The harness runs the
BOUND version, whose values are nonces that change each round and whose seed rows exist only in the database. So
hardcoding a row cannot pass, and an example value cannot be misread as a limit, the trap FrontEndSLM's Critic
report describes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from minerva.bridge.contract import AppContract, Entity

SEED_ROWS = 2
SESSION_TOKEN = "audit-session-token"
ANY_TITLE = "<any title>"
SEEDED = "<number of rows in the database>"
SEEDED_PLUS_ONE = "<number of rows in the database, plus one>"
A_SEEDED_TITLE = "<title of a row in the database>"


@dataclass(frozen=True)
class CompiledTests:
    visible: list[dict]
    bound: list[dict]
    seed_sql: str
    nonce: str


def _nonce(contract: AppContract, salt: str) -> str:
    return hashlib.sha256(f"{contract.name}:{salt}".encode()).hexdigest()[:8]


def _step(action: str, test_id: str = "", value: str = "", shown: str | None = None) -> tuple[dict, dict]:
    bound = {"action": action, "test_id": test_id, "value": value}
    return ({**bound, "value": value if shown is None else shown}, bound)


def _test(test_id: str, pairs: list[tuple[dict, dict]], **extra) -> tuple[dict, dict]:
    return ({"id": test_id, "steps": [p[0] for p in pairs], **extra},
            {"id": test_id, "steps": [p[1] for p in pairs], **extra})


def _seed_title(e: Entity, nonce: str, i: int) -> str:
    return f"Seeded {e.slug.replace('_', ' ')} {i} {nonce}"


def _created_title(e: Entity, nonce: str) -> str:
    return f"Created {e.slug.replace('_', ' ')} {nonce}"


def _create_test(e: Entity, nonce: str) -> tuple[dict, dict]:
    title = _created_title(e, nonce)
    api = json.dumps({"path": e.base, "title": title})
    return _test(f"create-{e.tid}", [
        _step("click", f"nav-{e.tid}"),
        _step("fill", f"{e.tid}-title-input", title, ANY_TITLE),
        _step("click", f"{e.tid}-submit"),
        _step("expect_text", f"{e.tid}-list", title, ANY_TITLE),
        _step("expect_count", f"{e.tid}-row", str(SEED_ROWS + 1), SEEDED_PLUS_ONE),
        _step("expect_api_contains", "", api, f"the server's {e.base} now has a row with that title"),
        _step("reload"),
        _step("click", f"nav-{e.tid}"),
        _step("expect_text", f"{e.tid}-list", title, ANY_TITLE),
    ])


def compile_tests(contract: AppContract, salt: str = "0") -> CompiledTests:
    """Bounded on purpose: navigation, one create per entity, one validation, sign-out."""
    nonce = _nonce(contract, salt)
    nav: list[tuple[dict, dict]] = []
    for e in contract.entities:
        nav += [
            _step("click", f"nav-{e.tid}"),
            _step("expect_visible", f"{e.tid}-list"),
            _step("expect_count", f"{e.tid}-row", str(SEED_ROWS), SEEDED),
            _step("expect_text", f"{e.tid}-list", _seed_title(e, nonce, 1), A_SEEDED_TITLE),
        ]
    pairs = [_test("nav-and-list", nav)]
    pairs += [_create_test(e, nonce) for e in contract.entities]
    p = contract.primary
    pairs.append(_test("empty-title-rejected", [
        _step("click", f"nav-{p.tid}"),
        _step("click", f"{p.tid}-submit"),
        _step("expect_visible", f"{p.tid}-form-error"),
        _step("expect_count", f"{p.tid}-row", str(SEED_ROWS), SEEDED),
    ]))
    pairs.append(_test("sign-out", [
        _step("click", "sign-out"),
        _step("expect_visible", "auth-form"),
    ]))
    return CompiledTests(visible=[v for v, _ in pairs], bound=[b for _, b in pairs],
                         seed_sql=seed_sql(contract, nonce), nonce=nonce)


def seed_sql(contract: AppContract, nonce: str) -> str:
    tables = ", ".join(["users", *(e.slug for e in contract.entities)])
    lines = [
        f"TRUNCATE {tables} RESTART IDENTITY CASCADE;",
        "INSERT INTO users (email, password_hash, session_token) "
        f"VALUES ('audit@example.com', 'not-a-usable-hash', '{SESSION_TOKEN}');",
    ]
    for e in contract.entities:
        values = ", ".join(f"(1, '{_seed_title(e, nonce, i)}')" for i in range(1, SEED_ROWS + 1))
        lines.append(f"INSERT INTO {e.slug} (owner_id, title) VALUES {values};")
    return "\n".join(lines) + "\n"


def journey_tests(contract: AppContract, salt: str = "0") -> list[dict]:
    """The whole-stack journey on the final tree: a new user signs up, creates a row, and finds it after signing in."""
    nonce = _nonce(contract, f"journey:{salt}")
    p = contract.primary
    title = _created_title(p, nonce)
    email, password = f"journey-{nonce}@example.com", f"pass-{nonce}-word"
    sign_in = [("fill", "auth-email", email), ("fill", "auth-password", password)]
    steps = [
        ("expect_visible", "auth-form", ""), ("click", "auth-mode", ""), *sign_in, ("click", "auth-submit", ""),
        ("click", f"nav-{p.tid}", ""), ("fill", f"{p.tid}-title-input", title), ("click", f"{p.tid}-submit", ""),
        ("expect_text", f"{p.tid}-list", title), ("reload", "", ""), ("click", f"nav-{p.tid}", ""),
        ("expect_text", f"{p.tid}-list", title), ("click", "sign-out", ""), ("expect_visible", "auth-form", ""),
        *sign_in, ("click", "auth-submit", ""), ("click", f"nav-{p.tid}", ""), ("expect_text", f"{p.tid}-list", title),
    ]
    return [{"id": "journey", "signed_out": True,
             "steps": [{"action": a, "test_id": t, "value": v} for a, t, v in steps]}]


def api_probes(contract: AppContract, salt: str = "0") -> dict:
    """What the harness checks over HTTP before any browser opens, so backend faults are not blamed on the UI."""
    nonce = _nonce(contract, salt)
    return {"entities": [{"slug": e.slug, "base": e.base, "seeded": SEED_ROWS, "seed_title": _seed_title(e, nonce, 1),
                          "probe_title": f"Probe {nonce}"} for e in contract.entities],
            "guarded_pages": list(contract.guarded_pages)}
