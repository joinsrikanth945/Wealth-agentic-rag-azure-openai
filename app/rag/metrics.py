"""Prometheus metrics for the agentic RAG workflow.

Exposed at GET /metrics by prometheus-fastapi-instrumentator (see app/main.py).
"""
import time
from functools import wraps

from prometheus_client import Counter, Histogram

# Questions sent to the agent (one per ask() call)
QUESTIONS = Counter(
    "agent_questions_total",
    "Questions received by the agent",
)

# Which way the agent answered: kb, web, direct or insufficient
ANSWER_PATH = Counter(
    "agent_answer_path_total",
    "Answer path taken by the agent",
    ["path"],
)

# How often weak evidence forced a query rewrite and retry
QUERY_REWRITES = Counter(
    "agent_query_rewrites_total",
    "Query rewrites triggered by weak evidence",
)

# Evidence grading results (kb / web, good / weak)
EVIDENCE_GRADE = Counter(
    "agent_evidence_grade_total",
    "Evidence grading results",
    ["source", "grade"],
)

# Time spent in each workflow step (LLM calls, retrieval, web search)
STEP_SECONDS = Histogram(
    "agent_step_seconds",
    "Duration of each agent workflow step",
    ["step"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)

# Errors inside workflow steps
STEP_ERRORS = Counter(
    "agent_step_errors_total",
    "Exceptions raised inside agent workflow steps",
    ["step"],
)


def timed(step: str):
    """Decorator: record duration and errors of a workflow node."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            except Exception:
                STEP_ERRORS.labels(step=step).inc()
                raise
            finally:
                STEP_SECONDS.labels(step=step).observe(time.perf_counter() - start)
        return wrapper
    return decorator
