FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml setup.cfg setup.py MANIFEST.in README.md ./
COPY tvscreener ./tvscreener
COPY monitor_app.py ./monitor_app.py

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip \
    && pip install .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
VOLUME ["/app/data"]

ENTRYPOINT ["uvicorn", "monitor_app:app", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/healthz || exit 1
