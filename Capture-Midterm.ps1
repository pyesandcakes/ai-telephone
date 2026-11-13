param(
    [switch]$Mock,
    [string]$Prompt = 'A red umbrella floating above an empty swimming pool at night.',
    [int]$Iterations = 12,
    [double]$Hold = 4
)
$ErrorActionPreference = 'Stop'
$arguments = @('--mode', 'capture', '--', '--prompt', $Prompt, '--iterations', "$Iterations", '--hold', "$Hold")
if ($Mock) { $arguments += '--mock' }
& (Join-Path $PSScriptRoot 'Start-AI-Telephone.ps1') @arguments
exit $LASTEXITCODE
