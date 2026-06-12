@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist "SimpAI_Studio\simpleai_update.py" (
    echo Missing update script: SimpAI_Studio\simpleai_update.py
    echo Put this bat next to the SimpAI_Studio folder.
    pause
    exit /b 1
)

if exist ".\python_embeded\python.exe" (
    .\python_embeded\python.exe -s SimpAI_Studio\simpleai_update.py %*
) else (
    python -s SimpAI_Studio\simpleai_update.py %*
)

echo.
echo All done.
echo Press any key to continue.
pause > nul
cmd