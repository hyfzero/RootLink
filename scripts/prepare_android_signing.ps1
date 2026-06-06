param(
    [string]$KeystorePath = (Join-Path $HOME ".rootlink\signing\rootlink-release.jks"),
    [string]$Alias = "rootlink-release",
    [string]$DistinguishedName = "CN=RootLink, OU=Release, O=RootLink, L=Shanghai, ST=Shanghai, C=CN",
    [int]$ValidityDays = 10000,
    [SecureString]$StorePassword,
    [SecureString]$KeyPassword
)

$ErrorActionPreference = "Stop"

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
        (Join-Path $HOME "java"),
        "${env:ProgramFiles}\Android\Android Studio\jbr",
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

    throw "keytool was not found. Install a JDK or add keytool to PATH."
}

function ConvertFrom-SecureStringPlainText {
    param([Parameter(Mandatory = $true)][SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

if (-not $StorePassword) {
    $StorePassword = Read-Host "Keystore password" -AsSecureString
}
if (-not $KeyPassword) {
    $KeyPassword = Read-Host "Key password" -AsSecureString
}

$keytool = Find-Keytool
$resolvedKeystorePath = [System.IO.Path]::GetFullPath($KeystorePath)
$signingDirectory = Split-Path -Parent $resolvedKeystorePath
$certificatePath = Join-Path $signingDirectory "rootlink-release.pem"
$certificateInfoPath = Join-Path $signingDirectory "certificate-fingerprints.txt"

New-Item -ItemType Directory -Path $signingDirectory -Force | Out-Null

$storePasswordText = ConvertFrom-SecureStringPlainText $StorePassword
$keyPasswordText = ConvertFrom-SecureStringPlainText $KeyPassword

try {
    $env:ROOTLINK_KEYSTORE_PASSWORD = $storePasswordText
    $env:ROOTLINK_KEY_PASSWORD = $keyPasswordText

    if (-not (Test-Path -LiteralPath $resolvedKeystorePath)) {
        & $keytool `
            -genkeypair `
            -keystore $resolvedKeystorePath `
            -storetype JKS `
            -storepass:env ROOTLINK_KEYSTORE_PASSWORD `
            -keypass:env ROOTLINK_KEY_PASSWORD `
            -alias $Alias `
            -keyalg RSA `
            -keysize 4096 `
            -validity $ValidityDays `
            -dname $DistinguishedName

        if ($LASTEXITCODE -ne 0) {
            throw "keytool failed to generate the keystore with exit code $LASTEXITCODE."
        }
    }
    else {
        Write-Output "Using the existing keystore. No key was generated."
    }

    & $keytool `
        -exportcert `
        -rfc `
        -keystore $resolvedKeystorePath `
        -storepass:env ROOTLINK_KEYSTORE_PASSWORD `
        -alias $Alias `
        -file $certificatePath

    if ($LASTEXITCODE -ne 0) {
        throw "keytool failed to export the certificate with exit code $LASTEXITCODE."
    }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5 wraps keytool warnings from stderr as ErrorRecord objects.
        $ErrorActionPreference = "Continue"
        $certificateInfo = & $keytool `
            -list `
            -v `
            -keystore $resolvedKeystorePath `
            -storepass:env ROOTLINK_KEYSTORE_PASSWORD `
            -alias $Alias 2>&1
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($LASTEXITCODE -ne 0) {
        throw "keytool failed to inspect the certificate with exit code $LASTEXITCODE."
    }

    $certificateInfo | Set-Content -LiteralPath $certificateInfoPath -Encoding UTF8

    Write-Output "Keystore: $resolvedKeystorePath"
    Write-Output "Alias: $Alias"
    Write-Output "Public certificate: $certificatePath"
    Write-Output "Certificate details: $certificateInfoPath"
    Write-Output "Passwords and private-key Base64 were not printed."
}
finally {
    Remove-Item Env:ROOTLINK_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:ROOTLINK_KEY_PASSWORD -ErrorAction SilentlyContinue
    $storePasswordText = $null
    $keyPasswordText = $null
}
