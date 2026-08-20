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
flutter build web --release

echo "==> Cleaning Flutter SDK from build workspace"
rm -rf "${FLUTTER_DIR}" "${FLUTTER_ARCHIVE}"

echo "==> Web build complete"
