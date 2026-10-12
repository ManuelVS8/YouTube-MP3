@echo off
setlocal EnableExtensions
title Instalador - Descargador YouTube
cd /d "%~dp0"
echo ==================================================
echo    Descargador YouTube - Instalacion
echo ==================================================
echo.

call :findpy
if defined PYEXE goto havepy

echo [1/3] No se ha encontrado Python. Instalando Python 3.12 (gratis)...
where winget >nul 2>nul
if errorlevel 1 goto nowinget
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpy
if not defined PYEXE goto pyfail

:havepy
echo [1/3] Python listo: %PYEXE%
echo.
echo [2/3] Instalando componentes: yt-dlp, ffmpeg y deno...
"%PYEXE%" -m pip install --disable-pip-version-check -U "yt-dlp[default]" deno imageio-ffmpeg
if errorlevel 1 goto pipfail
echo.
echo [3/3] Creando acceso directo en el escritorio...
"%PYEXE%" "%~dp0descargador_youtube.pyw" --crear-acceso
echo.
echo Listo. Abriendo el programa...
start "" "%PYWEXE%" "%~dp0descargador_youtube.pyw"
timeout /t 3 >nul
exit /b 0

:findpy
set "PYEXE="
set "PYWEXE="
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%i"
if defined PYEXE goto fp_done
for %%v in (313 312 311 310) do if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
:fp_done
if not defined PYEXE exit /b 0
for %%Q in ("%PYEXE%") do set "PYWEXE=%%~dpQpythonw.exe"
if not exist "%PYWEXE%" set "PYWEXE=%PYEXE%"
exit /b 0

:nowinget
echo.
echo No se puede instalar Python automaticamente en este equipo.
echo Se abrira la pagina oficial: descarga Python, instalalo y
echo MARCA la casilla "Add python.exe to PATH". Despues vuelve a
echo ejecutar este instalador.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:pyfail
echo.
echo Python se ha instalado, pero hay que volver a ejecutar este
echo instalador para continuar. Cierra esta ventana y abrelo otra vez.
pause
exit /b 1

:pipfail
echo.
echo No se pudieron instalar los componentes. Revisa la conexion
echo a Internet y vuelve a ejecutar el instalador.
pause
exit /b 1
