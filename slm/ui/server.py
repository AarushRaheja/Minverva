"""A small local web UI for the manager -> specialists -> integrator workflow. Stdlib HTTP only.

    uv run slm ui                     # http://127.0.0.1:8765

Backends:
  demo   rule planner + oracle specialists: no model, no GPU; shows the workflow end to end.
  vllm   the deployed multi-LoRA server (SLM_VLLM_URL), e.g. the Modal `slm-serve` app.
  local  trained adapters under SLM_LOCAL_ROOT (default ./out) via transformers + peft.

Planner: "manager" asks the manager SLM to plan the free-text brief; "rules" builds the reference
plan from the structured fields (entities / form / OAuth), which isolates the specialists.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from slm import contracts as C
from slm.bench.catalog import HELDOUT_TEMPLATES, TRAIN_TEMPLATES, Template_, build_plan, render_description
from slm.domains import ADAPTER, KINDS
from slm.llm.base import LLMClient
from slm.trace import Tracer

HERE = Path(__file__).parent
RESERVED = {"users", "user", "session", "oauth", "routes", "shell"}
SLUG = re.compile(r"^[a-z][a-z0-9_]{1,23}$")


# --- run state -------------------------------------------------------------------


@dataclass
class Run:
    id: str
    request: dict
    status: str = "running"  # running | done | error
    events: list[dict] = field(default_factory=list)
    artifacts: dict[str, dict] = field(default_factory=dict)  # task_id -> Artifact json
    plan: dict | None = None
    deliverable: dict | None = None
    error: str | None = None
    t0: float = field(default_factory=time.time)
    t1: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self, since: int = 0) -> dict:
        with self.lock:
            return {
                "id": self.id, "status": self.status, "error": self.error,
                "events": self.events[since:], "n_events": len(self.events),
                "artifacts": dict(self.artifacts), "plan": self.plan, "deliverable": self.deliverable,
                "wall_s": round((self.t1 or time.time()) - self.t0, 3),
            }


class RunTracer(Tracer):
    """Writes the normal JSONL trace and mirrors every event into the run for the browser."""

    def __init__(self, run: Run):
        super().__init__(run_id=f"ui-{run.id}")
        self.run = run

    def record(self, **fields):
        ev = super().record(**fields)
        d = ev.model_dump(exclude_none=True)
        with self.run.lock:
            self.run.events.append(d)
            if d.get("kind") == "plan" and d.get("ok") is False:
                self.run.error = d.get("error")
        return ev


class Capture(LLMClient):
    """Wraps a specialist client and keeps each task's artifact so the UI can show it live."""

    def __init__(self, inner: LLMClient, run: Run):
        super().__init__(inner.model, inner.tracer)
        self.inner, self.run = inner, run

    def for_model(self, model: str) -> Capture:
        inner = self.inner.for_model(model) if hasattr(self.inner, "for_model") else self.inner
        return Capture(inner, self.run)

    def _raw(self, system, user, json_schema):  # pragma: no cover - always delegated
        raise NotImplementedError

    def complete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        out = self.inner.complete(system, user, schema, caller=caller, callee=callee, ctx=ctx)
        self._keep(ctx, out)
        return out

    async def acomplete(self, system, user, schema, *, caller="user", callee="model", ctx=None):
        out = await self.inner.acomplete(system, user, schema, caller=caller, callee=callee, ctx=ctx)
        self._keep(ctx, out)
        return out

    def _keep(self, ctx, out):
        with self.run.lock:
            if isinstance(out, C.ProjectPlan):  # the manager's plan: show the graph as soon as it exists
                self.run.plan = plan_view(out)
            elif (ctx or {}).get("task_id"):
                self.run.artifacts[ctx["task_id"]] = out.model_dump()


def plan_view(plan: C.ProjectPlan) -> dict:
    return {**plan.model_dump(), "levels": plan.levels(),
            "provides": {t.id: t.provides() for t in plan.tasks}}


# --- backends --------------------------------------------------------------------


