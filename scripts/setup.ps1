param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $PSScriptRoot
$enginePath = Join-Path $skillRoot 'runtime\python'
New-Item -ItemType Directory -Force -Path $enginePath | Out-Null
& $Python -m pip install --upgrade --target $enginePath -r (Join-Path $skillRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Output "Installed dependencies in $enginePath"
