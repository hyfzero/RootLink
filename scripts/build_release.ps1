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
if ($BuildNumber -le 0) {
    $versionParts = $buildVersion.Split(".")
    if ($versionParts.Count -lt 3) {
        throw "BuildNumber was not provided and version '$buildVersion' is not a major.minor.patch version."
    }
    $BuildNumber = ([int]$versionParts[0] * 10000) + ([int]$versionParts[1] * 100) + [int]$versionParts[2]
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"

Push-Location $repoRoot
try {
    $failedTargets = @()
    foreach ($target in $Targets) {
        Write-Host "Building $target release, version $buildVersion, build $BuildNumber..."

        $arguments = @(
            "build",
            $target,
            "--build-version",
            $buildVersion,
            "--build-number",
            $BuildNumber,
            "--no-rich-output"
        )

        if ($ClearCache) {
            $arguments += "--clear-cache"
        }

        & $flet @arguments
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "flet build $target failed with exit code $LASTEXITCODE."
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
}
finally {
    Pop-Location
}
