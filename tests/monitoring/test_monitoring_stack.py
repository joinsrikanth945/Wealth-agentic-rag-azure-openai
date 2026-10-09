"""Integration tests for the monitoring stack: app /metrics -> Prometheus -> Grafana.

They need the docker-compose stack running, so plain `pytest` skips them.
Run them with (PowerShell):

    docker compose up -d --build
    $env:MONITORING_TEST = "1"
    pytest tests/monitoring -v

Optional settings (defaults match docker-compose.yml):
    APP_URL           http://localhost:8080
    PROMETHEUS_URL    http://localhost:9090
    GRAFANA_URL       http://localhost:3000
    GRAFANA_USER      admin
    GRAFANA_PASSWORD  change-me

One test asks the agent "Hello" (the direct path: one or two small LLM calls,
a fraction of a cent) and checks that the question shows up in Prometheus
and in Grafana.
"""
import os
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("MONITORING_TEST") != "1",
    reason="Set MONITORING_TEST=1 and start `docker compose up -d` to run the monitoring tests",
)

APP_URL = os.getenv("APP_URL", "http://localhost:8080").rstrip("/")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
GRAFANA_AUTH = (os.getenv("GRAFANA_USER", "admin"), os.getenv("GRAFANA_PASSWORD", "change-me"))

APP_JOB = "agentic-rag"            # job_name in monitoring/prometheus/prometheus.yml
DATASOURCE_UID = "prometheus"      # uid in monitoring/grafana/provisioning/datasources/prometheus.yml
DASHBOARD_UID = "agentic-rag"      # uid in monitoring/grafana/provisioning/dashboards/agentic-rag.json

# Prometheus scrapes every 15 s, so allow a few scrape cycles
SCRAPE_WAIT_SECONDS = 60


# ---------- helpers ----------

def prom_query(expr: str) -> float:
    """Run an instant PromQL query and return the first value (0 if no data)."""
    r = httpx.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=10)
    r.raise_for_status()
    body = r.json()
    assert body["status"] == "success", body
    result = body["data"]["result"]
    return float(result[0]["value"][1]) if result else 0.0


def wait_until(condition, timeout=SCRAPE_WAIT_SECONDS, interval=3):
    """Poll `condition()` until it returns a truthy value or the timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    return condition()


def grafana(method: str, path: str, **kwargs) -> httpx.Response:
    return httpx.request(method, f"{GRAFANA_URL}{path}", auth=GRAFANA_AUTH, timeout=15, **kwargs)


# ---------- 1. The app exposes metrics ----------

def test_app_metrics_endpoint_exposes_agent_metrics():
    r = httpx.get(f"{APP_URL}/metrics", timeout=30)
    assert r.status_code == 200
    for name in ("http_requests_total", "agent_questions_total", "agent_answer_path_total"):
        assert name in r.text, f"{name} missing from /metrics"


# ---------- 2. Prometheus is up and scraping the app ----------

def test_prometheus_is_ready():
    r = httpx.get(f"{PROMETHEUS_URL}/-/ready", timeout=10)
    assert r.status_code == 200


def test_prometheus_config_is_valid_and_loaded():
    r = httpx.get(f"{PROMETHEUS_URL}/api/v1/status/config", timeout=10)
    assert r.status_code == 200
    assert f"job_name: {APP_JOB}" in r.json()["data"]["yaml"]


def test_prometheus_scrapes_the_app():
    def app_target_health():
        r = httpx.get(f"{PROMETHEUS_URL}/api/v1/targets", timeout=10)
        r.raise_for_status()
        targets = [t for t in r.json()["data"]["activeTargets"] if t["labels"].get("job") == APP_JOB]
        return targets[0]["health"] if targets else None

    health = wait_until(lambda: app_target_health() == "up")
    assert health, f"Prometheus target '{APP_JOB}' is not UP (last state: {app_target_health()})"
    assert prom_query(f'up{{job="{APP_JOB}"}}') == 1


# ---------- 3. Grafana is up and provisioned as code ----------

def test_grafana_is_healthy():
    r = httpx.get(f"{GRAFANA_URL}/api/health", timeout=10)
    assert r.status_code == 200
    assert r.json().get("database") == "ok"


def test_grafana_login_works():
    r = grafana("GET", "/api/user")
    assert r.status_code == 200, "Grafana login failed: check GRAFANA_USER / GRAFANA_PASSWORD"


def test_grafana_prometheus_datasource_is_provisioned():
    r = grafana("GET", f"/api/datasources/uid/{DATASOURCE_UID}")
    assert r.status_code == 200, "Prometheus data source not provisioned"
    ds = r.json()
    assert ds["type"] == "prometheus"
    assert ds["url"] == "http://prometheus:9090"
    assert ds["isDefault"] is True


def test_grafana_can_reach_prometheus():
    r = grafana("GET", f"/api/datasources/uid/{DATASOURCE_UID}/health")
    assert r.status_code == 200
    assert r.json().get("status") == "OK", r.json()


def test_grafana_dashboard_is_provisioned():
    r = grafana("GET", f"/api/dashboards/uid/{DASHBOARD_UID}")
    assert r.status_code == 200, "Agentic RAG dashboard not provisioned"
    dashboard = r.json()["dashboard"]
    assert dashboard["title"] == "Agentic RAG - Overview"
    titles = {p["title"] for p in dashboard["panels"]}
    for expected in ("Answer path", "p95 duration by step", "Error rate (5xx)"):
        assert expected in titles, f"Panel '{expected}' missing"


# ---------- 4. End to end: a question flows app -> Prometheus -> Grafana ----------

def test_question_flows_through_to_prometheus_and_grafana():
    questions_before = prom_query(f'sum(agent_questions_total{{job="{APP_JOB}"}})')
    direct_before = prom_query(f'sum(agent_answer_path_total{{job="{APP_JOB}",path="direct"}})')

    # Ask a greeting: the cheapest path (direct answer, no retrieval)
    r = httpx.post(f"{APP_URL}/api/chat", json={"question": "Hello"}, timeout=120)
    assert r.status_code == 200, f"/api/chat failed: {r.text[:300]}"
    assert r.json()["source_used"] == "direct"

    # Prometheus picks up the new counts within a few scrapes
    questions_after = wait_until(
        lambda: (v := prom_query(f'sum(agent_questions_total{{job="{APP_JOB}"}})')) > questions_before and v
    )
    assert questions_after > questions_before, "agent_questions_total did not increase in Prometheus"
    direct_after = prom_query(f'sum(agent_answer_path_total{{job="{APP_JOB}",path="direct"}})')
    assert direct_after > direct_before, "direct answer path not counted"

    # Grafana returns the same data through its Prometheus data source
    now_ms = int(time.time() * 1000)
    r = grafana("POST", "/api/ds/query", json={
        "from": str(now_ms - 15 * 60 * 1000),
        "to": str(now_ms),
        "queries": [{
            "refId": "A",
            "datasource": {"type": "prometheus", "uid": DATASOURCE_UID},
            "expr": f'sum(agent_questions_total{{job="{APP_JOB}"}})',
            "instant": True,
        }],
    })
    assert r.status_code == 200, r.text[:300]
    frames = r.json()["results"]["A"]["frames"]
    assert frames, "Grafana returned no data for agent_questions_total"
    values = frames[0]["data"]["values"][-1]
    assert values and values[-1] >= questions_after
