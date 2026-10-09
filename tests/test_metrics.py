"""The /metrics endpoint exists and exposes the agent metrics."""
from fastapi.testclient import TestClient

from app.main import app
from app.rag import metrics


def test_metrics_endpoint_is_up():
    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_agent_metrics_are_exposed():
    metrics.ANSWER_PATH.labels(path="kb").inc()
    metrics.QUERY_REWRITES.inc()
    body = TestClient(app).get("/metrics").text
    assert 'agent_answer_path_total{path="kb"}' in body
    assert "agent_query_rewrites_total" in body
    assert "agent_step_seconds" in body or "agent_questions_total" in body


def test_timed_records_duration_and_errors():
    @metrics.timed("unit_test_step")
    def boom():
        raise ValueError("fail")

    try:
        boom()
    except ValueError:
        pass
    errors = metrics.STEP_ERRORS.labels(step="unit_test_step")._value.get()
    assert errors >= 1
