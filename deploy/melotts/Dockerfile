FROM python:3.9-slim

ARG MELOTTS_COMMIT=209145371cff8fc3bd60d7be902ea69cbdb7965a
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG PYTORCH_VERSION=2.2.2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    TORCH_HOME=/models/torch

ARG APT_MIRROR=
RUN set -eux; \
    if [ -n "${APT_MIRROR}" ]; then \
        sed -i \
            -e "s|http://deb.debian.org/debian-security|${APT_MIRROR}-security|g" \
            -e "s|http://deb.debian.org/debian|${APT_MIRROR}|g" \
            /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://codeload.github.com/myshell-ai/MeloTTS/tar.gz/${MELOTTS_COMMIT}', '/tmp/melotts.tar.gz')" \
    && mkdir MeloTTS \
    && tar -xzf /tmp/melotts.tar.gz --strip-components=1 -C MeloTTS \
    && rm /tmp/melotts.tar.gz \
    && cd MeloTTS \
    && python -m pip install --upgrade pip --index-url "${PIP_INDEX_URL}" \
    && python -m pip install --index-url "${PIP_INDEX_URL}" numpy==1.26.4 \
    && python -m pip install --index-url "${PYTORCH_INDEX_URL}" \
        "torch==${PYTORCH_VERSION}" "torchaudio==${PYTORCH_VERSION}" \
    && python -m pip install --index-url "${PIP_INDEX_URL}" . \
    && python -m pip install --index-url "${PIP_INDEX_URL}" fastapi==0.110.0 uvicorn==0.27.1 pydantic==2.6.3

RUN python -m pip uninstall -y unidic

COPY deploy/melotts/cleaner.py /usr/local/lib/python3.9/site-packages/melo/text/cleaner.py
COPY deploy/melotts/text_init.py /usr/local/lib/python3.9/site-packages/melo/text/__init__.py
COPY deploy/melotts/distribution.py /usr/local/lib/python3.9/site-packages/melo/text/distribution.py
COPY deploy/melotts/g2p_lazy.py /usr/local/lib/python3.9/site-packages/melo/text/g2p_lazy.py
RUN sed -i \
    -e 's/from g2p_en import G2p/from .g2p_lazy import LazyG2p/' \
    -e 's/_g2p = G2p()/_g2p = LazyG2p()/' \
    -e 's/from \.japanese import distribute_phone/from .distribution import distribute_phone/' \
    /usr/local/lib/python3.9/site-packages/melo/text/english.py
COPY deploy/melotts/service.py /opt/service.py

EXPOSE 9000
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "9000"]
