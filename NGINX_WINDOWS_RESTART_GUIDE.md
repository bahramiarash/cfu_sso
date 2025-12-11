# راهنمای Restart کردن Nginx در Windows Server

## روش‌های مختلف Restart کردن Nginx در Windows

### روش 1: استفاده از Command Prompt (CMD) یا PowerShell

#### الف) با دسترسی Administrator

```cmd
# باز کردن CMD یا PowerShell به عنوان Administrator
# سپس:

# روش 1: استفاده از taskkill و اجرای مجدد
taskkill /F /IM nginx.exe
cd C:\nginx
start nginx.exe

# روش 2: استفاده از nginx -s reload (بدون قطع سرویس)
cd C:\nginx
nginx.exe -s reload

# روش 3: استفاده از nginx -s quit و اجرای مجدد
cd C:\nginx
nginx.exe -s quit
    timeout /t 2
start nginx.exe
```

#### ب) با استفاده از مسیر کامل

```cmd
# اگر nginx در مسیر دیگری نصب شده است
C:\nginx\nginx.exe -s reload
# یا
C:\nginx\nginx.exe -s quit
C:\nginx\nginx.exe
```

### روش 2: استفاده از PowerShell

```powershell
# باز کردن PowerShell به عنوان Administrator

# روش 1: Reload (بدون قطع سرویس)
cd C:\nginx
.\nginx.exe -s reload

# روش 2: Stop و Start
Stop-Process -Name nginx -Force
Start-Process -FilePath "C:\nginx\nginx.exe"

# روش 3: با استفاده از Get-Process
Get-Process nginx | Stop-Process -Force
Start-Process -FilePath "C:\nginx\nginx.exe"
```

### روش 3: استفاده از Task Manager

1. باز کردن **Task Manager** (Ctrl + Shift + Esc)
2. رفتن به تب **Details**
3. پیدا کردن `nginx.exe`
4. راست کلیک → **End Task**
5. اجرای مجدد nginx از Command Prompt یا PowerShell

### روش 4: استفاده از Services (اگر nginx به عنوان Service نصب شده)

```cmd
# بررسی اینکه آیا nginx به عنوان Service نصب شده
sc query nginx

# اگر نصب شده باشد:
net stop nginx
net start nginx

# یا با PowerShell:
Stop-Service nginx
Start-Service nginx
```

### روش 5: استفاده از Batch Script

ایجاد فایل `restart_nginx.bat`:

```batch
@echo off
echo Stopping Nginx...
taskkill /F /IM nginx.exe 2>nul
timeout /t 2 /nobreak >nul
echo Starting Nginx...
cd /d C:\nginx
start nginx.exe
echo Nginx restarted successfully!
pause
```

یا برای reload (بدون قطع سرویس):

```batch
@echo off
echo Reloading Nginx configuration...
cd /d C:\nginx
nginx.exe -s reload
if %errorlevel% equ 0 (
    echo Nginx configuration reloaded successfully!
) else (
    echo Failed to reload. Trying restart...
    taskkill /F /IM nginx.exe 2>nul
    timeout /t 2 /nobreak >nul
    start nginx.exe
)
pause
```

## دستورات مفید Nginx در Windows

### بررسی وضعیت Nginx

```cmd
# بررسی اینکه nginx در حال اجرا است یا نه
tasklist | findstr nginx

# یا در PowerShell:
Get-Process nginx -ErrorAction SilentlyContinue
```

### تست تنظیمات Nginx

```cmd
cd C:\nginx
nginx.exe -t
```

### مشاهده لاگ‌ها

```cmd
# لاگ خطا
type C:\nginx\logs\error.log

# لاگ دسترسی
type C:\nginx\logs\access.log

# یا با PowerShell:
Get-Content C:\nginx\logs\error.log -Tail 50
```

### مشاهده تمام Process های Nginx

```cmd
tasklist | findstr nginx
```

## مراحل کامل Restart بعد از تغییر تنظیمات

### مرحله 1: تست تنظیمات

```cmd
cd C:\nginx
nginx.exe -t
```

اگر پیام `syntax is ok` و `test is successful` را دیدید، به مرحله بعد بروید.

### مرحله 2: Reload (توصیه می‌شود - بدون قطع سرویس)

```cmd
cd C:\nginx
nginx.exe -s reload
```

### مرحله 3: اگر Reload کار نکرد، Restart کامل

```cmd
# Stop
taskkill /F /IM nginx.exe

# Wait
timeout /t 2

# Start
cd C:\nginx
start nginx.exe
```

## اسکریپت PowerShell کامل

ایجاد فایل `restart_nginx.ps1`:

