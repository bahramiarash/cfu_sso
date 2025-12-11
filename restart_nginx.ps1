# restart_nginx.ps1
# Restart Nginx on Windows Server

$nginxPath = "C:\nginx"
$nginxExe = "$nginxPath\nginx.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Restart Nginx on Windows Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Checking Nginx status..." -ForegroundColor Yellow

# Check if nginx is running
$nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue

if ($nginxProcess) {
    Write-Host "Nginx is running. Testing configuration..." -ForegroundColor Yellow
    
    # Test configuration
    & $nginxExe -t
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Configuration is valid." -ForegroundColor Green
        Write-Host ""
        Write-Host "Reloading Nginx..." -ForegroundColor Yellow
        & $nginxExe -s reload
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "✅ Nginx reloaded successfully!" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "⚠️  Reload failed. Restarting..." -ForegroundColor Yellow
            Stop-Process -Name nginx -Force
            Start-Sleep -Seconds 2
            Start-Process -FilePath $nginxExe
            Write-Host ""
            Write-Host "✅ Nginx restarted!" -ForegroundColor Green
        }
    } else {
        Write-Host ""
        Write-Host "❌ Configuration test failed!" -ForegroundColor Red
        Write-Host "Please fix errors in nginx configuration first." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Nginx is not running." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Starting Nginx..." -ForegroundColor Yellow
    Start-Process -FilePath $nginxExe
    Write-Host ""
    Write-Host "✅ Nginx started!" -ForegroundColor Green
}

# Verify
Write-Host ""
Write-Host "Verifying..." -ForegroundColor Yellow
Start-Sleep -Seconds 1
$nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue
if ($nginxProcess) {
    Write-Host "✅ Nginx is running. PID: $($nginxProcess.Id)" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to start Nginx!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

