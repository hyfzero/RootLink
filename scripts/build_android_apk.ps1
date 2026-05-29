param(
    [switch]$ClearCache
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$flet = Join-Path $repoRoot ".venv\Scripts\flet.exe"
$pyvenvCfg = Join-Path $repoRoot ".venv\pyvenv.cfg"

function Get-PyvenvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $line = Get-Content -LiteralPath $Path -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Key))\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return $null
    }

    return ($line -replace "^\s*$([regex]::Escape($Key))\s*=\s*", "").Trim()
}

function Find-UvPythonHome {
    $uvPythonRoot = Join-Path $env:APPDATA "uv\python"
    if (-not (Test-Path -LiteralPath $uvPythonRoot)) {
        return $null
    }

    $candidates = @()
    foreach ($dir in Get-ChildItem -LiteralPath $uvPythonRoot -Directory -ErrorAction SilentlyContinue) {
        $python = Join-Path $dir.FullName "python.exe"
        if (-not (Test-Path -LiteralPath $python)) {
            continue
        }

        $versionOutput = & $python --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            continue
        }

        $match = [regex]::Match(($versionOutput | Out-String), "Python\s+(\d+\.\d+\.\d+)")
        if (-not $match.Success) {
            continue
        }

        $candidates += [pscustomobject]@{
            Home = $dir.FullName
            Version = [version]$match.Groups[1].Value
        }
    }

    return $candidates |
        Sort-Object -Property Version -Descending |
        Select-Object -First 1
}

function Repair-PyvenvIfNeeded {
    if (-not (Test-Path -LiteralPath $pyvenvCfg)) {
        throw ".venv\pyvenv.cfg was not found. Recreate the virtual environment in .venv first."
    }

    $pythonHome = Get-PyvenvValue -Path $pyvenvCfg -Key "home"
    $homePython = if ($pythonHome) { Join-Path $pythonHome "python.exe" } else { $null }
    if ($homePython -and (Test-Path -LiteralPath $homePython)) {
        return
    }

    Write-Warning ".venv points to a missing Python home: $pythonHome"
    $candidate = Find-UvPythonHome
    if (-not $candidate) {
        throw "No uv-managed CPython was found under $env:APPDATA\uv\python. Install/sync .venv before building."
    }

    Write-Host "Repairing .venv Python home to $($candidate.Home)"
    $lines = Get-Content -LiteralPath $pyvenvCfg -Encoding UTF8
    $hasHome = $false
    $hasVersionInfo = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^\s*home\s*=") {
            $hasHome = $true
            "home = $($candidate.Home)"
        }
        elseif ($line -match "^\s*version_info\s*=") {
            $hasVersionInfo = $true
            "version_info = $($candidate.Version)"
        }
        else {
            $line
        }
    }

    if (-not $hasHome) {
        $updated += "home = $($candidate.Home)"
    }
    if (-not $hasVersionInfo) {
        $updated += "version_info = $($candidate.Version)"
    }

    Set-Content -LiteralPath $pyvenvCfg -Value $updated -Encoding UTF8
}

function Add-ToolPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Warning "Optional tool path not found: $Path"
        return
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $parts = $env:Path -split ";"
    if ($parts -notcontains $resolved) {
        $env:Path = "$resolved;$env:Path"
    }
}

function Stop-StaleBuildProcesses {
    $repoPattern = [regex]::Escape($repoRoot)
    $processes = Get-CimInstance Win32_Process |
        Where-Object {
            $commandLine = $_.CommandLine
            $_.ProcessId -ne $PID -and
            $_.Name -match "^(flet|dart|dartvm)\.exe$" -and
            $commandLine -match $repoPattern -and
            (
                $commandLine -match "build\s+apk" -or
                $commandLine -match "serious_python" -or
                $commandLine -match "hooks_runner"
            )
        }

    foreach ($process in $processes) {
        Write-Warning "Stopping stale build process $($process.Name) ($($process.ProcessId))."
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }
}

