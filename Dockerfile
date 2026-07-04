FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY Echo-backend/requirements.txt /app/Echo-backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/Echo-backend/requirements.txt

COPY Echo-backend /app/Echo-backend

WORKDIR /app/Echo-backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
