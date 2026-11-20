@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Use: arraste um arquivo para este .bat ou passe o caminho como primeiro argumento.
rem O script não guarda tokens; usa a autenticação Git/Git Credential Manager já instalada.
if "%~1"=="" (
    echo Uso: arraste um arquivo do repositório para este .bat
    echo   ou execute: ENVIAR_ARQUIVO_GITHUB.bat "caminho\do\arquivo"
    echo.
    set /p "INPUT=Arquivo a enviar: "
) else (
    set "INPUT=%~1"
)
if not defined INPUT (
    echo Nenhum arquivo informado.
    exit /b 2
)

for %%I in ("%INPUT%") do set "TARGET=%%~fI"
if not exist "%TARGET%" (
    echo Arquivo nao encontrado: "%TARGET%"
    exit /b 3
)
if exist "%TARGET%\*" (
    echo O caminho selecionado e uma pasta. Arraste um arquivo individual.
    exit /b 3
)

for /f "delims=" %%R in ('git -C "%~dp0" rev-parse --show-toplevel 2^>nul') do set "ROOT=%%R"
if not defined ROOT (
    echo Esta pasta nao esta dentro de um repositorio Git.
    echo Clone o seu repositorio GitHub e coloque este .bat na raiz antes de usar.
    exit /b 4
)

for /f "delims=" %%B in ('git -C "%ROOT%" symbolic-ref --quiet --short HEAD 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH (
    echo HEAD esta destacado. Mude para uma branch antes de enviar.
    exit /b 5
)

set "REMOTE="
for /f "delims=" %%U in ('git -C "%ROOT%" remote get-url origin 2^>nul') do set "REMOTE=%%U"
if not defined REMOTE (
    echo Nao existe remote origin configurado.
    echo Configure o remote do GitHub com git remote add origin URL_DO_REPOSITORIO
    exit /b 6
)
set "JOJO_GIT_REMOTE=%REMOTE%"
powershell.exe -NoProfile -Command "if ($env:JOJO_GIT_REMOTE -match '(?i)^(https?://|ssh://)?([^/@]+@)?github\.com[:/].+') { exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
    echo O remote origin configurado nao parece ser do GitHub. Nada foi enviado.
    exit /b 7
)

set "JOJO_GIT_ROOT=%ROOT%"
set "JOJO_GIT_FILE=%TARGET%"
set "REL="
for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "$root=(Resolve-Path -LiteralPath $env:JOJO_GIT_ROOT).Path.TrimEnd([char]92); $file=(Resolve-Path -LiteralPath $env:JOJO_GIT_FILE).Path; $prefix=$root+[IO.Path]::DirectorySeparatorChar; if(-not $file.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){exit 8}; $file.Substring($prefix.Length).Replace([char]92,[char]47)"`) do set "REL=%%P"
if not defined REL (
    echo O arquivo precisa estar dentro da pasta deste repositorio.
    exit /b 8
)

rem Evita incluir acidentalmente arquivos que ja estavam staged por outra operacao.
git -C "%ROOT%" diff --cached --quiet
if errorlevel 1 (
    echo Ha outras alteracoes staged. Envie-as primeiro ou limpe o stage; nada foi commitado.
    exit /b 9
)

git -C "%ROOT%" add -- "%REL%"
if errorlevel 1 (
    echo Falha ao preparar o arquivo.
    exit /b 10
)
git -C "%ROOT%" diff --cached --quiet
if not errorlevel 1 (
    echo O arquivo nao tem alteracoes novas. Nada para enviar.
    exit /b 0
)

git -C "%ROOT%" commit -m "Update selected file"
if errorlevel 1 (
    echo Commit falhou. O arquivo pode continuar staged; revise o Git antes de tentar novamente.
    exit /b 11
)

echo Enviando somente o commit atual para origin/%BRANCH%...
git -C "%ROOT%" push origin HEAD
if errorlevel 1 (
    echo Push falhou. O commit local foi mantido; revise a autenticacao e o estado remoto.
    echo O script nao usa force-push nem armazena token.
    exit /b 12
)
echo Arquivo enviado ao GitHub com sucesso.
endlocal