function Test-TcpPortOpen {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,

        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne(500)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Disable-BrokenGradleProxyIfNeeded {
    $gradleProps = Join-Path $env:USERPROFILE ".gradle\gradle.properties"
    if (-not (Test-Path -LiteralPath $gradleProps)) {
        return $null
    }

    $content = Get-Content -LiteralPath $gradleProps -Raw
    $usesLocalProxy = $content -match "(?m)^\s*systemProp\.https?\.proxyHost\s*=\s*127\.0\.0\.1\s*$" -and
        $content -match "(?m)^\s*systemProp\.https?\.proxyPort\s*=\s*7890\s*$"
    if (-not $usesLocalProxy -or (Test-TcpPortOpen -HostName "127.0.0.1" -Port 7890)) {
        return $null
    }

    $backup = "$gradleProps.codex-build-apk-backup"
    Set-Content -LiteralPath $backup -Value $content -Encoding UTF8

    $filtered = ($content -split "`r?`n") |
        Where-Object { $_ -notmatch "^\s*systemProp\.(http|https)\.proxy(Host|Port)\s*=" }
    Set-Content -LiteralPath $gradleProps -Value $filtered -Encoding UTF8
    Write-Warning "Temporarily disabled dead Gradle proxy 127.0.0.1:7890 for this build."

    return [pscustomobject]@{
        Path = $gradleProps
        Backup = $backup
    }
}

function Restore-GradleProxyIfNeeded {
    param($State)

    if (-not $State) {
        return
    }

    if (Test-Path -LiteralPath $State.Backup) {
        Copy-Item -LiteralPath $State.Backup -Destination $State.Path -Force
        Remove-Item -LiteralPath $State.Backup -Force -ErrorAction SilentlyContinue
        Write-Host "Restored Gradle proxy settings."
    }
}

function Start-AndroidTemplatePruner {
    $flutterProject = Join-Path $repoRoot "build\flutter"
    $marker = Join-Path ([System.IO.Path]::GetTempPath()) "amadues-android-pruner-$PID.marker"
    Set-Content -LiteralPath $marker -Value "running" -Encoding UTF8

    $job = Start-Job -ArgumentList $flutterProject, $marker -ScriptBlock {
        param($FlutterProject, $Marker)

        while (Test-Path -LiteralPath $Marker) {
            foreach ($name in @("windows", "linux")) {
                $target = Join-Path $FlutterProject $name
                if (-not (Test-Path -LiteralPath $target)) {
                    continue
                }

                try {
                    $resolved = (Resolve-Path -LiteralPath $target).Path
                    if ($resolved.StartsWith($FlutterProject, [System.StringComparison]::OrdinalIgnoreCase)) {
                        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
                    }
                }
                catch {
                }
            }

            Start-Sleep -Milliseconds 500
        }
    }

    return [pscustomobject]@{
        Job = $job
        Marker = $marker
    }
}

function Stop-AndroidTemplatePruner {
    param($State)

    if (-not $State) {
        return
    }

    Remove-Item -LiteralPath $State.Marker -Force -ErrorAction SilentlyContinue
    Wait-Job -Job $State.Job -Timeout 5 | Out-Null
    Stop-Job -Job $State.Job -ErrorAction SilentlyContinue
    Receive-Job -Job $State.Job -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $State.Job -Force -ErrorAction SilentlyContinue
}

function Remove-GeneratedBuildCache {
    $targets = @(
        (Join-Path $repoRoot "build\.hash"),
        (Join-Path $repoRoot "build\flutter")
    )

    foreach ($target in $targets) {
        if (-not (Test-Path -LiteralPath $target)) {
            continue
        }

        $resolved = (Resolve-Path -LiteralPath $target).Path
        if (-not $resolved.StartsWith("$repoRoot\")) {
            throw "Refusing to remove path outside repository: $resolved"
        }

        Write-Host "Removing generated build cache: $resolved"
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

Repair-PyvenvIfNeeded

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Python executable was not found at $venvPython."
}
if (-not (Test-Path -LiteralPath $flet)) {
    throw "Flet executable was not found at $flet. Install dependencies in .venv first."
}

Add-ToolPath -Path "C:\Program Files\Git\cmd"
Add-ToolPath -Path "C:\Users\YY\flutter\3.41.4\bin"
Add-ToolPath -Path "C:\Users\YY\Android\sdk\platform-tools"

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"

Write-Host "Using Python:"
& $venvPython --version
if ($LASTEXITCODE -ne 0) {
    throw ".venv Python failed."
}

Write-Host "Using Flet:"
& $flet --version
if ($LASTEXITCODE -ne 0) {
    throw ".venv Flet failed."
}

Stop-StaleBuildProcesses

if ($ClearCache) {
    Remove-GeneratedBuildCache
}

Push-Location $repoRoot
$gradleProxyState = Disable-BrokenGradleProxyIfNeeded
$prunerState = Start-AndroidTemplatePruner
try {
    $arguments = @(
        "build",
        "apk",
        ".",
        "--no-rich-output",
        "--skip-flutter-doctor"
    )

    Write-Host "Running: $flet $($arguments -join ' ')"
    & $flet @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "flet build apk failed with exit code $LASTEXITCODE."
    }

    $apkFiles = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot "build") -Recurse -Filter "*.apk" -ErrorAction SilentlyContinue |
        Sort-Object -Property LastWriteTime -Descending)

    if ($apkFiles.Count -eq 0) {
        throw "Build completed, but no APK was found under build\."
    }

    Write-Host "APK output:"
    $apkFiles | Select-Object -First 5 FullName, Length, LastWriteTime
}
finally {
    Stop-AndroidTemplatePruner -State $prunerState
    Restore-GradleProxyIfNeeded -State $gradleProxyState
    Pop-Location
}
