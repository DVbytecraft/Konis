FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pré-collecter les fichiers statiques (même logique que Dockerfile.prod)
RUN mkdir -p /app/staticfiles && \
    DJANGO_SETTINGS_MODULE=konis.settings.prod \
    DJANGO_SECRET_KEY=build-dummy-not-for-production \
    DATABASE_URL=postgresql://build:build@localhost/build \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "konis.wsgi", "-b", "0.0.0.0:8000", "-w", "2", "--timeout", "120"]
