@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m core.games.controller_window
) else (
    python -m core.games.controller_window
)
if errorlevel 1 (
    echo.
    echo Nao foi possivel abrir o receptor JoJo-OS.
    echo Instale Python 3 com Tcl/Tk e veja a mensagem acima.
    pause
)
endlocal
