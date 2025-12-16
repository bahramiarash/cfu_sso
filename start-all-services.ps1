# start-all-services.ps1
Write-Host "Starting all microservices..." -ForegroundColor Green

# Load environment variables from .env file
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Set default values if not in .env
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "change-me-in-production" }
if (-not $env:JWT_SECRET) { $env:JWT_SECRET = $env:SECRET_KEY }
if (-not $env:AUTH_SERVICE_URL) { $env:AUTH_SERVICE_URL = "http://localhost:5001" }
if (-not $env:ADMIN_SERVICE_URL) { $env:ADMIN_SERVICE_URL = "http://localhost:5002" }
if (-not $env:SURVEY_SERVICE_URL) { $env:SURVEY_SERVICE_URL = "http://localhost:5003" }
if (-not $env:DASHBOARD_SERVICE_URL) { $env:DASHBOARD_SERVICE_URL = "http://localhost:5004" }
if (-not $env:KANBAN_SERVICE_URL) { $env:KANBAN_SERVICE_URL = "http://localhost:5005" }
if (-not $env:KNOWLEDGE_SERVICE_URL) { $env:KNOWLEDGE_SERVICE_URL = "http://localhost:5008" }
if (-not $env:REDIS_HOST) { $env:REDIS_HOST = "localhost" }
if (-not $env:REDIS_PORT) { $env:REDIS_PORT = "6379" }
if (-not $env:SSO_CLIENT_ID) { $env:SSO_CLIENT_ID = "bicfu" }
if (-not $env:SSO_REDIRECT_URI) { $env:SSO_REDIRECT_URI = "https://bi.cfu.ac.ir/auth/authorized" }

# Create directories
New-Item -ItemType Directory -Force -Path shared\databases, shared\flask_session | Out-Null

# Start Auth Service
Write-Host "Starting Auth Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\auth-service; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:JWT_SECRET='$env:JWT_SECRET'; `$env:SSO_CLIENT_SECRET='$env:SSO_CLIENT_SECRET'; `$env:SSO_CLIENT_ID='$env:SSO_CLIENT_ID'; `$env:SSO_REDIRECT_URI='$env:SSO_REDIRECT_URI'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 3

# Start Admin Service
Write-Host "Starting Admin Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\admin-service; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Survey Service
Write-Host "Starting Survey Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\survey-service; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Dashboard Service
Write-Host "Starting Dashboard Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\dashboard-service; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Kanban Service
Write-Host "Starting Kanban Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\kanban-service; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Knowledge Management Service
Write-Host "Starting Knowledge Management Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\knowledge-management-service; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Gateway Service
Write-Host "Starting Gateway Service..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd services\gateway-service; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; `$env:SECRET_KEY='$env:SECRET_KEY'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Monolithic App (for Survey and Dashboard HTML support)
Write-Host "Starting Monolithic App..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd app; `$env:FLASK_RUN_PORT='5006'; `$env:SECRET_KEY='$env:SECRET_KEY'; `$env:AUTH_SERVICE_URL='$env:AUTH_SERVICE_URL'; python app.py" -WindowStyle Normal
Start-Sleep -Seconds 2

# Start Metrics Service (Zabbix metrics for dashboard d8)
Write-Host "Starting Metrics Service (Zabbix)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd app; python zabbix2.py" -WindowStyle Normal
Start-Sleep -Seconds 2

Write-Host "`nAll services started! Check the PowerShell windows." -ForegroundColor Green
Write-Host "Auth Service: http://localhost:5001" -ForegroundColor Cyan
Write-Host "Admin Service: http://localhost:5002" -ForegroundColor Cyan
Write-Host "Survey Service: http://localhost:5003" -ForegroundColor Cyan
Write-Host "Dashboard Service: http://localhost:5004" -ForegroundColor Cyan
Write-Host "Kanban Service: http://localhost:5005" -ForegroundColor Cyan
Write-Host "Knowledge Management Service: http://localhost:5008" -ForegroundColor Cyan
Write-Host "Gateway Service: http://localhost:5000" -ForegroundColor Cyan
Write-Host "Monolithic App: http://localhost:5006" -ForegroundColor Cyan
Write-Host "Metrics Service (Zabbix): http://localhost:6000" -ForegroundColor Cyan
Write-Host "`nPress any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

