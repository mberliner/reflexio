@echo off
setlocal enabledelayedexpansion

echo.
echo [INFO] Reflexio Dicta - Demo de onboarding (Windows)
echo [INFO] Experimento: email_urgency
echo.

:: --- Configuración de Python ---
set PY_CMD=
for %%c in (py python python3) do (
    where %%c >nul 2>nul
    if !errorlevel! equ 0 (
        %%c -c "import sys" >nul 2>nul
        if !errorlevel! equ 0 (
            set PY_CMD=%%c
            goto :found_python
        )
    )
)

:found_python
if "%PY_CMD%"=="" (
    echo [ERROR] Python no encontrado o es el shim de MS Store.
    echo Asegurate de tener Python instalado y en el PATH.
    exit /b 1
)

:: Verificar versión
for /f "tokens=*" %%v in ('%PY_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VER=%%v
echo [OK] Python %PY_VER% (%PY_CMD%)

:: --- Procesar Argumentos ---
set MODE=%1
set CHECK_ONLY=false
if "%MODE%"=="" set MODE=both
if "%MODE%"=="--check" (
    set CHECK_ONLY=true
    set MODE=both
)

:: --- Validar Dependencias ---
%PY_CMD% -c "import gepa, dspy" >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Dependencias faltantes: gepa o dspy
    echo Instala con: %PY_CMD% -m pip install gepa dspy
    exit /b 1
)
echo [OK] Dependencias instaladas

:: --- Validar Archivos y .env ---
set "GEPA_CONFIG=gepa_standalone/experiments/configs/email_urgency.yaml"
set "DSPY_CONFIG=dspy_gepa_poc/configs/dynamic_email_urgency.yaml"

if not exist %GEPA_CONFIG% echo [ERROR] Falta %GEPA_CONFIG% && exit /b 1
if not exist %DSPY_CONFIG% echo [ERROR] Falta %DSPY_CONFIG% && exit /b 1

:: Check .env usando Python para evitar problemas de encoding con findstr
%PY_CMD% -c "import os; from dotenv import load_dotenv; load_dotenv('gepa_standalone/.env'); exit(0 if os.getenv('LLM_API_KEY') else 1)" >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo validar LLM_API_KEY en gepa_standalone/.env
    echo Verifique que el archivo existe y contiene LLM_API_KEY=tu_clave
    exit /b 1
)
echo [OK] Archivos y configuracion verificados

if "%CHECK_ONLY%"=="true" (
    echo.
    echo [OK] Validacion completa. Entorno listo para ejecutar.
    exit /b 0
)

:: --- Ejecución ---
if "%MODE%"=="gepa" goto :run_gepa
if "%MODE%"=="dspy" goto :run_dspy
if "%MODE%"=="both" (
    call :run_gepa_sub
    call :run_dspy_sub
    goto :end
)

:run_gepa
call :run_gepa_sub
goto :end

:run_dspy
call :run_dspy_sub
goto :end

:run_gepa_sub
echo.
echo === GEPA Standalone: email_urgency ===
%PY_CMD% gepa_standalone/universal_optimizer.py --config %GEPA_CONFIG%
exit /b 0

:run_dspy_sub
echo.
echo === DSPy + GEPA: email_urgency ===
%PY_CMD% dspy_gepa_poc/reflexio_declarativa.py --config %DSPY_CONFIG%
exit /b 0

:end
echo.
echo [OK] Demo completada.
exit /b 0
