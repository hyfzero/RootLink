# Android local APK build

This project builds Android APKs with Flet from the repo-local `.venv`.

## Build command

Use the native Flet command from the repository root:

```powershell
.\.venv\Scripts\flet.exe build apk . --no-rich-output --skip-flutter-doctor --template .\build\template-cache\flet-build-template-v0.84.0.zip --arch arm64-v8a
```

This is the verified phone APK command used on 2026-06-04.

Keep this as the only APK build command. Do not reintroduce wrapper scripts for
normal phone builds.

Do not set `SERIOUS_PYTHON_BUILD_DIST` for this build. In this project it caused
`serious_python_android` to skip packaging `site-packages`, producing an APK
that launched on Android with missing modules such as `certifi`.

A valid APK must contain:

```text
lib/arm64-v8a/libpythonsitepackages.so
```

## Local cache policy

The build should reuse local resources whenever possible. In particular, keep
these `serious_python_android` archives under `build\flutter`:

```text
build\flutter\build\serious_python_android\python-android-arm64-v8a.tar.gz
build\flutter\build\serious_python_android\python-android-armeabi-v7a.tar.gz
build\flutter\build\serious_python_android\python-android-x86_64.tar.gz
```

The upstream `serious_python_android-0.9.12` Gradle file registers download
tasks for all three ABI archives. On this machine the Pub cache is patched so
those tasks skip the network when the target archive already exists:

```gradle
onlyIf { !dest.exists() || dest.length() == 0 }
```

The patched file is:

```text
C:\Users\YY\AppData\Local\Pub\Cache\hosted\pub.dev\serious_python_android-0.9.12\android\build.gradle
```

The backup created before patching is:

```text
C:\Users\YY\AppData\Local\Pub\Cache\hosted\pub.dev\serious_python_android-0.9.12\android\build.gradle.codex-backup-20260605-0117
```

If Pub cache is reinstalled or `serious_python_android` is upgraded, verify this
patch before building. Without it, Gradle may download ABI archives on every
build and can fail with `java.net.SocketTimeoutException: Read timed out`.

Do not delete `build\flutter` as routine cleanup, because that removes the local
ABI archives and forces a download again. Delete it only when the generated
Flutter project is corrupted and you accept the cost of repopulating the cache.

## Environment

Run the command from the repository root and use the repo-local virtual
environment:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\flet.exe --version
```

The current Windows build machine also needs these tools available on `PATH`:

```powershell
$env:PATH = "C:\Program Files\Git\cmd;C:\Users\YY\flutter\3.41.4\bin;C:\Users\YY\Android\sdk\platform-tools;$env:PATH"
```

Windows Developer Mode must be enabled before building APKs, because Flutter
plugins create symlinks during the Android build:

```powershell
start ms-settings:developers
```

Turn on `Developer Mode` in the settings window, then run the Flet build command
again. Without this setting, Flutter can stop with `Building with plugins
requires symlink support`.

## Verify APK contents

After building, confirm the APK contains packaged Python dependencies:

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$apk = "D:\Godot\amadues\build\apk\RootLink.apk"
$zip = [IO.Compression.ZipFile]::OpenRead($apk)
try {
    $zip.Entries |
        Where-Object { $_.FullName -match "libpythonsitepackages|app\.zip" } |
        Select-Object FullName, Length |
        Format-Table -AutoSize
}
finally {
    $zip.Dispose()
}
```

Expected output includes:

```text
lib/arm64-v8a/libpythonsitepackages.so
assets/flutter_assets/app/app.zip
```

## Install on phone

Connect the Android phone and confirm it is visible:

```powershell
adb devices -l
```

If `adb` is not on `PATH`, use the full SDK path:

```powershell
& "C:\Users\YY\Android\sdk\platform-tools\adb.exe" devices -l
```

Install the APK:

```powershell
adb install -r .\build\apk\RootLink.apk
```

or:

```powershell
& "C:\Users\YY\Android\sdk\platform-tools\adb.exe" install -r .\build\apk\RootLink.apk
```

Launch the app:

```powershell
adb shell monkey -p com.amadues.companion -c android.intent.category.LAUNCHER 1
```

or:

```powershell
& "C:\Users\YY\Android\sdk\platform-tools\adb.exe" shell monkey -p com.amadues.companion -c android.intent.category.LAUNCHER 1
```

## Troubleshooting

- `git` is missing: install Git or add `C:\Program Files\Git\cmd` to `PATH`.
- `flutter` is missing: add `C:\Users\YY\flutter\3.41.4\bin` to `PATH`.
- `adb` is missing: add `C:\Users\YY\Android\sdk\platform-tools` to `PATH`.
- `Building with plugins requires symlink support`: enable Windows Developer
  Mode, then rerun the Flet build command.
- `Connect to 127.0.0.1:7890 failed`: Gradle is using a local proxy that is not
  running. Start the proxy or temporarily remove `systemProp.*.proxy*` entries
  from `%USERPROFILE%\.gradle\gradle.properties`.
- `downloadDistArchive_armeabi-v7a` or another ABI archive times out: verify
  the local cache policy above before retrying. The normal fix is to keep the
  existing archives and ensure the Pub cache patch skips downloads for files
  that already exist.
- `No module named 'certifi'` on Android: verify that
  `lib/arm64-v8a/libpythonsitepackages.so` exists in the APK and that
  `SERIOUS_PYTHON_BUILD_DIST` was not set during packaging.
