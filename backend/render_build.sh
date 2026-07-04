#!/usr/bin/env bash
set -euo pipefail

pip install -r requirements.txt

cd ../app
curl -fsSL https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.29.3-stable.tar.xz -o flutter.tar.xz
tar xf flutter.tar.xz
export PATH="$PWD/flutter/bin:$PATH"
flutter config --enable-web
flutter pub get
flutter build web --release
