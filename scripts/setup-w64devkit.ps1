param(
    [string]$InstallRoot = "tools"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$releaseFile = Join-Path $repoRoot "w64devkit-release.json"
$toolsDir = Join-Path $repoRoot $InstallRoot
$installDir = Join-Path $toolsDir "w64devkit"

if (Test-Path (Join-Path $installDir "bin\g++.exe")) {
    Write-Host "w64devkit is already installed at $installDir"
    exit 0
}

if (-not (Test-Path $releaseFile)) {
    throw "Missing $releaseFile"
}

$release = Get-Content $releaseFile -Raw | ConvertFrom-Json
$asset = $release.assets | Where-Object { $_.name -eq "w64devkit-x64-2.8.0.7z.exe" } | Select-Object -First 1

if (-not $asset) {
    throw "Could not find w64devkit x64 asset in $releaseFile"
}

New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

$installerPath = Join-Path $toolsDir $asset.name

if (-not (Test-Path $installerPath)) {
    Write-Host "Downloading $($asset.name)..."
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installerPath
}

Write-Host "Extracting w64devkit..."
& $installerPath "-y" "-o$toolsDir" | Out-Host

if (-not (Test-Path (Join-Path $installDir "bin\g++.exe"))) {
    throw "w64devkit extraction finished, but g++.exe was not found at $installDir\bin"
}

Write-Host "w64devkit installed at $installDir"
