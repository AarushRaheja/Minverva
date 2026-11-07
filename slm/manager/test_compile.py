"""Compile a spec's prose tests into executable checks.

The manager writes tests as sentences. A check is built only from values in the test's own text, or
from its `verifies` list, so a wrong path or entity stays wrong when it runs. Text outside these forms
returns None and the test does not count. This is deliberately strict: a correct paraphrase also fails
to compile, which is why the compile rate is reported beside the scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from slm.manager.spec import SpecTest


@dataclass(frozen=True)
class Check:
    kind: str
    args: tuple[tuple[str, object], ...] = ()

    def arg(self, name: str):
        return dict(self.args)[name]


def _check(kind: str, **args) -> Check:
    return Check(kind, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in args.items())))


def _slug(words: str) -> str:
    return words.strip().replace(" ", "_")


def compile_test(t: SpecTest) -> Check | None:
    d, e = t.description.strip(), t.expected.strip()

    def both(dp: str, ep: str):
        dm, em = re.fullmatch(dp, d), re.fullmatch(ep, e)
        return (dm, em) if dm and em else None

    if m := both(r"Apply the (\w+) schema to a database\.",
                 r"CREATE TABLE (\w+) succeeds and the table has (.+) columns\."):
        if m[0][1] != m[1][1]:
            return None
        return _check("schema_columns", table=m[0][1], columns=m[1][2].split(" and "))
    if m := both(r"Send GET (/api/\w+) when two rows exist\.", r"The response lists both rows, newest id first\."):
        return _check("list_order", path=m[0][1])
    if m := both(r"Send GET (/api/\w+)/\{item_id\} with the id of an existing row\.",
                 r"The response is the row with that id\."):
        return _check("fetch_one", path=m[0][1])
    if m := both(r"Send POST (/api/\w+) with a title and a valid session\.",
                 r"The response is the new row, owned by the session user\."):
        return _check("create_row", path=m[0][1])
    if m := both(r"Call list(\w+) and create(\w+) against a stubbed fetch\.",
                 r"list(\w+) sends GET (/api/\w+) and create(\w+) sends POST (/api/\w+)\."):
        names = {m[0][1], m[0][2], m[1][1], m[1][3]}
        if len(names) != 1 or m[1][2] != m[1][4]:
            return None
        return _check("client_calls", name=names.pop(), path=m[1][2])
    if both(r"Call require_session without the app_session cookie\.",
            r"require_session raises an HTTPException with status 401\."):
        return _check("session_rejects")
    if both(r"Request a protected route with no session cookie\.",
            r"require_route_guard calls require_session and the request gets a 401 response\."):
        return _check("guard_rejects")
    if both(r"Call oauth_start with a request\.", r"oauth_start returns a redirect to the provider's authorize URL\."):
        return _check("oauth_start")
    if m := both(r"Import the page module\.", r'The module exports route = "(/\w+)"\.'):
        return _check("route_export", route=m[1][1])
    if m := both(r"Render (\w+) with a stubbed fetch returning two rows\.", r"(\w+) renders one list item per row\."):
        return _check("page_renders", component=m[0][1]) if m[0][1] == m[1][1] else None
    if m := both(r"Submit (\w+) with a title\.", r"(\w+) calls the typed client's create function once\."):
        return _check("form_submits", component=m[0][1]) if m[0][1] == m[1][1] else None
    if both(r"Render Shell\.", r"Shell links every page and renders each page component\."):
        return _check("shell_renders")
    if m := both(r"Apply every schema file, with users first\.",
                 r"All (\d+) tables exist and every owner_id references users\."):
        return _check("all_schemas", count=int(m[1][1]))
    if both(r"Request a protected route with and without a valid session cookie\.",
            r"The signed-in request succeeds and the signed-out request is rejected\."):
        return _check("protected_route")
    if m := both(r"Create an? ([\w ]+) through the typed client, then list (/api/\w+)\.",
                 r"The new ([\w ]+) appears in the list response\."):
        if _slug(m[0][1]) != _slug(m[1][1]):
            return None
        return _check("client_create_list", entity=_slug(m[0][1]), path=m[0][2])
    if both(r"Render Shell and follow the link to every page\.",
            r"Every page route renders its component inside the shell\."):
        return _check("shell_renders")
    if m := both(r"Sign in, create an? ([\w ]+) through its form, then open (/\w+)\.",
                 r"The new ([\w ]+) is stored and listed on (/\w+)\."):
        if _slug(m[0][1]) != _slug(m[1][1]) or m[0][2] != m[1][2]:
            return None
        return _check("form_to_page", entity=_slug(m[0][1]), route=m[0][2])
    if both(r"Visit every page route without signing in\.", r"Every page request is rejected by the route guard\."):
        routes = [s.split(":", 1)[1] for s in t.verifies if s.startswith("route:")]
        return _check("routes_rejected", routes=routes) if routes else None
    if both(r"Start the OAuth sign-in flow from a signed-out browser\.",
            r"The browser is redirected to the provider's authorize URL\."):
        return _check("oauth_start")
    return None
