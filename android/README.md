# Basket Watch for Android

A single WebView over the generated dashboard. The receipt data is baked into
the page at build time, so the app works with no network and no account.

**What is in it:** the dashboard — spending, price trends, store comparison,
Hebrew/English, currency switch.

**What is not:** the Scan and Ask screens. Those call Claude through the
artifact runtime, which only exists inside the published artifact. In the APK
they show a note explaining where to find them.

## Getting the APK

Push to any branch, or run the **Build APK** workflow by hand
(Actions → Build APK → Run workflow). The APK lands in the run's Artifacts
section as `basket-watch-apk`.

It is a debug-signed APK: installable on a phone with "install unknown apps"
allowed for your browser or file manager, but not publishable to Play. For
Play you need a release keystore and `assembleRelease` — see
`developer.android.com/studio/publish/app-signing`.

## Building locally

Needs JDK 17 and the Android SDK (`ANDROID_HOME` set, platform 34 installed).

```bash
python3 scripts/build_dashboard.py
cp dashboard/index.html android/app/src/main/assets/index.html
cd android && gradle assembleDebug
```

The APK is at `app/build/outputs/apk/debug/app-debug.apk`.

## Refreshing the data in the app

The data is a build-time snapshot. Scan new bills (Claude Code, or the
published app), rerun the workflow, and install the new APK. If you want an
app whose data updates by itself, it needs a backend — see the note in the
repository README about running this as a product.
