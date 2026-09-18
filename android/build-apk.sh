#!/usr/bin/env bash
# Build the Basket Watch APK on Linux or macOS.
# Needs: Python 3, JDK 17, and the Android SDK (ANDROID_HOME set, platform 34).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/3] Rebuilding the dashboard from data/receipts ..."
python3 scripts/build_dashboard.py

echo "[2/3] Bundling the dashboard into the app ..."
mkdir -p android/app/src/main/assets
if [ -f dashboard/local.html ]; then
  echo "    using dashboard/local.html — this build carries your API key, do not share it"
  cp dashboard/local.html android/app/src/main/assets/index.html
else
  cp dashboard/index.html android/app/src/main/assets/index.html
fi

echo "[3/3] Building the APK ..."
cd android
./gradlew assembleDebug

echo
echo "Done. The APK is at:"
echo "   $PWD/app/build/outputs/apk/debug/app-debug.apk"
