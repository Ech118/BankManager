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


def test_analyze_runs_to_completion_and_returns_the_verdict(monkeypatch):
    from pathlib import Path

    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "fixtures/mock/verdict.json").read_text()
    )
    monkeypatch.setattr(server, "RUNNER", lambda ticker, as_of, run_id: fixture)
    api = TestClient(server.create_app())
    run_id = api.post("/api/analyze", json={"ticker": "acme"}).json()[
        "run_id"
    ]  # lowercase is normalised
    r = wait_done(api, run_id)
    assert (
        r.status_code == 200
        and r.json()["ticker"] == "ACME"
        and r.json()["card"]["verdict"] == "avoid"
    )
    assert (
        api.get(f"/api/runs/{run_id}/report").status_code == 404
    )  # a verdict run has no preliminary report


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


# ------------------------------------------------------- Step 3: real Coordinator behind the server
def composed_client(monkeypatch):
    monkeypatch.setattr(server, "RUNNER", None)
    monkeypatch.setattr(server, "COMPOSITION", None)
    server.configure(lambda: InMemoryMcpClient(build_fake_server()))
    return TestClient(server.create_app())


def test_composed_run_is_preliminary_until_a_verdict_exists(monkeypatch):
    api = composed_client(monkeypatch)
    run_id = api.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    r = wait_done(api, run_id)
    assert r.status_code == 409 and r.json()["status"] == "preliminary"
    rep = api.get(f"/api/runs/{run_id}/report").json()
    assert "Preliminary report" in rep["markdown"] and "## Verdict" not in rep["markdown"]
    assert "Competitive position" in rep["markdown"] and "Financial quality" in rep["markdown"]
    assert rep["state"]["ticker"] == "ACME" and set(rep["state"]["agent_outputs"]) == {
        "financial",
        "business",
    }


def test_composed_run_streams_a_lane_for_each_agent(monkeypatch):
    api = composed_client(monkeypatch)
    run_id = api.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    with api.stream("GET", f"/api/runs/{run_id}/events") as r:
        evs = [json.loads(ln[6:]) for ln in r.iter_lines() if ln.startswith("data: ")]
    lanes = {(e["agent"], e["status"]) for e in evs}
    assert {
        ("ingest", "done"),
        ("financial", "running"),
        ("business", "running"),
        ("financial", "done"),
        ("business", "done"),
        ("run", "done"),
    } <= lanes
    assert any("tokens_in" in e for e in evs if e["agent"] in ("financial", "business"))


def test_composed_run_reports_stats_from_the_coordinator(monkeypatch):
    api = composed_client(monkeypatch)
    run_id = api.post("/api/analyze", json={"ticker": "ACME"}).json()["run_id"]
    wait_done(api, run_id)
    stats = api.get(f"/api/runs/{run_id}/stats").json()
    assert set(stats["agents"]) == {"financial", "business"} and "seconds" in stats


def test_composed_run_for_an_unknown_company_fails_with_the_reason(monkeypatch):
    api = composed_client(monkeypatch)
    run_id = api.post("/api/analyze", json={"ticker": "NOPE"}).json()["run_id"]
    r = wait_done(api, run_id)
    assert r.status_code == 422 and "no company profile" in r.json()["error"].lower()


def test_report_endpoint_404s_for_a_verdict_run_and_unknown_runs(api):
    assert api.get("/api/runs/nope/report").status_code == 404


def test_cors_origins_default_to_local_dev_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("BM_CORS_ORIGINS", raising=False)
    assert server.cors_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]
    monkeypatch.setenv("BM_CORS_ORIGINS", "https://a.example, https://b.example")
    assert server.cors_origins() == ["https://a.example", "https://b.example"]
    monkeypatch.setenv("BM_CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="explicit origins"):
        server.cors_origins()


def test_cors_allows_the_configured_origin_only(monkeypatch):
    monkeypatch.setenv("BM_CORS_ORIGINS", "https://app.example")
    api = TestClient(server.create_app())
    ok = api.options(
        "/api/analyze",
        headers={"Origin": "https://app.example", "Access-Control-Request-Method": "POST"},
    )
    bad = api.options(
        "/api/analyze",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "https://app.example"
    assert "access-control-allow-origin" not in bad.headers


def test_composition_hands_the_verifier_callable_to_the_coordinator(monkeypatch):
    seen = {}

    class Spy:
        def __init__(self, mcp, **kw):
            seen.update(kw)
            self.stats = {}

        def run_state(self, ticker, as_of):
            from orchestrator.coordinator import new_state
            from schema.contracts.common import DataQuality
            from schema.contracts.enums import Mode

            return new_state(ticker, "2026-09-19", Mode.MOCK, False, DataQuality(overall="ok"))

    monkeypatch.setattr("orchestrator.coordinator.Coordinator", Spy)
    monkeypatch.setattr(server, "RUNNER", None)
    verify = lambda claim, passage: False  # noqa: E731
    server.configure(lambda: InMemoryMcpClient(build_fake_server()), verify_claim=verify)
    server._coordinator_runner("ACME", None, "r1")
    assert seen["verify_claim"] is verify
    monkeypatch.setattr(server, "COMPOSITION", None)
