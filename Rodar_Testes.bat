@echo off
REM ============================================================
REM  Pepper - Suite de testes automatizados (unittest / stdlib)
REM  Nao instala nada. Roda a logica pura: RFM, telefone/WhatsApp,
REM  faixas de preco. Use antes de publicar qualquer mudanca.
REM ============================================================
cd /d "%~dp0"
echo Rodando testes do Pepper...
echo.
venv\Scripts\python.exe -m unittest discover -s tests -v
echo.
echo ============================================================
if %ERRORLEVEL%==0 (
  echo  RESULTADO: TODOS OS TESTES PASSARAM.
) else (
  echo  RESULTADO: HOUVE FALHAS - revise antes de publicar.
)
echo ============================================================
pause
