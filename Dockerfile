FROM python:3.14-slim

ENV PDM_CHECK_UPDATE=false \
    PDM_VENV_IN_PROJECT=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir "pdm>=2.26,<3"

COPY pyproject.toml pdm.lock ./
RUN pdm sync --prod --frozen

COPY . ./

RUN useradd --create-home --shell /usr/sbin/nologin django \
    && chown -R django:django /app

USER django

EXPOSE 8000

CMD ["pdm", "run", "python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