def backends() -> list[dict]:
    from slm.llm.local import local_adapters, torch_available

    url = os.environ.get("SLM_VLLM_URL")
    root = os.environ.get("SLM_LOCAL_ROOT", "out")
    found = local_adapters(root) if Path(root).exists() else {}
    if not torch_available():
        local_why = "needs torch, transformers and peft installed"
    elif not found:
        local_why = f"no trained adapters under {root}/ (run `python -m slm.train backprop`)"
    else:
        local_why = f"{len(found)} adapters under {root}/: {', '.join(sorted(found))}"
    return [
        {"id": "demo", "label": "Demo (oracle specialists)", "available": True,
         "why": "Gold artifacts and the rule planner. Shows the workflow without running a model."},
        {"id": "vllm", "label": "vLLM server", "available": bool(url),
         "why": url or "set SLM_VLLM_URL to the deployed slm-serve URL"},
        {"id": "local", "label": "Local adapters", "available": bool(found) and torch_available(),
         "why": local_why},
    ]


def make_clients(backend: str, tracer: Tracer) -> tuple[LLMClient | None, dict[str, LLMClient]]:
    if backend == "demo":
        from slm.pipeline.oracle import OracleSpecialist

        return None, {d: OracleSpecialist(tracer=tracer) for d in C.DOMAINS}
    if backend == "vllm":
        from slm.llm.vllm import VLLMLoRAClient

        manager = VLLMLoRAClient(os.environ.get("SLM_MANAGER_MODEL", C.MANAGER_BASE), tracer, max_tokens=2048)
        spec = VLLMLoRAClient(C.BASE_MODEL, tracer, max_tokens=1024)
        return manager, {d: spec.for_model(ADAPTER[d]) for d in C.DOMAINS}
    if backend == "local":
        from slm.llm.local import MANAGER, LocalClient, local_adapters

        adapters = local_adapters(os.environ.get("SLM_LOCAL_ROOT", "out"))
        manager = LocalClient(MANAGER if MANAGER in adapters else C.MANAGER_BASE, adapters, tracer,
                              max_new_tokens=2048)
        return manager, {d: LocalClient(ADAPTER[d], adapters, tracer) for d in C.DOMAINS}
    raise ValueError(f"unknown backend {backend!r}")


# --- request -> project ----------------------------------------------------------


def template_from_spec(spec: dict) -> Template_:
    """Validate the structured brief and turn it into a catalog template (for the rule planner)."""
    name = str(spec.get("name") or "").strip() or "custom app"
    entities = [str(e).strip().lower() for e in spec.get("entities") or []]
    if not 1 <= len(entities) <= 4:
        raise ValueError("give 1 to 4 entities")
    for e in entities:
        if not SLUG.match(e):
            raise ValueError(f"entity {e!r} must be a lowercase slug (letters, digits, _), 2-24 chars")
        if e in RESERVED:
            raise ValueError(f"entity {e!r} is reserved (users/session/oauth/routes/shell)")
    if len(set(entities)) != len(entities):
        raise ValueError("entities must be unique")
    form = str(spec.get("form") or entities[0]).strip().lower()
    if form not in entities:
        raise ValueError(f"the form entity {form!r} must be one of the entities")
    article = str(spec.get("article") or "").strip() or f"a {name}"
    return Template_("custom", name, article, tuple(entities), form, bool(spec.get("oauth")))


def project_from_request(req: dict, run_id: str) -> tuple[C.Project, bool]:
    """(project, use_rule_plan)."""
    backend = req.get("backend", "demo")
    planner = "rules" if backend == "demo" else req.get("planner", "manager")
    plan = None
    brief = str(req.get("brief") or "").strip()
    if planner == "rules":
        tpl = template_from_spec(req.get("spec") or {})
        plan = build_plan(tpl)
        brief = brief or render_description(tpl)
    if not brief:
        raise ValueError("write a project brief")
    if len(brief) > 4000:
        raise ValueError("brief is too long (4,000 characters max)")
    project = C.Project(id=f"ui-{run_id}", source="synthetic", split="dev", description=brief, plan=plan,
                        n_tasks=len(plan.tasks) if plan else None, depth=len(plan.levels()) if plan else None)
    return project, planner == "rules"


