@echo off
REM Build the Basket Watch APK on Windows.
REM Needs: Python 3, JDK 17, and the Android SDK (Android Studio installs both).
REM Run from anywhere:  android\build-apk.bat

setlocal
cd /d "%~dp0\.."

echo [1/3] Rebuilding the dashboard from data\receipts ...
python scripts\build_dashboard.py
if errorlevel 1 (
    echo.
    echo Could not build the dashboard. Is Python 3 installed and on PATH?
    exit /b 1
)

echo [2/3] Bundling the dashboard into the app ...
if not exist "android\app\src\main\assets" mkdir "android\app\src\main\assets"
copy /y "dashboard\index.html" "android\app\src\main\assets\index.html" >nul
if errorlevel 1 exit /b 1

echo [3/3] Building the APK ...
cd android
call gradlew.bat assembleDebug
if errorlevel 1 (
    echo.
    echo The Gradle build failed. The usual cause is the Android SDK not being found.
    echo Either install Android Studio, or set ANDROID_HOME to your SDK folder, or
    echo create android\local.properties containing:
    echo     sdk.dir=C:\\Users\\%USERNAME%\\AppData\\Local\\Android\\Sdk
    exit /b 1
)

echo.
echo Done. The APK is at:
echo    %CD%\app\build\outputs\apk\debug\app-debug.apk
echo.
echo Copy it to your phone and tap it to install.
endlocal
