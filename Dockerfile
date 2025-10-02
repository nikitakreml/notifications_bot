# syntax=docker/dockerfile:1.6
FROM python:3.13-slim

# базовые пакеты + утилита для работы с SQLite из командной строки
RUN apt-get update && apt-get install -y --no-install-recommends \
      tzdata ca-certificates \
      sqlite3 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# зависимости (кэшируем слой)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# код приложения (благодаря .dockerignore, лишнее не копируется)
COPY . .

# таймзона процесса (можно переопределить через env)
ENV TZ=Europe/Berlin

# непривилегированный пользователь по умолчанию
RUN useradd -m -u 10001 -s /usr/sbin/nologin appuser
USER appuser

# точка входа — ваш main.py
CMD ["python", "main.py"]