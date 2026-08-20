#!/usr/bin/env bash
set -euo pipefail

# Pinned Flutter SDK — Render Python runtime does not include Flutter.
FLUTTER_VERSION="${FLUTTER_VERSION:-3.29.3}"
FLUTTER_ARCHIVE="flutter_linux_${FLUTTER_VERSION}-stable.tar.xz"
FLUTTER_URL="https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/${FLUTTER_ARCHIVE}"

echo "==> Installing Python dependencies"
pip install -r requirements.txt

echo "==> Building Flutter Web (${FLUTTER_VERSION})"
cd ../app
curl -fsSL "${FLUTTER_URL}" -o "${FLUTTER_ARCHIVE}"
tar xf "${FLUTTER_ARCHIVE}"
export PATH="$PWD/flutter/bin:$PATH"
flutter config --enable-web
flutter pub get
flutter build web --release

echo "==> Copying web build into backend/static/web"
mkdir -p ../backend/static/web
rm -rf ../backend/static/web/*
cp -r build/web/. ../backend/static/web/

echo "==> Cleaning Flutter SDK archive from slug"
rm -rf flutter "${FLUTTER_ARCHIVE}"

echo "==> Build complete"
