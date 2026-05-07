param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path
)

$resolvedPath = Resolve-Path -LiteralPath $Path -ErrorAction Stop
$bytes = [System.IO.File]::ReadAllBytes($resolvedPath.Path)
[Convert]::ToBase64String($bytes)
