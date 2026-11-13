@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python nebyl nalezen. Nainstalujte Python 3 a zkuste to znovu.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import streamlit, pyproj" >nul 2>nul
if errorlevel 1 (
    echo Instaluji zavislosti aplikace...
    %PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Instalace zavislosti selhala.
        pause
        exit /b 1
    )
)

start "" http://localhost:8502
%PYTHON% -m streamlit run scripts/app.py --server.port 8502
if errorlevel 1 (
    echo Aplikaci se nepodarilo spustit.
    pause
)
