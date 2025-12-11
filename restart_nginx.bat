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

