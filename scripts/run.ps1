param(
    [Parameter(Position=0)][string]$Script = 'doctor.py',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'runtime\python-host\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run SETUP.cmd first.' }
if ([IO.Path]::GetFileName($Script) -ne $Script -or -not $Script.EndsWith('.py')) {
    throw 'Specify a Python script filename in scripts/.'
}
$taskScript = Join-Path $PSScriptRoot $Script
if (-not (Test-Path -LiteralPath $taskScript)) { throw 'Unknown campus-doc script.' }
$env:PATH = (Join-Path $taskRoot 'runtime\node') + [IO.Path]::PathSeparator + $env:PATH
& $taskPython -X utf8 $taskScript @Arguments
exit $LASTEXITCODE
