# syntax=docker/dockerfile:1.6
FROM python:3.13-slim

# базовые пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
      tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# зависимости (кэшируем слой)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код приложения
COPY . .

# таймзона процесса (можно переопределить через env)
ENV TZ=Europe/Berlin

# непривилегированный пользователь по умолчанию
RUN useradd -m -u 10001 -s /usr/sbin/nologin appuser
USER appuser

# точка входа — ваш main.py
CMD ["python", "main.py"]
