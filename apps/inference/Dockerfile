# Service d'inférence (V0). PaddlePaddle ne publie de paquet Linux que pour x86_64.
FROM --platform=linux/amd64 python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# libgl1 et libglib2.0-0 : opencv-contrib-python (imposé par paddlex) ; libgomp1 : Paddle.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra ocr --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra ocr

RUN useradd --create-home --uid 10001 app
USER app
ENV HOME=/home/app PATH=/app/.venv/bin:$PATH
# Modèles téléchargés à la construction : le conteneur démarre sans accès réseau.
RUN python -m inference.api.warmup

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "inference.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
