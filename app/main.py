from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from app.api.routes import router
from app.core.config import get_settings, BASE_DIR
from app.core.logging import configure_logging
from app.services.audit import init_db


configure_logging()
settings = get_settings()
init_db()


app = FastAPI(title=settings.app_name, version="1.0.0")

# Prometheus metrics: request rate, latency and errors per endpoint, plus the
# agent metrics from app/rag/metrics.py, all exposed at GET /metrics
Instrumentator(excluded_handlers=["/metrics", "/static.*"]).instrument(app).expose(app, include_in_schema=False)

app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"app_name": settings.app_name})
