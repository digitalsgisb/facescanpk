param([switch]$Lan, [string]$Python = 'python', [string]$CertFile = '', [string]$KeyFile = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'dist/index.html'))) {
    Write-Host 'Building the React app...'
    & npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'React build failed.' }
}
$attendanceBind = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$attendanceArgs = @('server.py', '--host', $attendanceBind)
if ($CertFile -or $KeyFile) { $attendanceArgs += @('--certfile', $CertFile, '--keyfile', $KeyFile) }
& $Python @attendanceArgs
