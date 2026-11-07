"""The web UI: request validation, a full demo run, and the HTTP API (all offline)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO

import pytest

from slm.ui import server as S

SPEC = {"name": "plant tracker", "entities": ["plant", "garden"], "form": "plant", "oauth": True}


def wait(run, timeout=10.0):
    t = time.time()
    while run.status == "running" and time.time() - t < timeout:
        time.sleep(0.02)
    return run


@pytest.mark.parametrize("bad,msg", [
    ({"entities": []}, "1 to 4"),
    ({"entities": ["Plant!"]}, "slug"),
    ({"entities": ["users"]}, "reserved"),
    ({"entities": ["a_b", "a_b"]}, "unique"),
    ({"entities": ["plant"], "form": "tree"}, "form entity"),
])
def test_spec_validation(bad, msg):
    with pytest.raises(ValueError, match=msg):
        S.template_from_spec(bad)


def test_demo_run_on_a_custom_project_passes_every_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # traces go to ./.slm
    runs: dict = {}
    run = wait(S.start_run({"backend": "demo", "spec": SPEC}, runs))
    snap = run.snapshot()
    assert snap["status"] == "done", snap["error"]
    assert snap["deliverable"]["ok"] and not snap["deliverable"]["failures"]
    ids = {t["id"] for t in snap["plan"]["tasks"]}
    assert set(snap["artifacts"]) == ids  # every task's artifact was captured
    kinds = [e["kind"] for e in snap["events"]]
    assert kinds.count("final") == 1 and kinds.count("task") == len(ids)
    assert any("garden" in f["path"] for f in snap["deliverable"]["files"])
    with zipfile.ZipFile(BytesIO(S.deliverable_zip(run))) as z:
        assert f"{run.id}/CHECKS.md" in z.namelist()


def test_demo_forces_rule_planner_and_unavailable_backends_refuse(monkeypatch):
    monkeypatch.delenv("SLM_VLLM_URL", raising=False)
    project, rules = S.project_from_request({"backend": "demo", "planner": "manager", "spec": SPEC}, "x")
    assert rules and project.plan is not None
    with pytest.raises(ValueError, match="not available"):
        S.start_run({"backend": "vllm", "brief": "anything"}, {})
    with pytest.raises(ValueError, match="brief"):
        S.project_from_request({"backend": "vllm", "planner": "manager", "brief": " "}, "x")


def test_manager_plan_shows_up_live_with_a_fake_manager(tmp_path, monkeypatch):
    """A model backend: the manager's plan is captured and dispatched (fake manager + oracle specialists)."""
    from slm.llm.fake import FakeClient
    from slm.pipeline.oracle import OracleSpecialist

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(S, "backends", lambda: [{"id": "fake", "available": True, "why": ""}])
    monkeypatch.setattr(S, "make_clients", lambda b, tr: (
        FakeClient(tracer=tr), {d: OracleSpecialist(tracer=tr) for d in S.C.DOMAINS}))
    run = wait(S.start_run({"backend": "fake", "planner": "manager", "brief": "a notes app"}, {}))
    snap = run.snapshot()
    assert snap["plan"]["name"] == "notes app" and snap["plan"]["levels"]
    assert snap["deliverable"] is not None


def test_http_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.make_handler({}))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "<title>SLM Workbench</title>" in html
        meta = json.loads(urllib.request.urlopen(base + "/api/meta").read())
        assert {b["id"] for b in meta["backends"]} == {"demo", "vllm", "local"}
        assert any(t["split"] == "held-out" for t in meta["templates"])

        def post(body):
            req = urllib.request.Request(base + "/api/runs", json.dumps(body).encode(),
                                         {"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req).read())

        with pytest.raises(urllib.error.HTTPError) as e:
            post({"backend": "demo", "spec": {"entities": []}})
        assert e.value.code == 400
        rid = post({"backend": "demo", "spec": SPEC})["run_id"]
        for _ in range(200):
            snap = json.loads(urllib.request.urlopen(f"{base}/api/runs/{rid}").read())
            if snap["status"] != "running":
                break
            time.sleep(0.02)
        assert snap["status"] == "done" and snap["deliverable"]["ok"]
        since = json.loads(urllib.request.urlopen(f"{base}/api/runs/{rid}?since=3").read())
        assert len(since["events"]) == snap["n_events"] - 3
        z = urllib.request.urlopen(f"{base}/api/runs/{rid}/zip").read()
        assert zipfile.ZipFile(BytesIO(z)).namelist()
    finally:
        httpd.shutdown()
