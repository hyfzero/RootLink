param(
    [ValidateSet("windows", "apk")]
    [string[]]$Targets = @("windows", "apk"),
    [string]$FlutterPath = "flutter"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$pubspecText = Get-Content -LiteralPath (Join-Path $repoRoot "pubspec.yaml") -Raw -Encoding UTF8
$versionMatch = [regex]::Match($pubspecText, '(?m)^version:\s*([^+\s]+)\+(\d+)\s*$')
if (-not $versionMatch.Success) {
    throw "Project version was not found in pubspec.yaml."
}

$buildVersion = $versionMatch.Groups[1].Value
$artifactName = "RootLink"
$releaseDir = Join-Path $repoRoot "dist\release"

Push-Location $repoRoot
try {
    & $FlutterPath pub get
    if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed." }
    & $FlutterPath analyze
    if ($LASTEXITCODE -ne 0) { throw "flutter analyze failed." }
    & $FlutterPath test
    if ($LASTEXITCODE -ne 0) { throw "flutter test failed." }

    if ($Targets -contains "apk" -and -not (Test-Path -LiteralPath "android\key.properties")) {
        throw "android/key.properties is required for a signed release APK."
    }

    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    foreach ($target in $Targets) {
        if ($target -eq "windows") {
            & $FlutterPath build windows --release
            if ($LASTEXITCODE -ne 0) { throw "Windows release build failed." }
            $windowsOutput = Join-Path $repoRoot "build\windows\x64\runner\Release"
            $archive = Join-Path $releaseDir "$artifactName-v$buildVersion-windows.zip"
            Compress-Archive -Path "$windowsOutput\*" -DestinationPath $archive -Force
            Get-Item -LiteralPath $archive | Select-Object FullName, Length, LastWriteTime
        }
        else {
            & $FlutterPath build apk --release
            if ($LASTEXITCODE -ne 0) { throw "Signed Android release build failed." }
            $apk = Join-Path $repoRoot "build\app\outputs\flutter-apk\app-release.apk"
            $destination = Join-Path $releaseDir "$artifactName-v$buildVersion-android.apk"
            Copy-Item -LiteralPath $apk -Destination $destination -Force
            Get-Item -LiteralPath $destination | Select-Object FullName, Length, LastWriteTime
        }
    }
}
finally {
    Pop-Location
}
