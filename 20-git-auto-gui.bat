@echo off
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
start "" pythonw "C:\Users\my4nt\OneDrive - Early Buddhism Meditation Preservation Society\lucid24\py_tools\git-tools\git-auto-gui.pyw" --dir "%DIR%" %*
