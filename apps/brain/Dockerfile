FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libtiff-tools \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY api api
COPY migrations migrations
COPY models models
COPY services services

RUN useradd --system --uid 10001 --home /nonexistent --shell /usr/sbin/nologin brain \
    && chown -R brain:brain /app

USER brain

EXPOSE 8092

CMD ["python", "-m", "api.server"]
