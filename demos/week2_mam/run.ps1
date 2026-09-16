# Week-2 mam demo launcher
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host ""
Write-Host "Rewind — Month 1 mam console (login → full prototype)" -ForegroundColor DarkCyan
Write-Host "Seeding + Month-1 proofs + UI on http://127.0.0.1:8765/"
Write-Host "Sign in / Create account / Continue with Google, then all Month 1 tabs."
Write-Host "(first launch: verify 100x + spikes/corpus — a few minutes)"
Write-Host ""

Start-Process "http://127.0.0.1:8765/"
python demos/week2_mam/server.py
