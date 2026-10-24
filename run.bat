@echo off
rem run.bat - launch msc with the bundled 32-bit Python
rem 64-bit Python cannot create the Multisim COM object (class is registered
rem only in the WOW6432Node / 32-bit registry view), so always use this.
setlocal
cd /d "%~dp0"
if not exist "runtime\py32\python.exe" (
    echo [!] runtime\py32\python.exe not found.
    echo     Run:  python setup_env.py
    exit /b 1
)
"runtime\py32\python.exe" cli.py %*
