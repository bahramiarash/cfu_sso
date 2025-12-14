# stop-all-services.ps1
Write-Host "Stopping all microservices..." -ForegroundColor Yellow

# Find and kill Python processes running services
$services = @("auth-service", "admin-service", "survey-service", "dashboard-service", "kanban-service", "gateway-service")

foreach ($service in $services) {
    $processes = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -like "*cert2*" -and $_.CommandLine -like "*$service*"
    }
    
    if ($processes) {
        Write-Host "Stopping $service..." -ForegroundColor Yellow
        $processes | Stop-Process -Force
    }
}

# Stop Monolithic App (running on port 5006)
Write-Host "Stopping Monolithic App..." -ForegroundColor Yellow
try {
    # Try to find process using port 5006
    $port5006 = Get-NetTCPConnection -LocalPort 5006 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($port5006) {
        foreach ($pid in $port5006) {
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($proc -and $proc.Path -like "*cert2*") {
                Write-Host "Stopping process on port 5006 (PID: $pid)..." -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        }
    }
    
    # Also try to find by command line (using WMI)
    $monolithicProcesses = Get-WmiObject Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*cert2*" -and (
            $_.CommandLine -like "*app\app.py*" -or 
            $_.CommandLine -like "*app/app.py*" -or
            ($_.CommandLine -like "*\app.py*" -and $_.CommandLine -like "*\app\*")
        )
    }
    
    if ($monolithicProcesses) {
        foreach ($proc in $monolithicProcesses) {
            Write-Host "Stopping Monolithic App (PID: $($proc.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Write-Host "Monolithic App stopped." -ForegroundColor Green
    } elseif (-not $port5006) {
        Write-Host "Monolithic App not running." -ForegroundColor Gray
    }
} catch {
    Write-Host "Could not check for Monolithic App: $_" -ForegroundColor Yellow
}

# Stop Metrics Service (running on port 6000)
Write-Host "Stopping Metrics Service (Zabbix)..." -ForegroundColor Yellow
try {
    # Try to find process using port 6000
    $port6000 = Get-NetTCPConnection -LocalPort 6000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    if ($port6000) {
        foreach ($processId in $port6000) {
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($proc -and $proc.Path -like "*cert2*") {
                Write-Host "Stopping process on port 6000 (PID: $processId)..." -ForegroundColor Yellow
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Host "Metrics Service stopped." -ForegroundColor Green
    } else {
        Write-Host "Metrics Service not running." -ForegroundColor Gray
    }
    
    # Also try to find by command line (using WMI)
    $metricsProcesses = Get-WmiObject Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*cert2*" -and $_.CommandLine -like "*zabbix2.py*"
    }
    
    if ($metricsProcesses) {
        foreach ($proc in $metricsProcesses) {
            Write-Host "Stopping Metrics Service (PID: $($proc.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    Write-Host "Could not check for Metrics Service: $_" -ForegroundColor Yellow
}

# Alternative: Kill all Python processes in cert2 directory (more aggressive)
$allPython = Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*cert2*"
}

if ($allPython) {
    Write-Host "Stopping all Python processes in cert2..." -ForegroundColor Yellow
    $allPython | Stop-Process -Force
}

Write-Host "All services stopped!" -ForegroundColor Green

