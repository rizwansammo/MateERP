# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Official invoice/receipt PDFs are rendered by WeasyPrint (pango + harfbuzz).
# Document fonts are vendored under apps/documents/assets/fonts.
RUN apt-get update     && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core     && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data/storage && chown app:app /data/storage
WORKDIR /app

# Private document storage (company branding assets). Mounted as a named
# volume; never served directly — only through authorised API endpoints.
ENV PRIVATE_STORAGE_ROOT=/data/storage

COPY requirements/ requirements/


FROM base AS dev
RUN pip install -r requirements/dev.txt
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM base AS prod
RUN pip install -r requirements/base.txt
COPY --chown=app:app . .
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
