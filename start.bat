@echo off
rem Startet den IFC File Converter (Fenster). Mit Dateien als Argument laeuft die Kommandozeilen-Version.
rem Beim ersten Start (und nach Updates) wird alles automatisch eingerichtet.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title IFC File Converter
cd /d "%~dp0"

rem Neu einrichten, wenn sich pyproject.toml geaendert hat (z. B. neue Abhaengigkeiten).
for /f %%h in ('certutil -hashfile pyproject.toml MD5 ^| findstr /v ":"') do set STAMP=%%h
set /p INSTALLED=<".venv\installed.ok" 2>nul
if "%INSTALLED%"=="%STAMP%" goto run

echo Der Converter wird eingerichtet, das dauert einen Moment ...
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
)
if not exist ".venv\Scripts\python.exe" goto nopython
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -e .
if errorlevel 1 goto installfail
>".venv\installed.ok" echo %STAMP%

:run
if not "%~1"=="" goto cli
start "" ".venv\Scripts\pythonw.exe" -m ifc_converter.gui
exit /b

:cli
".venv\Scripts\python.exe" -m ifc_converter %*
if errorlevel 1 pause
exit /b

:nopython
echo.
echo Python wurde nicht gefunden. Bitte Python 3.10 oder neuer installieren:
echo https://www.python.org/downloads/  (Haken bei "Add python.exe to PATH" setzen)
pause
exit /b 1

:installfail
echo.
echo Die Installation ist fehlgeschlagen. Ist eine Internetverbindung da
echo bzw. erlaubt die Firmen-IT den Zugriff auf pypi.org?
pause
exit /b 1
