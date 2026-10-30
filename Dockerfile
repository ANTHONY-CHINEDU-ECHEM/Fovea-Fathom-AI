# API image: builds the seed index at build time so the container answers on first start.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend:/app

RUN groupadd --system fovea && useradd --system --gid fovea --home /app fovea
WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY ingestion ./ingestion
COPY evaluation ./evaluation
RUN pip install --upgrade pip && pip install .

ARG INSTALL_ML=false
RUN if [ "$INSTALL_ML" = "true" ]; then pip install ".[ml]"; fi

RUN python -m ingestion.cli seed && chown -R fovea:fovea /app
USER fovea
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready').status == 200 else 1)"
CMD ["uvicorn", "fovea.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
