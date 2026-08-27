# Atualiza as bases de mapeamento e sobe o app local.
#
# As gravacoes feitas pelo app viram commits no GitHub, nao no disco: sem um pull
# o app local le uma base velha e mostra como "nao mapeado" o que ja foi mapeado
# em producao. Este script garante a ordem certa (atualizar, depois rodar).

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$venv = "C:\Users\marcelo.souza\.venvs\lyra\Scripts\streamlit.exe"

# git pode nao estar no PATH dependendo do terminal
$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) { $git = "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe" }
if (-not (Test-Path $git)) { Write-Host "git nao encontrado." -ForegroundColor Red; exit 1 }

Set-Location $repo
Write-Host "Atualizando do GitHub..." -ForegroundColor Cyan

# --ff-only: so avanca o branch. Nunca cria merge nem rebase, e nunca mexe no que
# voce esta editando. Se nao der para avancar (voce tem commits locais), ele para
# e avisa, em vez de tentar ser esperto com arquivo binario.
& $git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Nao foi possivel atualizar automaticamente." -ForegroundColor Yellow
    Write-Host "Normalmente e porque voce tem commits locais ainda nao enviados." -ForegroundColor Yellow
    Write-Host "Resolva com: git pull --rebase origin main" -ForegroundColor Yellow
    Write-Host ""
    $resp = Read-Host "Subir o app mesmo assim, com a base local atual? (s/N)"
    if ($resp -ne "s") { exit 1 }
}

foreach ($base in @("data\mapping\mapping-artistas-ingrooves.xlsx",
                    "data\mapping\Robo_Abramus_Base.xlsx")) {
    $ultimo = & $git log -1 --format="%ad  %s" --date=format:"%d/%m %H:%M" -- $base
    Write-Host ("  {0,-45} {1}" -f (Split-Path $base -Leaf), $ultimo) -ForegroundColor DarkGray
}

if (-not (Test-Path $venv)) {
    Write-Host "streamlit nao encontrado em $venv" -ForegroundColor Red
    exit 1
}
Write-Host "`nSubindo o app em http://localhost:8501 ..." -ForegroundColor Cyan
& $venv run Home.py
