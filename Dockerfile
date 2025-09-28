# syntax=docker/dockerfile:1.6
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Moscow

WORKDIR /app

# зависимости отдельно => лучше кэш
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код приложения
COPY . .

# команда по умолчанию (compose всё равно задаёт command, но дублировать не вредно)
CMD ["python", "-X", "utf8", "main.py"]
