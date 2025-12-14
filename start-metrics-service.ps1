# Script to start Zabbix Metrics Service
# This service provides metrics data from Zabbix for dashboard d8

Write-Host "Starting Zabbix Metrics Service on port 6000..." -ForegroundColor Green

# Change to app directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$appPath = Join-Path $scriptPath "app"

# Check if zabbix2.py exists
$zabbixScript = Join-Path $appPath "zabbix2.py"
if (-not (Test-Path $zabbixScript)) {
    Write-Host "Error: zabbix2.py not found at $zabbixScript" -ForegroundColor Red
    exit 1
}

# Check if port 6000 is already in use
$portInUse = Get-NetTCPConnection -LocalPort 6000 -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "Warning: Port 6000 is already in use. The service may already be running." -ForegroundColor Yellow
    Write-Host "If you want to restart, please stop the existing service first." -ForegroundColor Yellow
    $response = Read-Host "Do you want to continue anyway? (y/n)"
    if ($response -ne "y") {
        exit 0
    }
}

# Start the service
Write-Host "Starting service..." -ForegroundColor Cyan
Set-Location $appPath
python zabbix2.py
