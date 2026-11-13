# Keep CLI flags verbatim, including -- and capture options.
$LaunchArguments = @($args)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
# Do not reuse a Windows virtualenv copied from another computer.
$candidates = @(
    @{ Exe = 'py'; Prefix = @('-3.12') },
    @{ Exe = 'py'; Prefix = @('-3.11') },
    @{ Exe = 'python'; Prefix = @() }
)
foreach ($candidate in $candidates) {
    $executable = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
    if (-not $executable) { continue }
    $prefix = $candidate.Prefix
    & $executable.Source @prefix -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $executable.Source @prefix (Join-Path $PSScriptRoot 'launch.py') @LaunchArguments
        exit $LASTEXITCODE
    }
}
Write-Host 'Install Python 3.12 from python.org (enable the Python launcher), then run Start-AI-Telephone again.'
Start-Process 'https://www.python.org/downloads/release/python-31210/'
exit 1
