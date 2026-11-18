param(
    [ValidateSet('Production_ESP','Inspection_ESP')]
    [string]$Station = 'Production_ESP',
    [switch]$Upload,
    [string]$Port = 'COM3'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
# ESP-IDF rejects spaces in framework/build paths. A junction gives this OneDrive
# checkout a short, space-free alias without copying or relocating user files.
$hasher = [System.Security.Cryptography.SHA256]::Create()
try { $hashBytes = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($repoRoot)) }
finally { $hasher.Dispose() }
$suffix = [BitConverter]::ToString($hashBytes).Replace('-','').Substring(0,8).ToLowerInvariant()
$aliasParent = Join-Path $env:USERPROFILE '.codex'
$aliasRoot = Join-Path $aliasParent "mct431-$suffix"
if (-not (Test-Path -LiteralPath $aliasRoot)) {
    New-Item -ItemType Directory -Force -Path $aliasParent | Out-Null
    New-Item -ItemType Junction -Path $aliasRoot -Target $repoRoot | Out-Null
} else {
    $entry = Get-Item -LiteralPath $aliasRoot -Force
    if ($entry.LinkType -ne 'Junction' -or $entry.Target -ne $repoRoot) {
        throw "Build alias exists with an unexpected target: $aliasRoot"
    }
}
$python = Join-Path $aliasRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create .venv and install requirements-build.txt first; see README.md.'
}
$previousCore = $env:PLATFORMIO_CORE_DIR
try {
    $env:PLATFORMIO_CORE_DIR = Join-Path $aliasRoot '.tools/pio'
    $arguments = @('-m','platformio','run','-d',(Join-Path $aliasRoot $Station))
    if ($Upload) { $arguments += @('-t','upload','--upload-port',$Port) }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "PlatformIO exited with code $LASTEXITCODE" }
} finally {
    $env:PLATFORMIO_CORE_DIR = $previousCore
}
