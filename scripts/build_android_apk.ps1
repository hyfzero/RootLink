param(
    [switch]$ClearCache,
    [switch]$RefreshCache,
    [switch]$Offline,
    [switch]$PrepareCacheOnly,
    [switch]$EnableDeveloperMode,
    [ValidateSet("arm64-v8a", "armeabi-v7a", "x86_64")]
    [string[]]$TargetArch = @("arm64-v8a")
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

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Enable-WindowsDeveloperMode {
    if (-not (Test-IsAdministrator)) {
        throw "Enabling Windows Developer Mode requires an elevated PowerShell. Run as Administrator: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_android_apk.ps1 -EnableDeveloperMode"
    }

    $key = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock"
    New-Item -Path $key -Force | Out-Null
    Set-ItemProperty -Path $key -Name "AllowDevelopmentWithoutDevLicense" -Type DWord -Value 1
    Set-ItemProperty -Path $key -Name "AllowAllTrustedApps" -Type DWord -Value 1
    Write-Host "Windows Developer Mode registry settings were enabled."
}

function Assert-SymlinkSupport {
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "amadues-symlink-test-$PID"
    try {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        $source = Join-Path $tempDir "source.txt"
        $link = Join-Path $tempDir "link.txt"
        Set-Content -LiteralPath $source -Value "test" -Encoding UTF8
        New-Item -ItemType SymbolicLink -Path $link -Target $source -ErrorAction Stop | Out-Null
    }
    catch {
        throw "Flutter plugin builds require Windows symlink support. Enable Developer Mode in Settings with: start ms-settings:developers. Or run this script as Administrator with -EnableDeveloperMode."
    }
    finally {
        Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
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

function Test-ZipFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
        try {
            return $zip.Entries.Count -gt 0
        }
        finally {
            $zip.Dispose()
        }
    }
    catch {
        return $false
    }
}

function Invoke-CachedDownload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [string]$Destination,

        [switch]$Refresh
    )

    if ((Test-Path -LiteralPath $Destination) -and -not $Refresh) {
        return
    }

    if ($Offline) {
        throw "Offline mode is enabled and required cache is missing: $Destination"
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $tempPath = "$Destination.tmp"
    Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue

    Write-Host "Downloading with retries: $Url"
    & curl.exe --fail --location --retry 5 --retry-all-errors --connect-timeout 30 --output $tempPath $Url
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        throw "Failed to download $Url."
    }

    Move-Item -LiteralPath $tempPath -Destination $Destination -Force
}

function Ensure-FletBuildTemplateCache {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FletVersion
    )

    $cacheDir = Join-Path $repoRoot "build\template-cache"
    New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

    $zipPath = Join-Path $cacheDir "flet-build-template-v$FletVersion.zip"
    if ($RefreshCache -and (Test-Path -LiteralPath $zipPath)) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    $cookiecutterZip = Join-Path $env:USERPROFILE ".cookiecutters\flet-build-template.zip"
    if (-not (Test-Path -LiteralPath $zipPath) -and (Test-Path -LiteralPath $cookiecutterZip)) {
        if (Test-ZipFile -Path $cookiecutterZip) {
            Copy-Item -LiteralPath $cookiecutterZip -Destination $zipPath -Force
            Write-Host "Imported Flet build template from Cookiecutter cache: $cookiecutterZip"
        }
        else {
            Write-Warning "Ignoring invalid Cookiecutter template cache: $cookiecutterZip"
        }
    }

    $url = "https://github.com/flet-dev/flet/releases/download/v$FletVersion/flet-build-template.zip"
    if (-not ((Test-Path -LiteralPath $zipPath) -and (Test-ZipFile -Path $zipPath))) {
        if (Test-Path -LiteralPath $zipPath) {
            Write-Warning "Removing invalid Flet build template cache: $zipPath"
            Remove-Item -LiteralPath $zipPath -Force
        }
        Invoke-CachedDownload -Url $url -Destination $zipPath -Refresh:$RefreshCache
    }

    if (-not (Test-ZipFile -Path $zipPath)) {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        throw "Downloaded Flet build template is not a valid zip: $url"
    }

    Write-Host "Using cached Flet build template: $zipPath"
    return $zipPath
}

function Ensure-HostPythonCache {
    $pythonVersion = "3.12.9"
    $releaseDate = "20250205"
    $arch = "x86_64-pc-windows-msvc-shared"
    $archiveName = "cpython-$pythonVersion+$releaseDate-$arch-install_only_stripped.tar.gz"
    $cacheDir = Join-Path $repoRoot "build\tool-cache\host-python"
    $archivePath = Join-Path $cacheDir $archiveName
    $extractDir = Join-Path $repoRoot "build\flutter\build\build_python_$pythonVersion"
    $pythonExe = Join-Path $extractDir "python\python.exe"

    if ($RefreshCache) {
        Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $url = "https://github.com/astral-sh/python-build-standalone/releases/download/$releaseDate/$archiveName"
        Invoke-CachedDownload -Url $url -Destination $archivePath -Refresh:$RefreshCache
        New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
        Write-Host "Extracting cached host Python: $archivePath"
        & tar.exe -xzf $archivePath -C $extractDir
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
            throw "Failed to extract cached host Python: $archivePath"
        }
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "Host Python cache is incomplete: $pythonExe"
    }

    Write-Host "Using cached serious_python host Python: $pythonExe"
}