```powershell
# restart_nginx.ps1
# Restart Nginx on Windows Server

$nginxPath = "C:\nginx"
$nginxExe = "$nginxPath\nginx.exe"

Write-Host "Checking Nginx status..." -ForegroundColor Yellow

# Check if nginx is running
$nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue

if ($nginxProcess) {
    Write-Host "Nginx is running. Testing configuration..." -ForegroundColor Yellow
    
    # Test configuration
    & $nginxExe -t
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Configuration is valid. Reloading..." -ForegroundColor Green
        & $nginxExe -s reload
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Nginx reloaded successfully!" -ForegroundColor Green
        } else {
            Write-Host "Reload failed. Restarting..." -ForegroundColor Yellow
            Stop-Process -Name nginx -Force
            Start-Sleep -Seconds 2
            Start-Process -FilePath $nginxExe
            Write-Host "Nginx restarted!" -ForegroundColor Green
        }
    } else {
        Write-Host "Configuration test failed! Please fix errors first." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Nginx is not running. Starting..." -ForegroundColor Yellow
    Start-Process -FilePath $nginxExe
    Write-Host "Nginx started!" -ForegroundColor Green
}

# Verify
Start-Sleep -Seconds 1
$nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue
if ($nginxProcess) {
    Write-Host "Nginx is running. PID: $($nginxProcess.Id)" -ForegroundColor Green
} else {
    Write-Host "Failed to start Nginx!" -ForegroundColor Red
    exit 1
}
```

**استفاده:**
```powershell
# در PowerShell به عنوان Administrator
.\restart_nginx.ps1
```

## اسکریپت Batch کامل

ایجاد فایل `restart_nginx.bat`:

```batch
@echo off
chcp 65001 >nul
echo ========================================
echo Restart Nginx on Windows Server
echo ========================================
echo.

set NGINX_PATH=C:\nginx
set NGINX_EXE=%NGINX_PATH%\nginx.exe

echo Checking Nginx status...
tasklist | findstr /I nginx.exe >nul
if %errorlevel% equ 0 (
    echo Nginx is running.
    echo.
    echo Testing configuration...
    cd /d %NGINX_PATH%
    %NGINX_EXE% -t
    
    if %errorlevel% equ 0 (
        echo Configuration is valid.
        echo.
        echo Reloading Nginx...
        %NGINX_EXE% -s reload
        
        if %errorlevel% equ 0 (
            echo.
            echo ✅ Nginx reloaded successfully!
        ) else (
            echo.
            echo ⚠️  Reload failed. Restarting...
            taskkill /F /IM nginx.exe 2>nul
            timeout /t 2 /nobreak >nul
            start %NGINX_EXE%
            echo.
            echo ✅ Nginx restarted!
        )
    ) else (
        echo.
        echo ❌ Configuration test failed!
        echo Please fix errors in nginx configuration first.
        pause
        exit /b 1
    )
) else (
    echo Nginx is not running.
    echo.
    echo Starting Nginx...
    cd /d %NGINX_PATH%
    start %NGINX_EXE%
    echo.
    echo ✅ Nginx started!
)

echo.
echo Verifying...
timeout /t 1 /nobreak >nul
tasklist | findstr /I nginx.exe >nul
if %errorlevel% equ 0 (
    echo ✅ Nginx is running.
) else (
    echo ❌ Failed to start Nginx!
    pause
    exit /b 1
)

echo.
echo ========================================
pause
```

## نصب Nginx به عنوان Windows Service (اختیاری)

اگر می‌خواهید nginx به عنوان Windows Service اجرا شود:

### استفاده از NSSM (Non-Sucking Service Manager)

1. دانلود NSSM از: https://nssm.cc/download
2. استخراج و کپی `nssm.exe` به یک مسیر (مثلاً `C:\tools\`)
3. نصب Service:

```cmd
# در CMD به عنوان Administrator
C:\tools\nssm.exe install nginx "C:\nginx\nginx.exe"
C:\tools\nssm.exe set nginx AppDirectory "C:\nginx"
C:\tools\nssm.exe set nginx DisplayName "Nginx Web Server"
C:\tools\nssm.exe set nginx Description "Nginx Web Server"
C:\tools\nssm.exe set nginx Start SERVICE_AUTO_START

# شروع Service
net start nginx
```

بعد از نصب به عنوان Service:

```cmd
# Restart
net stop nginx
net start nginx

# یا با PowerShell:
Restart-Service nginx
```

## عیب‌یابی

### اگر nginx شروع نمی‌شود:

1. **بررسی لاگ خطا:**
   ```cmd
   type C:\nginx\logs\error.log
   ```

2. **بررسی Port:**
   ```cmd
   netstat -ano | findstr :80
   netstat -ano | findstr :443
   ```

3. **بررسی تنظیمات:**
   ```cmd
   cd C:\nginx
   nginx.exe -t
   ```

### اگر Port در حال استفاده است:

```cmd
# پیدا کردن Process که Port 80 را استفاده می‌کند
netstat -ano | findstr :80

# متوقف کردن Process (PID را از خروجی بالا بگیرید)
taskkill /F /PID <PID>
```

## خلاصه دستورات

```cmd
# تست تنظیمات
cd C:\nginx && nginx.exe -t

# Reload (بدون قطع سرویس)
cd C:\nginx && nginx.exe -s reload

# Restart کامل
taskkill /F /IM nginx.exe && timeout /t 2 && cd C:\nginx && start nginx.exe

# بررسی وضعیت
tasklist | findstr nginx
```

## نکات مهم

1. **همیشه قبل از restart، `nginx -t` را اجرا کنید** تا از صحت تنظیمات اطمینان حاصل کنید
2. **از `reload` استفاده کنید** تا سرویس قطع نشود
3. **اگر nginx به عنوان Service نصب شده، از `net stop/start` استفاده کنید**
4. **برای تغییرات در فایل تنظیمات، `reload` کافی است و نیازی به restart کامل نیست**

