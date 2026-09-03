FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=core.settings

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn core.wsgi:application -b 0.0.0.0:8000 --workers 2 --timeout 120"]
