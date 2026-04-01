@echo off
title CodeMini Копирайтер
cd /d "%~dp0"
echo Запуск веб-бота CodeMini...
echo Открой браузер: http://localhost:5001
echo.
python -m codemini.web.app
pause
