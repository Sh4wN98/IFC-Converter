@echo off
setlocal
rem Startet den IFC File Converter (Fenster). Mit Dateien als Argument laeuft die Kommandozeilen-Version.
rem Beim ersten Start (und nach Updates) wird alles automatisch eingerichtet.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title IFC File Converter
cd /d "%~dp0"

rem Aus einer ZIP-Datei heraus gestartet, fehlt alles ausser dieser Datei.
if not exist "pyproject.toml" goto notextracted

rem Neu einrichten, wenn sich pyproject.toml geaendert hat (z. B. neue Abhaengigkeiten).
set "STAMP="
for /f %%h in ('certutil -hashfile pyproject.toml MD5 ^| findstr /v ":"') do set "STAMP=%%h"
set "INSTALLED="
if exist ".venv\installed.ok" set /p INSTALLED=<".venv\installed.ok"
if defined STAMP if "%INSTALLED%"=="%STAMP%" goto run

echo Der Converter wird eingerichtet. Beim ersten Mal werden ca. 200 MB geladen,
echo das kann einige Minuten dauern ...
echo.
if exist ".venv\Scripts\python.exe" goto venvready
call :findpython
if not defined PYTHON goto nopython
echo Python gefunden: %PYTHON%
%PYTHON% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto venvfail

:venvready
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip --disable-pip-version-check
".venv\Scripts\python.exe" -m pip install -e . --disable-pip-version-check
if errorlevel 1 goto installfail
>".venv\installed.ok" echo %STAMP%
echo.
echo Eingerichtet.

:run
if not "%~1"=="" goto cli
rem pythonw.exe zeigt keine Fehler an, daher erst pruefen, ob das Fenster starten kann.
".venv\Scripts\python.exe" -c "import ifc_converter.gui"
if errorlevel 1 goto guifail
start "" ".venv\Scripts\pythonw.exe" -m ifc_converter.gui
exit /b

:cli
".venv\Scripts\python.exe" -m ifc_converter %*
if errorlevel 1 pause
exit /b

rem Sucht Python 3.10 oder neuer. Der Platzhalter aus dem Microsoft Store besteht die Pruefung nicht.
:findpython
set "PYTHON="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PYTHON=py -3" && exit /b
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PYTHON=python" && exit /b
exit /b

:notextracted
echo.
echo Bitte die ZIP-Datei zuerst entpacken (Rechtsklick, "Alle extrahieren ...")
echo und dann start.bat im entpackten Ordner doppelklicken.
pause
exit /b 1

:nopython
echo.
echo Python 3.10 oder neuer wurde nicht gefunden. Bitte installieren:
echo https://www.python.org/downloads/  (Haken bei "Add python.exe to PATH" setzen)
echo Danach dieses Fenster schliessen und start.bat erneut starten.
pause
exit /b 1

:venvfail
echo.
echo Die Python-Umgebung konnte nicht angelegt werden (Ordner .venv).
echo Liegt der Ordner an einem Ort mit Schreibrechten (z. B. Dokumente oder Desktop)?
pause
exit /b 1

:installfail
echo.
echo Die Installation ist fehlgeschlagen (siehe Meldungen oben). Ist eine Internetverbindung da
echo bzw. erlaubt die Firmen-IT den Zugriff auf pypi.org?
pause
exit /b 1

:guifail
echo.
echo Das Programmfenster konnte nicht gestartet werden (siehe Meldungen oben).
echo Tipp: den Ordner .venv loeschen und start.bat erneut starten.
pause
exit /b 1
