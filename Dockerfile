# Multi-stage: Flutter Web build + FastAPI runtime (optional local parity with Render).
# No secrets — configure via environment variables at run time.

ARG FLUTTER_VERSION=3.29.3

FROM debian:bookworm-slim AS flutter-builder
ARG FLUTTER_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates xz-utils git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY app/pubspec.yaml app/pubspec.lock ./app/
COPY app/analysis_options.yaml ./app/
COPY app/web ./app/web
COPY app/lib ./app/lib
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" -o flutter.tar.xz \
    && tar xf flutter.tar.xz \
    && export PATH="/src/flutter/bin:$PATH" \
    && cd app \
    && flutter config --enable-web \
    && flutter pub get \
    && flutter build web --release

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=flutter-builder /src/app/build/web ./static/web
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
