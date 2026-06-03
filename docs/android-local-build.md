# Android local APK build

This project builds Android APKs with Flet from the repo-local `.venv`.

## Build command

Use the native Flet command from the repository root:

```powershell
.\.venv\Scripts\flet.exe build apk . --no-rich-output --skip-flutter-doctor --template .\build\template-cache\flet-build-template-v0.84.0.zip --arch arm64-v8a
```

This is the verified phone APK command used on 2026-06-04.

Do not set `SERIOUS_PYTHON_BUILD_DIST` for this build. In this project it caused
`serious_python_android` to skip packaging `site-packages`, producing an APK
that launched on Android with missing modules such as `certifi`.

A valid APK must contain:

```text
lib/arm64-v8a/libpythonsitepackages.so
```

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

Install the APK:

```powershell
adb install -r .\build\apk\RootLink.apk
```

Launch the app:

```powershell
adb shell monkey -p com.amadues.companion -c android.intent.category.LAUNCHER 1
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
- `No module named 'certifi'` on Android: verify that
  `lib/arm64-v8a/libpythonsitepackages.so` exists in the APK and that
  `SERIOUS_PYTHON_BUILD_DIST` was not set during packaging.
