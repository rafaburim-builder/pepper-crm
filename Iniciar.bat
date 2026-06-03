@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Pepper - Chilli Beans

echo.
echo  ============================================
echo   PEPPER - Chilli Beans
echo  ============================================
echo.

:: 1. Encerra qualquer instancia anterior (libera arquivos travados)
taskkill /f /im streamlit.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: 2. Apaga cache Python antigo (garante leitura do codigo mais recente)
rmdir /s /q "__pycache__"          2>nul
rmdir /s /q "api\__pycache__"      2>nul
rmdir /s /q "modules\__pycache__"  2>nul

:: 3. Configura ambiente (nao grava novo cache)
set PYTHONDONTWRITEBYTECODE=1

:: 4. Verifica venv — configura se for a primeira vez
if not exist "venv\Scripts\activate.bat" (
    echo  Primeira execucao: configurando ambiente...
    call Configurar.bat
    if errorlevel 1 (
        echo [ERRO] Falha na configuracao.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

:: 5. Verifica dependencias
streamlit --version >nul 2>&1
if errorlevel 1 (
    echo  Instalando dependencias...
    pip install -r requirements.txt --quiet --disable-pip-version-check
)

echo  Iniciando Pepper...
echo.
echo  O sistema abrira automaticamente no navegador.
echo  Endereco: http://localhost:8501
echo.
echo  Para FECHAR: pressione Ctrl+C nesta janela.
echo  ============================================
echo.

streamlit run app.py ^
    --server.headless false ^
    --browser.gatherUsageStats false ^
    --server.port 8501 ^
    --theme.base dark ^
    --theme.primaryColor "#D4002A"

pause
