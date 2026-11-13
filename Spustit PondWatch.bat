@echo off
setlocal
cd /d "%~dp0"

rem 1. Check for existing local virtual environment
if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "venv\bin\python.exe" (
    set "PYTHON=venv\bin\python.exe"
) else (
    rem 2. Find base python to create virtual environment
    if exist "%USERPROFILE%\anaconda3\python.exe" (
        set "BASE_PYTHON=%USERPROFILE%\anaconda3\python.exe"
    ) else (
        where py >nul 2>nul
        if not errorlevel 1 (
            set "BASE_PYTHON=py -3"
        ) else (
            where python >nul 2>nul
            if not errorlevel 1 (
                set "BASE_PYTHON=python"
            ) else (
                echo Python nebyl nalezen. Nainstalujte Python 3 a zkuste to znovu.
                pause
                exit /b 1
            )
        )
    )

    rem Create .venv automatically if missing
    echo Vytvarim virtualni prostredi .venv...
    %BASE_PYTHON% -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PYTHON=.venv\Scripts\python.exe"
    ) else (
        set "PYTHON=%BASE_PYTHON%"
    )
)

echo Pouzivam Python: %PYTHON%

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

echo Spoustim PondWatch AI na http://localhost:8502 ...
start "" http://localhost:8502
%PYTHON% -m streamlit run scripts/app.py --server.port 8502
if errorlevel 1 (
    echo Aplikaci se nepodarilo spustit.
    pause
)
