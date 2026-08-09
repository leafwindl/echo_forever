FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY Echo-backend/requirements.txt /app/Echo-backend/requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN python -m pip install --upgrade pip --index-url "${PIP_INDEX_URL}" \
    && python -m pip install --index-url "${PIP_INDEX_URL}" -r /app/Echo-backend/requirements.txt

COPY Echo-backend /app/Echo-backend
COPY scripts /app/scripts
COPY app/assets/character /app/assets/character
COPY assets/sticker /app/assets/sticker

WORKDIR /app/Echo-backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
