# Android local APK build

This project builds Android APKs with Flet from the repo-local `.venv`.

## Localized build setup

The Android build wrapper is `scripts/build_android_apk.ps1`. It keeps large
build inputs in local cache directories so normal packaging can run without
network access after the cache is prepared once.

Cached inputs:

- `build/template-cache`: Flet build template zip.
- `build/tool-cache/host-python`: CPython used by `serious_python` while
  packaging the Python app.
- `build/tool-cache/android-python`: Android Python runtime archives.
- `build/android-python-dist`: extracted Android Python runtime used by Gradle.

The default Android ABI is `arm64-v8a`. This matches current Android phones and
avoids downloading legacy `armeabi-v7a` and emulator `x86_64` runtimes unless
they are explicitly requested.

## One-time cache preparation

Run this once while network access is available:

```powershell
.\scripts\build_android_apk.ps1 -RefreshCache -PrepareCacheOnly
```

Windows Developer Mode must be enabled before building APKs, because Flutter
plugins create symlinks during the Android build:

```powershell
start ms-settings:developers
```

Turn on `Developer Mode` in the settings window, then run the build command
again. Without this setting, Flutter stops with `Building with plugins requires
symlink support`.

Alternatively, run PowerShell as Administrator and let the build wrapper enable
the required Windows setting:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_android_apk.ps1 -EnableDeveloperMode
```

This is a one-time Windows setting. It cannot be enabled from a normal
non-admin shell.

For the default phone APK, only the `arm64-v8a` Android Python runtime is
required. To prepare additional ABIs, pass them explicitly:

```powershell
.\scripts\build_android_apk.ps1 -RefreshCache -PrepareCacheOnly -TargetArch arm64-v8a,armeabi-v7a,x86_64
```

## Offline packaging

After cache preparation succeeds, build without network access:

```powershell
.\scripts\build_android_apk.ps1 -Offline
```

To clear generated Flet output while keeping the local tool cache:

```powershell
.\scripts\build_android_apk.ps1 -ClearCache -Offline
```

## ABI selection

Default:

```powershell
.\scripts\build_android_apk.ps1 -Offline -TargetArch arm64-v8a
```

Build all supported ABIs only after all ABI caches have been prepared:

```powershell
.\scripts\build_android_apk.ps1 -Offline -TargetArch arm64-v8a,armeabi-v7a,x86_64
```

## Proxy behavior

If `%USERPROFILE%\.gradle\gradle.properties` points Gradle to a dead
`127.0.0.1:7890` proxy, the wrapper temporarily removes those Gradle proxy
settings for the build and restores them afterward. In `-Offline` mode, missing
cache files fail fast instead of triggering downloads.
