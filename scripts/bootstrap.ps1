# Portable Windows setup. All downloaded files stay under this repository/runtime.
[CmdletBinding()]
param([switch]$SkipSmoke)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'This portable installer supports Windows x64. See README for other environments.'
}
$taskLock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'windows-runtime.json') -Raw | ConvertFrom-Json
$taskRuntime = Join-Path $taskRoot 'runtime'
$taskCache = Join-Path $taskRuntime 'downloads'
$taskPythonHost = Join-Path $taskRuntime 'python-host'
$taskLibraries = Join-Path $taskRuntime 'python'
$taskNodeDir = Join-Path $taskRuntime 'node'
foreach ($taskDir in @($taskCache, $taskPythonHost, $taskLibraries, $taskNodeDir)) {
    New-Item -ItemType Directory -Force -Path $taskDir | Out-Null
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-CheckedDownload {
    param([string]$Url, [string]$Hash, [string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host ('Downloading ' + ([Uri]$Url).Segments[-1])
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path
    }
    $taskActual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskActual -ne $Hash) {
        throw "SHA-256 mismatch: $Path. Setup stopped before executing this file."
    }
}

$taskPythonZip = Join-Path $taskCache ('python-' + $taskLock.python.version + '.zip')
Get-CheckedDownload $taskLock.python.url $taskLock.python.sha256 $taskPythonZip
Expand-Archive -LiteralPath $taskPythonZip -DestinationPath $taskPythonHost -Force
# The embeddable interpreter deliberately uses only these project-local paths.
$taskPathFile = Join-Path $taskPythonHost 'python313._pth'
@('python313.zip', '.', '..\python', '..\..\scripts', 'import site') |
    Set-Content -LiteralPath $taskPathFile -Encoding ASCII
foreach ($taskWheel in $taskLock.wheels) {
    $taskWheelZip = Join-Path $taskCache ($taskWheel.name + '-' + $taskWheel.version + '.zip')
    Get-CheckedDownload $taskWheel.url $taskWheel.sha256 $taskWheelZip
    Expand-Archive -LiteralPath $taskWheelZip -DestinationPath $taskLibraries -Force
}
$taskNodeDownload = Join-Path $taskNodeDir 'node.exe'
Get-CheckedDownload $taskLock.node.url $taskLock.node.sha256 $taskNodeDownload
$taskPython = Join-Path $taskPythonHost 'python.exe'
$env:PATH = $taskNodeDir + [IO.Path]::PathSeparator + $env:PATH
& $taskPython -X utf8 (Join-Path $PSScriptRoot 'doctor.py')
if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed.' }
if (-not $SkipSmoke) {
    & $taskPython -X utf8 (Join-Path $PSScriptRoot 'smoke.py')
    if ($LASTEXITCODE -ne 0) { throw 'Sample generation/editing failed.' }
}
Write-Host 'campus-doc ready. Sample files and setup-status.json are in runtime/.'
