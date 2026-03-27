# OpenClaw Android Shell (WebView)

This directory is a standalone Android project that wraps the existing web app at:

- `projects/05-mobile-openclaw`

It does not modify any existing backend/frontend code in the main project.

## What is implemented

- Native Kotlin + Android WebView shell
- Configurable backend URL (saved locally in `SharedPreferences`)
- Default backend URL from Gradle property: `OPENCLAW_BASE_URL`
- Network permissions and cleartext HTTP enabled for LAN debugging
- File upload support from web `<input type="file">`
- Camera + gallery/file picker support (when web accept type includes image)
- Android back key mapped to WebView history back
- Error panel + retry when backend is unreachable

## Quick start

1. Start OpenClaw backend in the main repository root:

```powershell
.\launch_all.ps1
```

2. Build APK from this Android directory:

```powershell
cd D:\1-workspace\6-ai\openclaw-dev\android-openclaw-webview
Copy-Item .\local.properties.example .\local.properties
# Edit .\local.properties and set your real Android SDK path
.\build-debug.ps1 -BaseUrl http://192.168.1.50:8105
```

3. Install on a connected Android device:

```powershell
.\gradlew.bat installDebug
```

Or:

```powershell
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

## Backend URL behavior

- Build-time default comes from `-POPENCLAW_BASE_URL=...`.
- Runtime URL can be changed in app using `Configure URL`.
- Runtime value overrides build-time default and is persisted locally.

## Notes for emulator vs real device

- Android emulator can usually use `http://10.0.2.2:8105`.
- Real device should use your PC LAN IP, for example `http://192.168.x.x:8105`.
- Keep phone and PC on the same LAN.

## Project structure

- `app/src/main/java/com/openclaw/mobile/MainActivity.kt`: WebView shell and integrations
- `app/src/main/AndroidManifest.xml`: permissions, cleartext, `FileProvider`
- `app/src/main/res/xml/network_security_config.xml`: cleartext config
- `app/src/main/res/xml/file_paths.xml`: camera capture output sharing
- `app/src/main/res/layout/activity_main.xml`: host layout
- `app/src/main/res/layout/dialog_backend_url.xml`: backend URL dialog
