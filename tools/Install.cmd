@echo off
rem Install or update Blackboard for the current user.
rem
rem This file ships inside every release zip, next to an "app" folder holding
rem the executable. Running it copies the executable to one fixed location and
rem points .blk files at that location. Because the location never changes,
rem every board always opens in whatever version was installed last -- there
rem is no second copy that can go stale.
rem
rem No administrator rights are needed: everything lives under the current
rem user's own folders and registry.
rem
rem Pass /nopause to skip the "press any key" at the end (used by release.ps1).

setlocal

set "TARGET=%LOCALAPPDATA%\Programs\Blackboard"
set "EXE=%TARGET%\Blackboard.exe"
set "SOURCE=%~dp0app\Blackboard.exe"

set "NOPAUSE="
if /I "%~1"=="/nopause" set "NOPAUSE=1"

set "VER="
if exist "%~dp0app\version.txt" set /p VER=<"%~dp0app\version.txt"

echo.
if defined VER echo Installing Blackboard version %VER%
if not defined VER echo Installing Blackboard
echo Destination: %TARGET%
echo.

if not exist "%SOURCE%" (
    echo ERROR: cannot find "%SOURCE%".
    echo Unpack the whole zip file before running this, not just Install.cmd.
    goto :fail
)

rem Overwriting a running executable fails, and force-closing it could lose
rem unsaved boards. Ask instead.
tasklist /FI "IMAGENAME eq Blackboard.exe" 2>nul | find /I "Blackboard.exe" >nul
if not errorlevel 1 (
    echo ERROR: Blackboard is running. Close it and run this again.
    goto :fail
)

if not exist "%TARGET%" mkdir "%TARGET%"
copy /y "%SOURCE%" "%EXE%" >nul
if errorlevel 1 (
    echo ERROR: could not copy the executable to "%TARGET%".
    goto :fail
)

rem Register .blk for this user. .bee is deliberately left alone, so a stock
rem BeeRef installation keeps its own files.
reg add "HKCU\Software\Classes\.blk" /ve /t REG_SZ /d "Blackboard.Board" /f >nul
reg add "HKCU\Software\Classes\Blackboard.Board" /ve /t REG_SZ /d "Blackboard Board" /f >nul
reg add "HKCU\Software\Classes\Blackboard.Board\DefaultIcon" /ve /t REG_SZ /d "\"%EXE%\",0" /f >nul
reg add "HKCU\Software\Classes\Blackboard.Board\shell\open\command" /ve /t REG_SZ /d "\"%EXE%\" \"%%1\"" /f >nul
if errorlevel 1 (
    echo ERROR: could not register .blk files.
    goto :fail
)

rem Make Explorer notice the new association without needing a restart.
ie4uinit.exe -show >nul 2>&1

echo Done.
echo.
echo Blackboard is installed at:
echo   %EXE%
echo Double-clicking a .blk board now opens this version.
echo Check Help - About inside the application to confirm the version.
echo.
if not defined NOPAUSE pause
exit /b 0

:fail
echo.
echo Installation failed. Nothing was changed.
echo.
if not defined NOPAUSE pause
exit /b 1
