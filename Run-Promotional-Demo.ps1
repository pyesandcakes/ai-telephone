param(
    [string]$Prompt = 'A red umbrella floating above an empty swimming pool at night.',
    [int]$Iterations = 12,
    [double]$Hold = 4
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Start-AI-Telephone.ps1') '--mode' 'promo' '--' '--prompt' $Prompt '--iterations' "$Iterations" '--hold' "$Hold"
exit $LASTEXITCODE
