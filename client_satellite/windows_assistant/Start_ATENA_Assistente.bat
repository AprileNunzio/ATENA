@echo off
setlocal
cd /d "%~dp0"
title ATENA Assistente
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python non e installato su questo PC.
  echo  Si aprira la pagina di download: installa Python 3.10 o piu recente
  echo  e metti la spunta su "Add Python to PATH". Poi riavvia questo file.
  echo.
  start https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo  Prima installazione di ATENA: preparo i componenti, ci vogliono 1-3 minuti...
  python -m venv .venv || goto error
)
fc /b requirements.txt ".venvequirements.installed" >nul 2>nul
if errorlevel 1 (
  echo  Installo o aggiorno i componenti di ATENA...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements.txt || goto error
  copy /y requirements.txt ".venvequirements.installed" >nul
)
start "" ".venv\Scripts\pythonw.exe" atena_assistant.py
exit /b 0
:error
echo.
echo  Installazione non riuscita. Controlla la connessione a Internet e riprova.
echo  Se il problema continua, invia questa schermata a chi gestisce ATENA.
pause
exit /b 1
