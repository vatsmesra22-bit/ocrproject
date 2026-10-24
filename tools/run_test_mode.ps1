# TESTING ONLY: run the app on this laptop.
# Lists stay in the browser of the phone/laptop that uploads them - nothing is saved here.
# Usage (from the project folder):  .\tools\run_test_mode.ps1
# Add -Lan to let a phone on the same Wi-Fi open it (test data only).
param([switch]$Lan)

Set-Location (Split-Path $PSScriptRoot -Parent)
$python = ".\.venv\Scripts\python.exe"

Write-Host "TEST MODE - use made-up lists only" -ForegroundColor Yellow
if ($Lan) {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" } | Select-Object -First 1).IPAddress
    Write-Host "On your phone (same Wi-Fi) open:  http://${ip}:8000" -ForegroundColor Green
    & $python -m app.cli serve --host 0.0.0.0 --port 8000
} else {
    & $python -m app.cli serve --port 8000
}