def start_run(req: dict, runs: dict[str, Run]) -> Run:
    """Validate synchronously (errors go back to the caller), then execute in a thread."""
    backend = req.get("backend", "demo")
    avail = {b["id"]: b for b in backends()}
    if backend not in avail:
        raise ValueError(f"unknown backend {backend!r}")
    if not avail[backend]["available"]:
        raise ValueError(f"backend {backend!r} is not available: {avail[backend]['why']}")
    run = Run(id=uuid.uuid4().hex[:8], request=req)
    project, rule_plan = project_from_request(req, run.id)
    runs[run.id] = run
    threading.Thread(target=_execute, args=(run, project, rule_plan, backend, bool(req.get("parallel", True))),
                     daemon=True).start()
    return run


def _execute(run: Run, project: C.Project, rule_plan: bool, backend: str, parallel: bool) -> None:
    from slm.pipeline.dispatch import solve_project

    tracer = RunTracer(run)
    try:
        manager, spec = make_clients(backend, tracer)
        manager = Capture(manager, run) if manager is not None else None
        spec = {d: Capture(c, run) for d, c in spec.items()}
        if rule_plan and project.plan is not None:
            with run.lock:
                run.plan = plan_view(project.plan)
        mode = "gold" if backend == "demo" else "specialists"
        plan, deliverable = asyncio.run(solve_project(
            project, manager_client=manager, specialist_clients=spec, tracer=tracer,
            gold_plan=rule_plan, mode=mode, parallel=parallel))
        with run.lock:
            if plan is not None:
                run.plan = plan_view(plan)
            if deliverable is not None:
                run.deliverable = {**deliverable.model_dump(), "ok": deliverable.ok,
                                   "failures": deliverable.failures}
            run.status = "done" if deliverable is not None else "error"
            if deliverable is None and not run.error:
                run.error = "no deliverable (see the trace)"
    except Exception as e:  # noqa: BLE001 - surfaced in the UI
        with run.lock:
            run.status, run.error = "error", f"{type(e).__name__}: {e}"
    finally:
        run.t1 = time.time()


def deliverable_zip(run: Run) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (run.deliverable or {}).get("files", []):
            z.writestr(f"{run.id}/{f['path']}", f["content"])
        checks = (run.deliverable or {}).get("checks", [])
        z.writestr(f"{run.id}/CHECKS.md", "".join(
            f"- [{'x' if c['ok'] else ' '}] {c['name']} {c.get('detail', '')}\n" for c in checks))
    return buf.getvalue()


def meta() -> dict:
    def tpl(t: Template_, split: str) -> dict:
        return {"id": t.id, "name": t.name, "article": t.article, "entities": list(t.entities),
                "form": t.form, "oauth": t.oauth, "split": split, "brief": render_description(t)}

    return {
        "backends": backends(),
        "templates": [tpl(t, "train") for t in TRAIN_TEMPLATES] + [tpl(t, "held-out") for t in HELDOUT_TEMPLATES],
        "domains": {d: list(KINDS[d]) for d in C.DOMAINS},
        "adapters": dict(ADAPTER),
    }


# --- HTTP ------------------------------------------------------------------------


def make_handler(runs: dict[str, Run]):
    class Handler(BaseHTTPRequestHandler):
        server_version = "slm-ui/1"

        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            path, _, query = self.path.partition("?")
            params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            if path in ("/", "/index.html"):
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/meta":
                return self._json(meta())
            m = re.fullmatch(r"/api/runs/([0-9a-f]{8})(/zip)?", path)
            if m and m.group(1) in runs:
                run = runs[m.group(1)]
                if m.group(2):
                    return self._send(200, deliverable_zip(run), "application/zip",
                                      {"Content-Disposition": f'attachment; filename="slm-{run.id}.zip"'})
                return self._json(run.snapshot(int(params.get("since", 0) or 0)))
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):  # noqa: N802
            if self.path != "/api/runs":
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(min(n, 100_000)) or b"{}")
                run = start_run(req, runs)
            except (ValueError, json.JSONDecodeError) as e:
                return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            return self._json({"run_id": run.id})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    runs: dict[str, Run] = {}
    httpd = ThreadingHTTPServer((host, port), make_handler(runs))
    print(f"slm ui on http://{host}:{port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
