FROM python:3.14-slim AS dependencies
WORKDIR /build
ENV PDM_CHECK_UPDATE=false
RUN pip install --no-cache-dir "pdm>=2.26,<3" \
    && python -m venv /opt/venv
COPY pyproject.toml pdm.lock ./
RUN pdm use -f /opt/venv/bin/python && pdm sync --prod --no-editable

FROM python:3.14-slim
ENV PATH="/opt/venv/bin:${PATH}" \
    DJANGO_SETTINGS_MODULE=app.settings.prod \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin django \
    && mkdir -p /app/staticfiles /var/lib/celery \
    && chown -R django:django /app/staticfiles /var/lib/celery
COPY --from=dependencies /opt/venv /opt/venv
COPY app/ app/
COPY core/ core/
COPY manage.py ./
USER django
EXPOSE 8000
CMD ["gunicorn", "app.wsgi:application", "--bind=0.0.0.0:8000", "--access-logfile=-", "--access-logformat=%(m)s %(U)s %(s)s %(L)s", "--timeout=30", "--forwarded-allow-ips="]
