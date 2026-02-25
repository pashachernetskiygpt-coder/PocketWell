@echo off
setlocal

REM Переходим в папку, где лежит батник и csg.py
cd /d "%~dp0"

REM === Определяем, чем запускать Python ===
set "PYTHON_EXE="

REM 1) Локальное виртуальное окружение .venv (если есть)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

REM 2) Если venv не найден - пробуем python из PATH
if "%PYTHON_EXE%"=="" (
    where python >nul 2>&1
    if %errorlevel%==0 (
        REM python доступен по PATH
        set "PYTHON_EXE=python"
    )
)

REM 3) Если и в PATH нет - используем портативный Python с работы
if "%PYTHON_EXE%"=="" (
    set "PYTHON_EXE=D:\Portable\Python313\python.exe"
)

REM 4) Если всё равно пусто - что-то совсем не так
if "%PYTHON_EXE%"=="" (
    echo [ОШИБКА] Не удалось найти Python ни в .venv, ни в PATH, ни по фиксированному пути.
    echo Проверь установку Python.
    pause
    exit /b 1
)

REM Если PYTHON_EXE - это путь (с двоеточием/слешом) - проверяем, что файл существует
echo %PYTHON_EXE% | findstr /r "[\\:]" >nul
if %errorlevel%==0 (
    if not exist "%PYTHON_EXE%" (
        echo [ОШИБКА] Не найден интерпретатор Python:
        echo   "%PYTHON_EXE%"
        echo Исправь путь в csg.bat или поставь Python.
        pause
        exit /b 1
    )
)

echo Используется Python: "%PYTHON_EXE%"
echo Запуск csg.py ...

REM --- Запуск приложения ---
"%PYTHON_EXE%" "%~dp0csg.py"
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
    echo.
    echo [ОШИБКА] csg.py завершился с кодом %ERR%.
    echo См. program_debug.log для деталей.
    pause
    exit /b %ERR%
)

endlocal
exit /b 0
