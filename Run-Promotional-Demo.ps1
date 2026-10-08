param(
    [string]$Prompt = 'A red umbrella floating above an empty swimming pool at night.',
    [int]$Iterations = 12,
    [double]$Hold = 4
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$promoPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $promoPython)) { throw 'Complete the real-model setup in README.md first.' }
$promoStarted = Get-Date
$env:HF_HUB_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
& $promoPython capture.py --prompt $Prompt --iterations $Iterations --hold $Hold
if ($LASTEXITCODE -ne 0) { throw 'Real capture failed. Saved images remain in captures.' }
$promoSession = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'captures') -Directory |
    Where-Object { $_.Name -like '*-capture-*' -and $_.CreationTime -ge $promoStarted -and (Test-Path -LiteralPath (Join-Path $_.FullName 'result.json')) } |
    Sort-Object CreationTime -Descending | Select-Object -First 1
if (-not $promoSession) { throw 'No completed capture found for this invocation.' }
$promoCapture = Get-Content -LiteralPath (Join-Path $promoSession.FullName 'capture.json') -Raw | ConvertFrom-Json
& $promoPython build_promo.py $promoCapture.run_folder
if ($LASTEXITCODE -ne 0) { throw 'Promotional export failed; read the output logs.' }
Write-Output "Video and printable poster saved to $(Join-Path $PSScriptRoot 'promotional-output')"
