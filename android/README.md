# Basket Watch for Android

A single WebView over the generated dashboard. The receipt data is baked into
the page at build time, so the app works with no network and no account.

**What is in it:** the dashboard — spending, price trends, store comparison,
Hebrew/English, currency switch.

**What is not:** the Scan and Ask screens. Those call Claude through the
artifact runtime, which only exists inside the published artifact. In the APK
they show a note explaining where to find them. Nothing in the APK calls an AI,
so the APK costs nothing to run however many people install it.

## Build it on your own machine

You need three things. Installing **Android Studio** gets you all of them
(it bundles a JDK and the Android SDK):

| | |
|---|---|
| Python 3 | python.org, or the Microsoft Store |
| JDK 17 | bundled with Android Studio |
| Android SDK, platform 34 | bundled with Android Studio |

Gradle itself you do **not** need to install — the wrapper in this folder
downloads the right version on first run.

### Windows

```bat
git clone https://github.com/samsambm/webapi.git C:\Users\sammybe\Documents\BI\invapp
cd C:\Users\sammybe\Documents\BI\invapp
git checkout claude/bill-scanning-dashboard-kidqww
android\build-apk.bat
```

The APK lands at `android\app\build\outputs\apk\debug\app-debug.apk`.
First run takes a few minutes while Gradle downloads itself; later runs take
seconds.

If Gradle cannot find the SDK, either set `ANDROID_HOME`, or create
`android\local.properties` with:

```
sdk.dir=C:\\Users\\sammybe\\AppData\\Local\\Android\\Sdk
```

(Backslashes are doubled in that file — that is not a typo.)

### macOS and Linux

```bash
git clone https://github.com/samsambm/webapi.git invapp
cd invapp && git checkout claude/bill-scanning-dashboard-kidqww
android/build-apk.sh
```

### From Android Studio

Open the `android/` folder as a project. Before the first build, run
`python3 scripts/build_dashboard.py` and copy `dashboard/index.html` into
`android/app/src/main/assets/` — Android Studio will not do that step for you.
Then press Run with a phone connected or an emulator started.

## Or let CI build it

Push to any branch, or run the **Build APK** workflow by hand
(Actions → Build APK → Run workflow). The APK appears in the run's Artifacts
as `basket-watch-apk`. CI builds through the same wrapper, so it produces the
same APK your machine does.

## Signing

`assembleDebug` produces a debug-signed APK: installable on a phone with
"install unknown apps" allowed for whichever app opens it, but not publishable
to Google Play. For Play you need a release keystore of your own and
`assembleRelease` — see developer.android.com/studio/publish/app-signing.
Generate that key yourself and keep it safe; losing it means you can never
update the app on Play again.

## Refreshing the data in the app

The data is a build-time snapshot. Scan new bills (Claude Code, or the
published app), rerun the build, and install the new APK. If you want an app
whose data updates by itself, it needs a backend — see "Running this as a
product" in the repository README.
