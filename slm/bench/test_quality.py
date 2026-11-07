"""Score generated tests by running them: must pass on gold artifacts and fail on broken versions.

    uv run --with fastapi --with uvicorn --with httpx --with asyncpg \
        python -m slm.bench.test_quality --raw results.jsonl --out out/test-quality/report.json \
        --node-modules out/test-quality/node_modules --dsn postgresql://postgres@localhost:54329

Needs a running Postgres server and Node with react, react-dom, jsdom and esbuild.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from multiprocessing import get_context
from pathlib import Path

from slm.bench.build import SEED
from slm.bench.catalog import gold_artifacts
from slm.bench.mutants import mutants_for
from slm.bench.variety import generate_varied
from slm.contracts import ProjectPlan, integrate
from slm.domains import DOMAINS, api_base, component, page_route, pascal
from slm.manager.spec import ProjectSpec, SpecTest, gold_spec
from slm.manager.test_compile import Check, compile_test

HARNESS = Path(__file__).with_name("frontend_harness.cjs")
SERVER_CHECKS = {"list_order", "fetch_one", "create_row", "guard_rejects", "protected_route", "routes_rejected",
                 "client_create_list", "form_to_page"}


def spec_tests(spec: ProjectSpec) -> list[tuple[str, str | None, SpecTest]]:
    """(scope level, owning task id, test), for every test in a spec."""
    out: list[tuple[str, str | None, SpecTest]] = [("system", None, t) for t in spec.system_tests]
    for d in DOMAINS:
        out += [("integration", None, t) for t in spec.domain(d).integration_tests]
    for _, task in spec.tasks():
        out += [("unit", task.id, s.test) for s in task.steps]
    return out


class Runner:
    """Runs checks against one version of a project at a time. One per worker process."""

    def __init__(self, dsn_root: str, node_modules: str, index: int):
        import asyncpg

        self.asyncpg = asyncpg
        self.database = f"quality_{index}"
        self.dsn = f"{dsn_root}/{self.database}"
        self.loop = asyncio.new_event_loop()
        admin = self.loop.run_until_complete(asyncpg.connect(f"{dsn_root}/postgres"))
        self.loop.run_until_complete(admin.execute(f"DROP DATABASE IF EXISTS {self.database} WITH (FORCE)"))
        self.loop.run_until_complete(admin.execute(f"CREATE DATABASE {self.database}"))
        self.loop.run_until_complete(admin.close())
        self.conn = self.loop.run_until_complete(asyncpg.connect(self.dsn))
        env = {**os.environ, "NODE_PATH": node_modules}
        self.node = subprocess.Popen(["node", str(HARNESS)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1)
        self.tmp = tempfile.mkdtemp(prefix=f"quality{index}")
        self.schema_ok = False

    def sql(self, statement: str, *args):
        return self.loop.run_until_complete(self.conn.fetch(statement, *args))

    def _load_schemas(self, plan: ProjectPlan, files: dict[str, str]) -> bool:
        self.sql("DROP SCHEMA public CASCADE")
        self.sql("CREATE SCHEMA public")
        try:
            for t in plan.tasks:
                if t.kind == "schema":
                    self.loop.run_until_complete(self.conn.execute(files[f"src/database/{t.target}.sql"]))
            return True
        except Exception:  # noqa: BLE001 - a broken schema is what some versions are for
            return False

    def _reset_rows(self, plan: ProjectPlan) -> bool:
        tables = ", ".join(t.target for t in plan.tasks if t.kind == "schema")
        try:
            self.sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
            self.sql("INSERT INTO users (email, password_hash, session_token) VALUES "
                     "('other@example.com', 'x', 'other'), ('good@example.com', 'x', 'good')")
            return True
        except Exception:  # noqa: BLE001
            return False

    def _node(self, op: str, **request) -> bool:
        self.node.stdin.write(json.dumps({"op": op, "root": self.root, **request}) + "\n")
        self.node.stdin.flush()
        return bool(json.loads(self.node.stdout.readline())["pass"])

    def _seed(self, entity: str) -> None:
        self.sql(f"INSERT INTO {entity} (owner_id, title) VALUES (2, 'row one'), (2, 'row two')")

    def _in_scratch_schema(self, statements: list[str], query):
        """Apply SQL in a throwaway schema, read the result, and roll everything back."""

        async def run():
            tx = self.conn.transaction()
            await tx.start()
            try:
                await self.conn.execute("CREATE SCHEMA scratch; SET LOCAL search_path = scratch")
                for s in statements:
                    await self.conn.execute(s)
                return await query()
            finally:
                await tx.rollback()

        return self.loop.run_until_complete(run())

    def _check_schema(self, check: Check, files: dict[str, str]) -> bool:
        table = check.arg("table")
        users, own = files.get("src/database/users.sql"), files.get(f"src/database/{table}.sql")
        if own is None or users is None:
            return False
        statements = [own] if table == "users" else [users, own]

        async def columns():
            return await self.conn.fetch("SELECT column_name FROM information_schema.columns "
                                         "WHERE table_schema = 'scratch' AND table_name = $1", table)

        have = {r["column_name"] for r in self._in_scratch_schema(statements, columns)}
        return set(check.arg("columns")) <= have

    def _check_all_schemas(self, check: Check, plan: ProjectPlan, files: dict[str, str]) -> bool:
        names = [p for p in files if p.startswith("src/database/") and p.endswith(".sql")]
        ordered = sorted(names, key=lambda p: not p.endswith("/users.sql"))

        async def facts():
            tables = await self.conn.fetch("SELECT table_name FROM information_schema.tables "
                                           "WHERE table_schema = 'scratch'")
            refs = await self.conn.fetch(
                "SELECT conrelid::regclass::text AS tbl, pg_get_constraintdef(oid) AS def FROM pg_constraint "
                "WHERE contype = 'f' AND connamespace = 'scratch'::regnamespace")
            return {r["table_name"] for r in tables}, {r["tbl"].split(".")[-1]: r["def"] for r in refs}

        tables, refs = self._in_scratch_schema([files[p] for p in ordered], facts)
        others = tables - {"users"}
        linked = all("owner_id" in refs.get(t, "") and "users" in refs.get(t, "") for t in others)
        return len(tables) == check.arg("count") and linked

    def _run(self, check: Check, plan: ProjectPlan, files: dict[str, str], http) -> bool:
        kind = check.kind
        good = {"Cookie": "app_session=good"}
        entities = {api_base(t.target): t.target for t in plan.tasks if t.kind == "rest"}
        by_route = {page_route(t.target): t.target for t in plan.tasks if t.kind == "page"}
        if kind == "schema_columns":
            return self._check_schema(check, files)
        if kind == "all_schemas":
            return self._check_all_schemas(check, plan, files)
        if kind == "session_rejects":
            return self._session_rejects()
        if kind == "oauth_start":
            return self._oauth_start()
        if kind == "client_calls":
            match = [t.target for t in plan.tasks if t.kind == "client" and pascal(t.target) == check.arg("name")]
            if not match:
                return False
            return self._node("client_calls", file=f"src/network/{match[0]}_client.ts",
                              name=check.arg("name"), path=check.arg("path"))
        if kind == "route_export":
            entity = by_route.get(check.arg("route"))
            if not entity:
                return False
            return self._node("route_export", file=f"src/frontend/{component(entity, 'page')}.tsx",
                              route=check.arg("route"))
        if kind in ("page_renders", "form_submits"):
            comp = check.arg("component")
            if f"src/frontend/{comp}.tsx" not in files:
                return False
            # A page must read its own entity's endpoint, or it would work only against a stub.
            pages = {component(t.target, "page"): api_base(t.target) for t in plan.tasks if t.kind == "page"}
            extra = {"path": pages[comp]} if kind == "page_renders" and comp in pages else {}
            return self._node(kind, file=f"src/frontend/{comp}.tsx", comp=comp, **extra)
        if kind == "shell_renders":
            pages = [t.target for t in plan.tasks if t.kind == "page"]
            return self._node(kind, routes=[page_route(p) for p in pages], headings=[pascal(p) for p in pages])

        # Everything below needs the app and a database.
        if http is None or not self.schema_ok or not self._reset_rows(plan):
            return False
        if kind in ("list_order", "fetch_one", "create_row"):
            entity = entities.get(check.arg("path"))
            if not entity:
                return False
            if kind == "create_row":
                r = http.post(check.arg("path"), json={"title": "made here"}, headers=good)
                if r.status_code != 200:
                    return False
                body = r.json()
                stored = self.sql(f"SELECT owner_id, title FROM {entity}")
                return (body.get("title") == "made here" and body.get("owner_id") == 2 and len(stored) == 1
                        and stored[0]["owner_id"] == 2 and stored[0]["title"] == "made here")
            self._seed(entity)
            if kind == "list_order":
                r = http.get(check.arg("path"), headers=good)
                return r.status_code == 200 and [x.get("id") for x in r.json()] == [2, 1]
            r = http.get(f"{check.arg('path')}/2", headers=good)
            return r.status_code == 200 and r.json().get("id") == 2 and r.json().get("title") == "row two"
        routes = list(plan.routes())
        if kind == "guard_rejects":
            return http.get(routes[0]).status_code == 401
        if kind == "routes_rejected":
            return all(http.get(r).status_code == 401 for r in check.arg("routes"))
        if kind == "protected_route":
            return http.get(routes[0]).status_code == 401 and 200 <= http.get(routes[0], headers=good).status_code < 300
        base = str(http.base_url).rstrip("/")
        if kind == "client_create_list":
            entity = check.arg("entity")
            if not any(t.kind == "client" and t.target == entity for t in plan.tasks):
                return False
            return self._node(kind, file=f"src/network/{entity}_client.ts", name=pascal(entity),
                              path=check.arg("path"), base=base)
        if kind == "form_to_page":
            entity = check.arg("entity")
            if not any(t.kind == "form" and t.target == entity for t in plan.tasks) or entity not in by_route.values():
                return False
            ok = self._node(kind, formFile=f"src/frontend/{component(entity, 'form')}.tsx",
                            formComp=component(entity, "form"), pageFile=f"src/frontend/{component(entity, 'page')}.tsx",
                            pageComp=component(entity, "page"), route=check.arg("route"), base=base)
            return ok and len(self.sql(f"SELECT 1 FROM {entity}")) == 1
        raise ValueError(f"unknown check {kind}")

    def _session_rejects(self) -> bool:
        from fastapi import HTTPException
        from starlette.requests import Request

        try:
            session = importlib.import_module("src.auth.session")
            asyncio.run(session.require_session(Request({"type": "http", "headers": []})))
        except HTTPException as e:
            return e.status_code == 401
        except Exception:  # noqa: BLE001
            return False
        return False

    def _oauth_start(self) -> bool:
        class Stub:
            headers: dict = {}

        try:
            oauth = importlib.import_module("src.auth.oauth")
            return "authorize" in asyncio.run(oauth.oauth_start(Stub()))["redirect"]
        except Exception:  # noqa: BLE001
            return False

    def run_version(self, plan: ProjectPlan, files: dict[str, str], checks: list[Check]) -> dict[Check, bool]:
        import httpx
        import uvicorn

        self.root = str(Path(self.tmp) / "app")
        subprocess.run(["rm", "-rf", self.root], check=True)
        for path, content in files.items():
            p = Path(self.root) / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self.schema_ok = self._load_schemas(plan, files)
        for name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
            del sys.modules[name]
        sys.path.insert(0, self.root)
        os.environ["DATABASE_URL"] = self.dsn

        server, thread, http = None, None, None
        if any(c.kind in SERVER_CHECKS for c in checks):
            try:
                app = importlib.import_module("src.app").app
                with socket.socket() as s:
                    s.bind(("127.0.0.1", 0))
                    port = s.getsockname()[1]
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical",
                                                       lifespan="off"))
                db = importlib.import_module("src.database.db").db

                async def serve():
                    await server.serve()
                    if db._pool is not None:
                        await db._pool.close()

                thread = threading.Thread(target=lambda: asyncio.run(serve()), daemon=True)
                thread.start()
                for _ in range(500):
                    if server.started:
                        break
                    time.sleep(0.01)
                http = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0, trust_env=False)
            except Exception:  # noqa: BLE001 - a version whose app cannot load fails its server checks
                http = None
        results: dict[Check, bool] = {}
        for check in checks:
            try:
                results[check] = bool(self._run(check, plan, files, http))
            except Exception:  # noqa: BLE001 - a crash during a check is a failed check
                results[check] = False
        if server is not None:
            server.should_exit = True
            if thread is not None:
                thread.join(timeout=5)
        if http is not None:
            http.close()
        sys.path.remove(self.root)
        return results


_runner: Runner | None = None


def _init(dsn_root: str, node_modules: str, counter) -> None:
    global _runner
    with counter.get_lock():
        counter.value += 1
        index = counter.value
    _runner = Runner(dsn_root, node_modules, index)


def score_project(job: dict) -> dict:
    plan = ProjectPlan.model_validate_json(job["plan"])
    files = {f.path: f.content for f in integrate(job["project_id"], plan, gold_artifacts(plan)).files}
    arms = {"manager": job["output"], "gold": gold_spec(plan).model_dump_json()}
    compiled: dict[str, list[dict]] = {}
    checks: dict[Check, None] = {}
    for arm, text in arms.items():
        try:
            spec = ProjectSpec.model_validate_json(text)
        except ValueError:
            compiled[arm] = []
            continue
        rows = []
        for level, task, test in spec_tests(spec):
            check = compile_test(test)
            rows.append({"id": test.id, "level": level, "task": task, "scope": test.scope, "check": check})
            if check is not None:
                checks[check] = None
        compiled[arm] = rows
    unique = list(checks)
    on_gold = _runner.run_version(plan, files, unique)
    alive = [c for c in unique if on_gold[c]]
    mutants = mutants_for(plan, files)
    caught: dict[Check, list[str]] = {c: [] for c in alive}
    for m in mutants:
        result = _runner.run_version(plan, {**files, m.path: m.content}, alive)
        for c in alive:
            if not result[c]:
                caught[c].append(m.id)
    report = {"project_id": job["project_id"], "tasks": len(plan.tasks), "mutants": [m.id for m in mutants],
              "parsed": {arm: bool(rows) for arm, rows in compiled.items()}, "arms": {}}
    for arm, rows in compiled.items():
        report["arms"][arm] = [
            {"id": r["id"], "level": r["level"], "task": r["task"], "scope": r["scope"],
             "kind": r["check"].kind if r["check"] else None, "compiled": r["check"] is not None,
             "passes_gold": bool(r["check"] and on_gold[r["check"]]),
             "caught": caught.get(r["check"], []) if r["check"] else []}
            for r in rows
        ]
    return report


def summarize(projects: list[dict], arm: str) -> dict:
    tests = [t for p in projects for t in p["arms"][arm]]
    compiled = [t for t in tests if t["compiled"]]
    passing = [t for t in compiled if t["passes_gold"]]
    counted = [t for t in passing if t["caught"]]
    catches = sorted(len(t["caught"]) for t in passing)
    all_mutants = sum(len(p["mutants"]) for p in projects if p["parsed"][arm])
    killed = sum(len({m for t in p["arms"][arm] if t["passes_gold"] for m in t["caught"]})
                 for p in projects if p["parsed"][arm])
    parsed = [p for p in projects if p["parsed"][arm]]
    tasks = sum(p["tasks"] for p in parsed)
    n = max(len(tests), 1)

    def by(field: str) -> dict:
        out = {}
        for key, count in Counter(t[field] for t in tests).items():
            group = [t for t in tests if t[field] == key]
            alive = [t for t in group if t["passes_gold"]]
            out[str(key)] = {"tests": count, "compiled": sum(t["compiled"] for t in group), "pass_gold": len(alive),
                             "counted": sum(bool(t["caught"]) for t in alive),
                             "mean_caught": round(sum(len(t["caught"]) for t in alive) / max(len(alive), 1), 2)}
        return dict(sorted(out.items()))

    return {
        "briefs": len(projects), "briefs_with_tests": len(parsed), "tests": len(tests),
        "tests_per_task": round(len(tests) / max(tasks, 1), 2),
        "unit_tests_per_task": round(sum(t["level"] == "unit" for t in tests) / max(tasks, 1), 2),
        "compile_rate": round(len(compiled) / n, 3), "pass_rate": round(len(passing) / n, 3),
        "pass_rate_of_compiled": round(len(passing) / max(len(compiled), 1), 3),
        "counted_rate": round(len(counted) / n, 3), "counted": len(counted),
        "caught_per_passing_test_mean": round(sum(catches) / max(len(catches), 1), 2),
        "caught_per_passing_test_median": catches[len(catches) // 2] if catches else 0,
        "passing_tests_catching_nothing": sum(c == 0 for c in catches),
        "mutants": all_mutants, "mutants_killed": killed,
        "mutation_score": round(killed / max(all_mutants, 1), 3),
        "by_level": by("level"), "by_kind": by("kind"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--node-modules", required=True)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    gold = {p.id: p for p in generate_varied(100, "dev", SEED)}
    jobs = []
    for line in Path(args.raw).read_text().splitlines():
        row = json.loads(line)
        jobs.append({"project_id": row["project_id"], "output": row["output"],
                     "plan": gold[row["project_id"]].plan.model_dump_json()})
    if args.limit:
        jobs = jobs[:args.limit]
    ctx = get_context("spawn")
    counter = ctx.Value("i", 0)
    t0 = time.time()
    with ctx.Pool(args.workers, initializer=_init, initargs=(args.dsn, args.node_modules, counter)) as pool:
        projects = []
        for i, report in enumerate(pool.imap_unordered(score_project, jobs), 1):
            projects.append(report)
            print(f"{i}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    out = {"manager": summarize(projects, "manager"), "gold_control": summarize(projects, "gold"),
           "seconds": round(time.time() - t0, 1), "projects": projects}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out))
    print(json.dumps({k: out[k] for k in ("manager", "gold_control", "seconds")}, indent=1))


if __name__ == "__main__":
    main()
