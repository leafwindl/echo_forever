FROM python:3.9-slim

ARG MELOTTS_COMMIT=209145371cff8fc3bd60d7be902ea69cbdb7965a
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    TORCH_HOME=/models/torch

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone https://github.com/myshell-ai/MeloTTS.git \
    && cd MeloTTS \
    && git checkout "${MELOTTS_COMMIT}" \
    && python -m pip install --upgrade pip --index-url "${PIP_INDEX_URL}" \
    && python -m pip install --index-url "${PIP_INDEX_URL}" . \
    && python -m pip install --index-url "${PIP_INDEX_URL}" fastapi==0.110.0 uvicorn==0.27.1 pydantic==2.6.3

COPY deploy/melotts/service.py /opt/service.py

EXPOSE 9000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "9000"]
