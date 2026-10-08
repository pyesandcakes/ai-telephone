param(
    [switch]$Mock,
    [string]$Prompt = 'A red umbrella floating above an empty swimming pool at night.',
    [int]$Iterations = 12,
    [double]$Hold = 4
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$capturePython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $capturePython)) {
    if (-not $Mock) { throw 'Complete the real-model .venv setup in README.md first. Use -Mock to test recording without AI models.' }
    $capturePython = Join-Path $PSScriptRoot '.capture-venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $capturePython)) {
        py -3.12 -m venv (Join-Path $PSScriptRoot '.capture-venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required for setup.' }
    }
}
& $capturePython -m pip install -r requirements-capture.txt
if ($LASTEXITCODE -ne 0) { throw 'Capture dependency installation failed.' }
$captureArguments = @('capture.py', '--prompt', $Prompt, '--iterations', $Iterations, '--hold', $Hold)
if ($Mock) { $captureArguments += '--mock' }
& $capturePython @captureArguments
if ($LASTEXITCODE -ne 0) { throw 'Capture ended with an error; inspect saved capture files.' }
