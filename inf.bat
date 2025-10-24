@echo off
color 0A
:START
cls
echo ================================
echo       SYSTEM INFORMATION
echo ================================
systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type"
echo.
echo Running your Python script...
echo ================================
python main.py
echo.
echo Script finished. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto START
