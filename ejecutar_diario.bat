@echo off
:: ============================================================
:: PRONACA - Actualizacion diaria
:: - ETL: todos los dias
:: - Reentrenamiento: solo dia 28 o 29 del mes
:: ============================================================

set PYTHON=C:\Users\willi\AppData\Local\Microsoft\WindowsApps\python.exe
set BASE=D:\Proyectos\Pronaca\Avicola\DashboardFinal
set LOG=%BASE%\logs\ejecucion.log

:: Crear carpeta de logs si no existe
if not exist "%BASE%\logs" mkdir "%BASE%\logs"

echo. >> "%LOG%"
echo ============================================================ >> "%LOG%"
echo Inicio: %DATE% %TIME% >> "%LOG%"
echo ============================================================ >> "%LOG%"

:: ── PASO 1: ETL (siempre) ────────────────────────────────────
echo [%TIME%] Ejecutando ETL... >> "%LOG%"
"%PYTHON%" "%BASE%\etl\etl.py" >> "%LOG%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [%TIME%] ERROR en ETL - codigo %ERRORLEVEL% >> "%LOG%"
    goto fin
)
echo [%TIME%] ETL completado OK >> "%LOG%"

:: ── PASO 2: Reentrenamiento (solo dia 28 o 29) ──────────────
:: Usamos PowerShell para obtener el dia del mes de forma robusta
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).Day"') do set DIA=%%d

if "%DIA%"=="28" goto entrenar
if "%DIA%"=="29" goto entrenar
goto fin

:entrenar
echo [%TIME%] Dia %DIA% del mes - Ejecutando reentrenamiento... >> "%LOG%"
"%PYTHON%" "%BASE%\models\retrain_model.py" >> "%LOG%" 2>&1
if %ERRORLEVEL% neq 0 (
    echo [%TIME%] ERROR en reentrenamiento - codigo %ERRORLEVEL% >> "%LOG%"
    goto fin
)
echo [%TIME%] Reentrenamiento completado OK >> "%LOG%"

:fin
echo [%TIME%] Proceso finalizado >> "%LOG%"
