@echo off
chcp 65001 >nul
title Chilli Beans - Configuracao Inicial

echo.
echo  =============================================
echo   CHILLI BEANS - Configuracao Inicial
echo  =============================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado neste computador.
    echo.
    echo  Siga os passos abaixo:
    echo   1. Acesse: https://www.python.org/downloads/
    echo   2. Baixe e instale o Python 3.11 ou superior
    echo   3. IMPORTANTE: na instalacao, marque a opcao
    echo      "Add Python to PATH"
    echo   4. Reinicie o computador
    echo   5. Execute este arquivo novamente
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo  [OK] %PYVER% encontrado.
echo.

:: Cria ambiente virtual se nao existir
if not exist "venv" (
    echo  Criando ambiente virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo  [OK] Ambiente virtual criado.
    echo.
)

:: Ativa e instala dependencias
echo  Instalando dependencias (aguarde, pode demorar alguns minutos)...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet --disable-pip-version-check
pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar dependencias.
    echo        Verifique sua conexao com a internet e tente novamente.
    pause
    exit /b 1
)

:: Cria pasta de dados
if not exist "data" mkdir data

echo.
echo  =============================================
echo   [OK] Configuracao concluida com sucesso!
echo.
echo   Agora use o arquivo "Iniciar.bat" para
echo   abrir o programa.
echo  =============================================
echo.
pause
