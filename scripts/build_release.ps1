param(
    [ValidateSet("windows", "apk")]
    [string[]]$Targets = @("windows", "apk"),

    [int]$BuildNumber = 0,

    [switch]$ClearCache
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$flet = Join-Path $repoRoot ".venv\Scripts\flet.exe"
$pyproject = Join-Path $repoRoot "pyproject.toml"

if (-not (Test-Path -LiteralPath $flet)) {
    throw "Flet executable was not found at $flet. Install dependencies in .venv first."
}

$pyprojectText = Get-Content -LiteralPath $pyproject -Raw -Encoding UTF8
$versionMatch = [regex]::Match($pyprojectText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Project version was not found in pyproject.toml."
}
$buildVersion = $versionMatch.Groups[1].Value
$artifactMatch = [regex]::Match($pyprojectText, '(?m)^artifact\s*=\s*"([^"]+)"')
if (-not $artifactMatch.Success) {
    throw "Flet artifact name was not found in pyproject.toml."
}
$artifactName = $artifactMatch.Groups[1].Value
if ($BuildNumber -le 0) {
    $buildNumberMatch = [regex]::Match($pyprojectText, '(?m)^build_number\s*=\s*(\d+)')
    if (-not $buildNumberMatch.Success) {
        throw "BuildNumber was not provided and tool.flet.build_number was not found in pyproject.toml."
    }
    $BuildNumber = [int]$buildNumberMatch.Groups[1].Value
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"

Push-Location $repoRoot
try {
    $failedTargets = @()
    foreach ($target in $Targets) {
        Write-Host "Building $target release, version $buildVersion, build $BuildNumber..."

        if ($target -eq "windows") {
            $windowsOutput = Join-Path $repoRoot "build\windows"
            $windowsAppDir = Join-Path $windowsOutput $artifactName
            if (Test-Path -LiteralPath $windowsAppDir) {
                $removeError = $null
                for ($attempt = 1; $attempt -le 5; $attempt++) {
                    try {
                        Remove-Item -LiteralPath $windowsAppDir -Recurse -Force
                        $removeError = $null
                        break
                    }
                    catch {
                        $removeError = $_
                        Start-Sleep -Seconds 3
                    }
                }
                if ($null -ne $removeError) {
                    throw $removeError
                }
            }
            $arguments = @(
                "pack",
                "main.py",
                "--onedir",
                "--name",
                $artifactName,
                "--product-name",
                $artifactName,
                "--product-version",
                $buildVersion,
                "--file-version",
                "$buildVersion.$BuildNumber",
                "--bundle-id",
                "com.amadues.companion",
                "--distpath",
                $windowsOutput,
                "--add-data",
                "resource:resource",
                "assets:assets",
                "--pyinstaller-build-args=--paths=src",
                "--yes"
            )
        }
        else {
            $arguments = @(
                "build",
                $target,
                ".",
                "--build-version",
                $buildVersion,
                "--build-number",
                $BuildNumber,
                "--no-rich-output"
            )

            $cachedTemplate = Join-Path $repoRoot "build\template-cache\flet-build-template-v0.84.0.zip"
            if ($target -eq "apk" -and (Test-Path -LiteralPath $cachedTemplate)) {
                $arguments += @(
                    "--skip-flutter-doctor",
                    "--template",
                    $cachedTemplate,
                    "--arch",
                    "arm64-v8a"
                )
            }

            if ($ClearCache) {
                $arguments += "--clear-cache"
            }
        }

        & $flet @arguments
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Flet packaging for $target failed with exit code $LASTEXITCODE."
            $failedTargets += $target
            continue
        }
    }

    if ($failedTargets.Count -eq 0) {
        Write-Host "Release builds completed."
    }
    else {
        Write-Warning "Release builds completed with failures: $($failedTargets -join ', ')"
    }

    foreach ($target in $Targets) {
        $outputDir = Join-Path $repoRoot "build\$target"
        if (Test-Path -LiteralPath $outputDir) {
            Get-ChildItem -LiteralPath $outputDir | Select-Object FullName, Length, LastWriteTime
        }
    }

    if ($failedTargets.Count -gt 0) {
        throw "Failed release targets: $($failedTargets -join ', ')"
    }

    $releaseDir = Join-Path $repoRoot "dist\release"
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

    if ($Targets -contains "windows") {
        $windowsDir = Join-Path $repoRoot "build\windows\$artifactName"
        $windowsArchive = Join-Path $releaseDir "$artifactName-v$buildVersion-windows.zip"
        $archiveError = $null
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            try {
                Start-Sleep -Seconds 3
                Compress-Archive -Path $windowsDir -DestinationPath $windowsArchive -Force
                $archiveError = $null
                break
            }
            catch {
                $archiveError = $_
                Write-Warning "Windows archive attempt $attempt failed: $($_.Exception.Message)"
            }
        }
        if ($null -ne $archiveError) {
            throw $archiveError
        }
        Get-Item -LiteralPath $windowsArchive | Select-Object FullName, Length, LastWriteTime
    }

    if ($Targets -contains "apk") {
        $apkSource = Join-Path $repoRoot "build\apk\$artifactName.apk"
        $apkDestination = Join-Path $releaseDir "$artifactName-v$buildVersion-android.apk"
        Copy-Item -LiteralPath $apkSource -Destination $apkDestination -Force
        Get-Item -LiteralPath $apkDestination | Select-Object FullName, Length, LastWriteTime
    }
}
finally {
    Pop-Location
}
