param(
    [Parameter(Mandatory = $true)]
    [string]$KeystorePath,

    [Parameter(Mandatory = $true)]
    [string]$StorePassword,

    [Parameter(Mandatory = $true)]
    [string]$KeyPassword,

    [Parameter(Mandatory = $true)]
    [string]$Alias
)

function Find-Keytool {
    $fromPath = Get-Command keytool -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }

    if ($env:JAVA_HOME) {
        $fromJavaHome = Join-Path $env:JAVA_HOME "bin\keytool.exe"
        if (Test-Path -LiteralPath $fromJavaHome) {
            return $fromJavaHome
        }
    }

    $commonRoots = @(
        "${env:ProgramFiles}\Java",
        "${env:ProgramFiles}\Eclipse Adoptium",
        "${env:ProgramFiles}\Microsoft"
    )

    foreach ($root in $commonRoots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }

        $match = Get-ChildItem -LiteralPath $root -Recurse -Filter keytool.exe -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    return $null
}

$keytool = Find-Keytool
if (-not $keytool) {
    throw "keytool was not found. Install a JDK or add keytool to PATH."
}

if (-not (Test-Path -LiteralPath $KeystorePath)) {
    & $keytool `
        -genkeypair `
        -v `
        -keystore $KeystorePath `
        -storepass $StorePassword `
        -keypass $KeyPassword `
        -alias $Alias `
        -keyalg RSA `
        -keysize 2048 `
        -validity 10000 `
        -dname "CN=Amadues Companion, OU=Release, O=Amadues, L=Shanghai, S=Shanghai, C=CN"

    if ($LASTEXITCODE -ne 0) {
        throw "keytool failed with exit code $LASTEXITCODE."
    }
}

$resolvedPath = Resolve-Path -LiteralPath $KeystorePath -ErrorAction Stop
$bytes = [System.IO.File]::ReadAllBytes($resolvedPath.Path)

Write-Output "ANDROID_KEYSTORE_BASE64:"
Write-Output ([Convert]::ToBase64String($bytes))
Write-Output ""
Write-Output "ANDROID_KEYSTORE_PASSWORD: $StorePassword"
Write-Output "ANDROID_KEY_PASSWORD: $KeyPassword"
Write-Output "ANDROID_KEY_ALIAS: $Alias"