function Ensure-AndroidPythonDistCache {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$AbiList
    )

    $pythonVersion = "3.12"
    $cacheDir = Join-Path $repoRoot "build\tool-cache\android-python"
    $distRoot = Join-Path $repoRoot "build\android-python-dist"

    foreach ($abi in $AbiList) {
        $archiveName = "python-android-dart-$pythonVersion-$abi.tar.gz"
        $archivePath = Join-Path $cacheDir $archiveName
        $abiDir = Join-Path $distRoot $abi

        if ($RefreshCache) {
            Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $abiDir -Recurse -Force -ErrorAction SilentlyContinue
        }

        if (-not (Test-Path -LiteralPath $abiDir)) {
            $url = "https://github.com/flet-dev/python-build/releases/download/v$pythonVersion/$archiveName"
            Invoke-CachedDownload -Url $url -Destination $archivePath -Refresh:$RefreshCache
            New-Item -ItemType Directory -Path $abiDir -Force | Out-Null
            Write-Host "Extracting cached Android Python for $abi"
            & tar.exe -xzf $archivePath -C $abiDir
            if ($LASTEXITCODE -ne 0) {
                Remove-Item -LiteralPath $abiDir -Recurse -Force -ErrorAction SilentlyContinue
                throw "Failed to extract cached Android Python archive: $archivePath"
            }
        }

        if (-not (Test-Path -LiteralPath $abiDir)) {
            throw "Android Python cache is incomplete: $abiDir"
        }
    }

    $env:SERIOUS_PYTHON_BUILD_DIST = $distRoot
    Write-Host "Using cached Android Python dist: $distRoot"
    Write-Host "Android target ABI: $($AbiList -join ', ')"
}

function Remove-IncompleteSeriousPythonCache {
    $flutterBuildDir = Join-Path $repoRoot "build\flutter\build"
    if (-not (Test-Path -LiteralPath $flutterBuildDir)) {
        return
    }

    $resolvedBuildDir = (Resolve-Path -LiteralPath $flutterBuildDir).Path
    if (-not $resolvedBuildDir.StartsWith("$repoRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to inspect path outside repository: $resolvedBuildDir"
    }

    foreach ($dir in Get-ChildItem -LiteralPath $resolvedBuildDir -Directory -Filter "build_python_*" -ErrorAction SilentlyContinue) {
        $pythonExe = Join-Path $dir.FullName "python\python.exe"
        if (Test-Path -LiteralPath $pythonExe) {
            continue
        }

        Write-Warning "Removing incomplete serious_python cache: $($dir.FullName)"
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force

        foreach ($archive in Get-ChildItem -LiteralPath $resolvedBuildDir -File -Filter "cpython-*.tar.gz" -ErrorAction SilentlyContinue) {
            Write-Warning "Removing possibly incomplete Python archive: $($archive.FullName)"
            Remove-Item -LiteralPath $archive.FullName -Force
        }
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
$fletVersionOutput = & $flet --version 2>&1
$fletVersionOutput
if ($LASTEXITCODE -ne 0) {
    throw ".venv Flet failed."
}
$fletVersionMatch = [regex]::Match(($fletVersionOutput | Out-String), "Flet:\s*([0-9]+\.[0-9]+\.[0-9]+)")
if (-not $fletVersionMatch.Success) {
    throw "Could not determine Flet version from: $($fletVersionOutput | Out-String)"
}
$fletVersion = $fletVersionMatch.Groups[1].Value

Stop-StaleBuildProcesses

if ($EnableDeveloperMode) {
    Enable-WindowsDeveloperMode
}

if ($ClearCache) {
    Remove-GeneratedBuildCache
}

$fletBuildTemplate = Ensure-FletBuildTemplateCache -FletVersion $fletVersion
Ensure-HostPythonCache
Ensure-AndroidPythonDistCache -AbiList $TargetArch
if ($PrepareCacheOnly) {
    Write-Host "Build cache is ready."
    exit 0
}
Assert-SymlinkSupport
Remove-IncompleteSeriousPythonCache

Push-Location $repoRoot
$gradleProxyState = Disable-BrokenGradleProxyIfNeeded
$prunerState = $null
try {
    $arguments = @(
        "build",
        "apk",
        ".",
        "--no-rich-output",
        "--skip-flutter-doctor",
        "--template",
        $fletBuildTemplate,
        "--arch"
    )
    $arguments += $TargetArch
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
