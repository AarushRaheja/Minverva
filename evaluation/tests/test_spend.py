import json

import pytest

from evaluation.adapters.model_interface import OllamaChat
from evaluation.runner import orchestrator as o
from evaluation.runner.modal_bridge import Bridge, digest_problem
from evaluation.runner.spend import SpendGuard, SpendUnknown, app_cost, load_config

CFG = {"cap_usd": 20.0, "rate_usd_per_hour": 1.0, "reporting_lag_hours": 1.5, "refresh_seconds": 300, "max_stale_seconds": 900,
       "model": "m", "digest_prefix": "abc"}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def guard(value=0.0, clock=None):
    return SpendGuard(CFG, read=lambda: value, clock=clock or Clock())


def forward_counter():
    calls = []

    def forward(path, body):
        calls.append(path)
        return 200, b'{"ok":true}'

    return forward, calls


def test_config_keeps_the_promised_twenty_dollars_inside_the_credits():
    c = load_config()
    assert c["cap_usd"] == pytest.approx(20.85) and c["cap_usd"] < 30
    assert c["rate_usd_per_hour"] >= 0.80 + 4 * 0.0473 + 16 * 0.008


def test_only_apps_count():
    assert app_cost([{"object_id": "ap-1", "cost": "1.5"}, {"object_id": "vo-1", "cost": "9"}]) == 1.5


def test_blocks_at_the_cap_and_when_a_reservation_would_not_fit():
    assert guard(20.0).blocked() and not guard(10.0).blocked()
    assert guard(19.5).blocked(0.77) and not guard(19.0).blocked(0.77)


def test_counts_spend_billing_has_not_reported_yet():
    c = Clock()
    g = guard(19.0, c)
    assert not g.blocked()
    c.t += 3600  # an hour of GPU, none of it reported yet: refresh still reads 19
    assert g.spent() == pytest.approx(20.0) and g.blocked()


def test_unreported_estimate_is_limited():
    c = Clock()
    g = guard(0.0, c)
    c.t += 100 * 3600
    assert g.spent() == pytest.approx(1.5)


def test_billing_unreadable_from_the_start_blocks():
    def bad():
        raise SpendUnknown("no network")

    assert "can't read" in SpendGuard(CFG, read=bad, clock=Clock()).blocked()


def test_billing_lost_midway_blocks_once_stale():
    c = Clock()
    state = {"fail": False}

    def read():
        if state["fail"]:
            raise SpendUnknown("down")
        return 1.0

    g = SpendGuard(CFG, read=read, clock=c)
    assert not g.blocked()
    state["fail"] = True
    c.t += 600  # a read failed, but the last figure is recent enough
    assert not g.blocked()
    c.t += 400
    assert "can't read" in g.blocked()


def test_bridge_never_forwards_past_the_limit():
    forward, calls = forward_counter()
    b = Bridge(guard(25.0), forward)
    code, data = b.handle("/api/chat", b"{}")
    b.server.server_close()
    assert code == 503 and calls == [] and b.refused == 1 and "limit" in json.loads(data)["error"]


def test_bridge_forwards_chat_every_time_and_caches_status_checks():
    forward, calls = forward_counter()
    b = Bridge(guard(1.0), forward)
    for _ in range(2):
        b.handle("/api/chat", b"{}")
        b.handle("/api/version", None)
    b.server.server_close()
    assert calls == ["/api/chat", "/api/version", "/api/chat"]


def test_bridge_refuses_anything_else_such_as_pulling_or_deleting_models():
    forward, calls = forward_counter()
    b = Bridge(guard(1.0), forward)
    for path in ("/api/pull", "/api/delete", "/api/generate"):
        assert b.handle(path, b"{}")[0] == 404
    b.server.server_close()
    assert calls == []


def test_modal_failure_looks_like_an_outage_not_a_model_failure():
    def boom(path, body):
        raise ConnectionError("modal down")

    b = Bridge(guard(1.0), boom)
    assert b.handle("/api/chat", b"{}")[0] == 503
    b.server.server_close()


def test_bridge_listens_on_localhost_only_and_works_with_the_client():
    forward = lambda path, body: (200, json.dumps({"message": {"content": "hi"}, "prompt_eval_count": 1, "eval_count": 2}).encode())  # noqa: E731
    with Bridge(guard(1.0), forward) as b:
        assert b.server.server_address[0] == "127.0.0.1"
        assert OllamaChat("m", host=b.url, timeout_s=5).chat([])["tok_out"] == 2


def test_limit_turns_a_model_call_into_a_censored_trial_for_both_clients():
    from slm.llm.cli import BackendUnavailable
    from slm.llm.ollama import OllamaClient

    from evaluation.adapters.model_interface import ModelUnavailable

    with Bridge(guard(25.0), forward_counter()[0]) as b:
        with pytest.raises(ModelUnavailable):
            OllamaChat("m", host=b.url, timeout_s=5).chat([])
        with pytest.raises(BackendUnavailable):
            OllamaClient("m", base_url=b.url, timeout_s=5)._raw("s", "u", {})


def test_both_agents_read_the_same_server_setting(monkeypatch):
    from slm.llm.ollama import OllamaClient

    monkeypatch.setenv("SLM_OLLAMA_URL", "http://127.0.0.1:9/")
    assert OllamaChat("m").host == OllamaClient("m").base_url == "http://127.0.0.1:9"


def test_tool_loop_and_custom_agent_send_the_same_model_settings():
    from slm.llm.ollama import OllamaClient

    seen = {}

    class T:
        def handle_request(self, request):
            import httpx

            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"message": {"content": "{}"}})

    import httpx

    OllamaChat("m", transport=httpx.MockTransport(lambda r: (seen.update(json.loads(r.content)), httpx.Response(200, json={"message": {"content": "{}"}}))[1])).chat([])
    other = OllamaClient("m").payload("s", "u", {})
    assert seen["think"] is other["think"] is False
    assert seen["options"]["seed"] == other["options"]["seed"] and seen["options"]["temperature"] == other["options"]["temperature"]


def test_digest_mismatch_is_caught():
    tags = lambda d: json.dumps({"models": [{"name": "m", "digest": d}]}).encode()  # noqa: E731
    assert digest_problem(tags("abcdef"), CFG) is None
    assert "expected" in digest_problem(tags("zzz"), CFG)
    assert "isn't on" in digest_problem(b'{"models":[]}', CFG)


def test_modal_experiment_is_blocked_before_anything_can_wake_a_gpu(monkeypatch):
    from evaluation.runner import modal_bridge, spend

    monkeypatch.setattr(spend, "read_report", lambda count_from: 999.0)
    monkeypatch.setattr(modal_bridge, "modal_forwarder", lambda name: pytest.fail("reached Modal"))
    with pytest.raises(o.NotAllowed, match="limit"):
        o.run_experiment("functional-gate", say=lambda _: None)


def test_modal_worst_case_is_included_in_the_estimate():
    trials = o.plan_trials(o.load_experiment("functional-gate"))
    assert o.estimate(trials, 1.15)["worst_case_usd"] == pytest.approx(13.8)
    assert o.estimate(trials)["worst_case_usd"] == 0


def test_a_trial_that_would_not_fit_does_not_start(monkeypatch):
    ran = []
    monkeypatch.setattr(o, "run_trial", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(o, "RESULTS", __import__("pathlib").Path("/private/tmp/agenteval-test-results"))
    said = []
    exp = o.load_experiment("functional-gate")
    o._run(exp, yes=True, final=False, say=said.append, retry_env=True, modal_reserve=lambda b: "over the limit", modal_rate=1.15)
    assert not ran and any("over the limit" in s for s in said)
