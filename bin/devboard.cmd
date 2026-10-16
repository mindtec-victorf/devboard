@echo off
rem devboard CLI launcher for Windows (installed by install.ps1). Prefers the py launcher, then python.
set "DEVBOARD_SCRIPT=%~dp0..\skills\devboard\scripts\devboard.py"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%DEVBOARD_SCRIPT%" %*
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python "%DEVBOARD_SCRIPT%" %*
  exit /b
)
echo devboard needs Python 3.10+ (python.org or the Microsoft Store) 1>&2
exit /b 1
