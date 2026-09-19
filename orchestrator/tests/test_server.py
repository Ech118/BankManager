"""HTTP API: start a run, stream per-agent SSE events, fetch the result, validate input."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from orchestrator import server
from orchestrator.coordinator import Coordinator
from orchestrator.mcp_client import InMemoryMcpClient
from tests.e2e.support.fake_mcp import build_fake_server


def coordinator_runner(ticker, as_of, run_id):
    """A runner that drives the real Coordinator (so the events are the real ones)."""
    mcp = InMemoryMcpClient(build_fake_server())
    try:
        return Coordinator(mcp, run_id=run_id).run_state(ticker, as_of).model_dump(mode="json")
    finally:
        mcp.close()


@pytest.fixture()
def api(monkeypatch):
    monkeypatch.setattr(server, "RUNNER", coordinator_runner)
    return TestClient(server.create_app())


def wait_done(api, run_id, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = api.get(f"/api/runs/{run_id}")
        if r.status_code != 202:
            return r
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_health_and_config(api):
    assert api.get("/api/health").json() == {"ok": True}
    assert set(api.get("/api/config").json()) == {"mode", "llm"}


def test_analyze_runs_to_completion_and_returns_the_result(api):
    run_id = api.post("/api/analyze", json={"ticker": "acme"}).json()[
        "run_id"
    ]  # lowercase is normalised
    r = wait_done(api, run_id)
    assert r.status_code == 200 and r.json()["ticker"] == "ACME"


def test_sse_streams_a_lane_per_stage_then_done(api):
    run_id = api.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    evs = []
    with api.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        evs = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    seq = [(e["agent"], e["status"]) for e in evs]
    assert seq[:4] == [
        ("run", "running"),
        ("ingest", "running"),
        ("ingest", "done"),
        ("financial", "running"),
    ]
    assert ("financial", "done") in seq and seq[-1] == ("run", "done")
    assert all({"agent", "status", "ts", "run_id"} <= set(e) for e in evs)
    done = next(e for e in evs if e["agent"] == "financial" and e["status"] == "done")
    assert "tokens_in" in done


def test_late_subscriber_gets_the_full_history(api):
    run_id = api.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    wait_done(api, run_id)
    with api.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert len([ln for ln in r.iter_lines() if ln.startswith("data: ")]) >= 6


@pytest.mark.parametrize("bad", ["", "TOOLONGX", "AA;DROP", "../etc", "a b", "123"])
def test_invalid_ticker_is_rejected_before_any_work(api, bad):
    assert api.post("/api/analyze", json={"ticker": bad}).status_code == 422


def test_invalid_as_of_is_rejected(api):
    assert (
        api.post("/api/analyze", json={"ticker": "ACME", "as_of": "yesterday"}).status_code == 422
    )


def test_a_failed_run_reports_the_reason_and_closes_the_stream(monkeypatch):
    def boom(ticker, as_of, run_id):
        raise ValueError("Financial institution (SIC 6022). Banks are out of scope for v1.")

    monkeypatch.setattr(server, "RUNNER", boom)
    api = TestClient(server.create_app())
    run_id = api.post("/api/analyze", json={"ticker": "BANKX"}).json()["run_id"]
    r = wait_done(api, run_id)
    assert (
        r.status_code == 422
        and r.json()["status"] == "failed"
        and "Banks are out of scope" in r.json()["error"]
    )
    with api.stream("GET", f"/api/runs/{run_id}/events") as ev:
        last = [json.loads(ln[6:]) for ln in ev.iter_lines() if ln.startswith("data: ")][-1]
    assert (last["agent"], last["status"]) == ("run", "failed")


def test_unknown_run_is_404(api):
    for path in ("", "/events", "/stats"):
        assert api.get(f"/api/runs/nope{path}").status_code == 404
