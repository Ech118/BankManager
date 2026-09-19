"""End-to-end over HTTP in mock mode: POST -> SSE events -> verdict."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from agents import validate
from orchestrator.server import app

client = TestClient(app)


def wait_done(run_id, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/runs/{run_id}")
        if r.status_code != 202:
            return r
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_health_and_config():
    assert client.get("/api/health").json() == {"ok": True}
    assert set(client.get("/api/config").json()) == {"mode", "llm"}


def test_analyze_returns_schema_valid_verdict_with_disclaimer():
    run_id = client.post("/api/analyze", json={"ticker": "acme"}).json()["run_id"]   # lowercase is normalised
    r = wait_done(run_id)
    assert r.status_code == 200
    v = r.json()
    validate.check(v, "verdict.json")
    assert v["ticker"] == "ACME" and v["disclaimer"] and v["audit"]["passed"]


def test_sse_streams_one_lane_per_agent_then_done():
    run_id = client.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    agents = {e["agent"] for e in events}
    assert {"scope", "data", "calc", "scout", "forensic", "business", "balance_sheet", "valuation",
            "red_team", "synthesizer", "audit", "run"} <= agents
    assert events[-1] == {**events[-1], "agent": "run", "status": "done"}
    assert all({"agent", "status", "ts"} <= set(e) for e in events)
    for a in ("forensic", "valuation"):
        st = [e["status"] for e in events if e["agent"] == a]
        assert st[0] == "started" and st[-1] == "done"


def test_late_subscriber_gets_full_replay():
    run_id = client.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    wait_done(run_id)
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        lines = [l for l in r.iter_lines() if l.startswith("data: ")]
    assert len(lines) >= 12


@pytest.mark.parametrize("bad", ["", "TOOLONGX", "AA;DROP", "../etc", "a b", "123"])
def test_invalid_ticker_rejected_before_any_work(bad):
    assert client.post("/api/analyze", json={"ticker": bad}).status_code == 422


def test_invalid_as_of_rejected():
    assert client.post("/api/analyze", json={"ticker": "ACME", "as_of": "yesterday"}).status_code == 422


def test_out_of_scope_ticker_reports_a_clear_failure_reason():
    run_id = client.post("/api/analyze", json={"ticker": "BANKX"}).json()["run_id"]
    r = wait_done(run_id)
    assert r.status_code == 422 and r.json()["status"] == "failed" and "Banks" in r.json()["error"]


def test_unknown_run_is_404():
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/nope/events").status_code == 404


def test_stats_endpoint_reports_cost_and_latency():
    run_id = client.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    wait_done(run_id)
    s = client.get(f"/api/runs/{run_id}/stats").json()
    assert {"seconds", "input_tokens", "output_tokens", "cost_usd_estimate", "agents"} <= set(s)
