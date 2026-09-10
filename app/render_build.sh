#!/usr/bin/env bash
set -euo pipefail

# Pinned Flutter SDK for Render static site — always download fresh (no cache reuse).
FLUTTER_VERSION="${FLUTTER_VERSION:-3.35.3}"
FLUTTER_ARCHIVE="flutter_linux_${FLUTTER_VERSION}-stable.tar.xz"
FLUTTER_URL="https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/${FLUTTER_ARCHIVE}"
FLUTTER_DIR="flutter_${FLUTTER_VERSION}"

 echo "==> Preparing Flutter ${FLUTTER_VERSION} for web build"
rm -rf flutter flutter_* "${FLUTTER_ARCHIVE}"
curl -fsSL "${FLUTTER_URL}" -o "${FLUTTER_ARCHIVE}"
tar xf "${FLUTTER_ARCHIVE}"
mv flutter "${FLUTTER_DIR}"
export PATH="$PWD/${FLUTTER_DIR}/bin:$PATH"

echo "==> Flutter version (must be ${FLUTTER_VERSION})"
flutter --version

flutter config --enable-web
flutter pub get

API_BASE_URL="${API_BASE_URL:-}"
if [[ -z "${API_BASE_URL}" ]]; then
  echo "ERROR: API_BASE_URL must be configured for staging builds" >&2
  exit 1
fi

echo "==> Building Flutter web against configured staging API"
flutter build web --release --dart-define="API_BASE_URL=${API_BASE_URL}"

echo "==> Cleaning Flutter SDK from build workspace"
rm -rf "${FLUTTER_DIR}" "${FLUTTER_ARCHIVE}"

echo "==> Web build complete"
