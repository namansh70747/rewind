# Week-2 mam demo launcher
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host ""
Write-Host "Rewind — Week 2 mam demo" -ForegroundColor DarkCyan
Write-Host "Seeding recordings + starting UI on http://127.0.0.1:8765/"
Write-Host "(first launch runs verify 100x — ~1–2 min)"
Write-Host ""

Start-Process "http://127.0.0.1:8765/"
python demos/week2_mam/server.py
